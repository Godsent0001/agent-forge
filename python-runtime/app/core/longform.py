"""Resumable long-form production workflow for any text-heavy domain.

Sections are checkpointed independently in SQLite. The caller supplies the model
adapter; the workflow never assumes a particular LLM provider or context window.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Sequence


@dataclass(frozen=True)
class SectionSpec:
    section_id: str
    title: str
    instructions: str
    acceptance_criteria: tuple[str, ...] = ()


@dataclass(frozen=True)
class SectionResult:
    section: SectionSpec
    content: str
    sha256: str
    word_count: int
    reused_checkpoint: bool = False


@dataclass(frozen=True)
class LongFormResult:
    project_id: str
    title: str
    sections: tuple[SectionResult, ...]
    content: str
    sha256: str
    word_count: int


SectionGenerator = Callable[[str, SectionSpec, str, tuple[str, ...]], Awaitable[str]]
SectionVerifier = Callable[[SectionSpec, str], Awaitable[bool | tuple[bool, str]]]


class LongFormWorkflow:
    """Persistent outline -> section generation -> consistency context -> assembly."""

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS longform_projects (
                    project_id TEXT PRIMARY KEY, title TEXT NOT NULL, outline_json TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS longform_sections (
                    project_id TEXT NOT NULL, section_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    title TEXT NOT NULL, instructions TEXT NOT NULL, criteria_json TEXT NOT NULL,
                    content TEXT NOT NULL, sha256 TEXT NOT NULL, word_count INTEGER NOT NULL,
                    status TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, section_id),
                    FOREIGN KEY(project_id) REFERENCES longform_projects(project_id)
                );
                CREATE INDEX IF NOT EXISTS idx_longform_order ON longform_sections(project_id, ordinal);
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create_project(self, title: str, sections: Sequence[SectionSpec], *, project_id: str | None = None) -> str:
        if not title.strip():
            raise ValueError("title must not be blank")
        if not sections:
            raise ValueError("At least one section is required")
        ids = [s.section_id for s in sections]
        if any(not x.strip() for x in ids) or len(set(ids)) != len(ids):
            raise ValueError("Section ids must be non-empty and unique")
        pid = project_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        outline = [{"section_id": s.section_id, "title": s.title, "instructions": s.instructions,
                    "acceptance_criteria": list(s.acceptance_criteria)} for s in sections]
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT outline_json,title FROM longform_projects WHERE project_id=?", (pid,)).fetchone()
            encoded = json.dumps(outline, ensure_ascii=False, sort_keys=True)
            if existing:
                if existing["outline_json"] != encoded or existing["title"] != title:
                    raise ValueError("A project id cannot be reused with a different outline")
                return pid
            db.execute("INSERT INTO longform_projects VALUES (?, ?, ?, 'planned', ?, ?)", (pid, title, encoded, now, now))
            for ordinal, section in enumerate(sections):
                db.execute(
                    "INSERT INTO longform_sections VALUES (?, ?, ?, ?, ?, ?, '', '', 0, 'pending', ?)",
                    (pid, section.section_id, ordinal, section.title, section.instructions,
                     json.dumps(list(section.acceptance_criteria), ensure_ascii=False), now),
                )
        return pid

    async def run(
        self, project_id: str, *, generator: SectionGenerator,
        verifier: SectionVerifier | None = None, max_section_words: int = 8000,
        regenerate_failed: bool = True,
    ) -> LongFormResult:
        if max_section_words < 1:
            raise ValueError("max_section_words must be positive")
        project, rows = self._load(project_id)
        if not rows:
            raise ValueError(f"Unknown project: {project_id}")
        title = project["title"]
        completed: list[SectionResult] = []
        prior_summaries: list[str] = []
        try:
            self._set_project_status(project_id, "running")
            for row in rows:
                spec = SectionSpec(
                    section_id=row["section_id"], title=row["title"], instructions=row["instructions"],
                    acceptance_criteria=tuple(json.loads(row["criteria_json"])),
                )
                content = row["content"]
                reused = row["status"] == "completed" and bool(content)
                if not reused:
                    content = (await generator(title, spec, self._compact_context(prior_summaries), tuple(prior_summaries))).strip()
                    if not content:
                        raise ValueError(f"Generator returned empty content for section {spec.section_id!r}")
                    words = len(content.split())
                    if words > max_section_words:
                        raise ValueError(f"Section {spec.section_id!r} exceeded {max_section_words} words ({words})")
                    if verifier:
                        outcome = await verifier(spec, content)
                        passed, detail = outcome if isinstance(outcome, tuple) else (outcome, "")
                        if not passed and regenerate_failed:
                            retry_context = self._compact_context(prior_summaries + [f"Verification feedback for {spec.title}: {detail}"])
                            content = (await generator(title, spec, retry_context, tuple(prior_summaries))).strip()
                            if not content:
                                raise ValueError(f"Regeneration returned empty content for {spec.section_id!r}")
                            words = len(content.split())
                            if words > max_section_words:
                                raise ValueError(f"Regenerated section {spec.section_id!r} exceeded word limit")
                            second = await verifier(spec, content)
                            passed2, detail2 = second if isinstance(second, tuple) else (second, "")
                            if not passed2:
                                raise ValueError(f"Section {spec.section_id!r} failed verification: {detail2}")
                        elif not passed:
                            raise ValueError(f"Section {spec.section_id!r} failed verification: {detail}")
                    self._save_section(project_id, row["section_id"], content)
                words = len(content.split())
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                completed.append(SectionResult(spec, content, digest, words, reused))
                # The context is summaries rather than full previous sections to prevent context blowup.
                prior_summaries.append(f"{spec.title}: {self._summary(content)}")
            assembled = "\n\n".join(f"# {r.section.title}\n\n{r.content}" for r in completed)
            result = LongFormResult(
                project_id=project_id, title=title, sections=tuple(completed), content=assembled,
                sha256=hashlib.sha256(assembled.encode("utf-8")).hexdigest(), word_count=len(assembled.split()),
            )
            self._set_project_status(project_id, "completed")
            return result
        except BaseException:
            self._set_project_status(project_id, "interrupted")
            raise

    def _load(self, project_id: str):
        with self._connect() as db:
            project = db.execute("SELECT * FROM longform_projects WHERE project_id=?", (project_id,)).fetchone()
            rows = db.execute("SELECT * FROM longform_sections WHERE project_id=? ORDER BY ordinal", (project_id,)).fetchall()
        if project is None:
            raise ValueError(f"Unknown project: {project_id}")
        return project, rows

    def _save_section(self, project_id: str, section_id: str, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE longform_sections SET content=?,sha256=?,word_count=?,status='completed',updated_at=? WHERE project_id=? AND section_id=?",
                (content, digest, len(content.split()), now, project_id, section_id),
            )
            db.execute("UPDATE longform_projects SET updated_at=? WHERE project_id=?", (now, project_id))

    def _set_project_status(self, project_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("UPDATE longform_projects SET status=?,updated_at=? WHERE project_id=?", (status, now, project_id))

    @staticmethod
    def _summary(content: str, limit: int = 500) -> str:
        compact = " ".join(content.split())
        return compact[:limit] + ("…" if len(compact) > limit else "")

    @staticmethod
    def _compact_context(summaries: list[str]) -> str:
        return "\n".join(summaries[-24:])

    def get_status(self, project_id: str) -> dict:
        project, rows = self._load(project_id)
        return {
            "project_id": project_id, "title": project["title"], "status": project["status"],
            "sections": [{"section_id": r["section_id"], "title": r["title"], "status": r["status"],
                          "word_count": r["word_count"], "sha256": r["sha256"]} for r in rows],
        }
