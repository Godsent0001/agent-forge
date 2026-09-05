"""Asset & Cache shelf. All local filesystem + hashing logic — no external deps."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output


def _hash_inputs(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class CacheEngineTool(Tool):
    name = "cache_engine"
    description = "Hash tool inputs and skip regeneration when nothing changed."

    def __init__(self, cache_dir: str = "./cache"):
        self._root = Path(cache_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        action = params.get("action", "check")  # check | store

        if action == "check":
            key = _hash_inputs(params.get("inputs", {}))
            entry_path = self._root / f"{key}.json"
            if entry_path.exists():
                return to_json_output({"cache_hit": True, "key": key, **json.loads(entry_path.read_text())})
            return to_json_output({"cache_hit": False, "key": key})

        if action == "store":
            key = _hash_inputs(params.get("inputs", {}))
            output = params.get("output", {})
            (self._root / f"{key}.json").write_text(json.dumps(output))
            return to_json_output({"stored": True, "key": key})

        raise ToolExecutionError(f"Unknown action '{action}'. Use check or store.")


class DependencyEngineTool(Tool):
    name = "dependency_engine"
    description = "Track what needs regeneration when an upstream input changes."

    # A fixed dependency chain per the spec's dialogue-change example.
    # A real version would let this be authored per-project; kept fixed
    # here to match the concrete example from the spec directly.
    CHAIN = ["dialogue", "voice", "lip_sync", "captions", "timeline"]

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        changed = params.get("changed")
        if changed not in self.CHAIN:
            raise ToolExecutionError(f"Unknown changed stage '{changed}'. Chain: {' -> '.join(self.CHAIN)}")

        idx = self.CHAIN.index(changed)
        downstream = self.CHAIN[idx:]  # the changed stage itself, plus everything after it
        unaffected = self.CHAIN[:idx]

        return to_json_output({"needs_regeneration": downstream, "unaffected": unaffected})


class ProjectManagerTool(Tool):
    name = "project_manager"
    description = "Scaffold and manage a self-contained episode project folder."

    SUBDIRS = ["audio", "animation", "graphics", "assets", "previews", "renders"]

    def __init__(self, projects_root: str = "./projects"):
        self._root = Path(projects_root)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        episode_id = params.get("episode_id")
        action = params.get("action", "scaffold")
        if not episode_id:
            raise ToolExecutionError("project_manager requires 'episode_id'")

        episode_dir = self._root / episode_id

        if action == "scaffold":
            for sub in self.SUBDIRS:
                (episode_dir / sub).mkdir(parents=True, exist_ok=True)
            project_file = episode_dir / "project.json"
            if not project_file.exists():
                project_file.write_text(json.dumps({"episode_id": episode_id}, indent=2))
            return to_json_output({"episode_dir": str(episode_dir), "subdirs": self.SUBDIRS})

        if action == "status":
            if not episode_dir.exists():
                raise ToolExecutionError(f"No such episode project: {episode_id}")
            status = {sub: len(list((episode_dir / sub).iterdir())) for sub in self.SUBDIRS
                      if (episode_dir / sub).exists()}
            return to_json_output({"episode_dir": str(episode_dir), "file_counts": status})

        raise ToolExecutionError(f"Unknown action '{action}'. Use scaffold or status.")


class AssetCacheStoreTool(Tool):
    name = "asset_cache_store"
    description = "Store and look up reusable franchise-wide assets (rigs, fonts, music, SFX)."

    def __init__(self, store_dir: str = "./assets/shared"):
        self._root = Path(store_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        action = params.get("action", "list")

        if action == "list":
            category = params.get("category")
            base = self._root / category if category else self._root
            if not base.exists():
                return to_json_output({"assets": []})
            return to_json_output({"assets": [p.name for p in base.iterdir()]})

        if action == "put":
            src, category, name = params.get("src_path"), params.get("category", "misc"), params.get("name")
            if not src or not Path(src).exists():
                raise ToolExecutionError(f"asset_cache_store: src_path not found: {src}")
            dest_dir = self._root / category
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / (name or Path(src).name)
            shutil.copy2(src, dest)
            return to_json_output({"stored_at": str(dest)})

        raise ToolExecutionError(f"Unknown action '{action}'. Use list or put.")


class ProductionConfigTool(Tool):
    name = "production_config"
    description = "Centralize render/audio/caption/character default settings."

    DEFAULTS = {
        "video": {"width": 1080, "height": 1920, "fps": 30},
        "audio": {"sample_rate": 48000},
        "captions": {"max_words_per_line": 5},
        "characters": {"default_animation_intensity": 0.65},
    }

    def __init__(self, config_path: str = "./production_config.json"):
        self._path = Path(config_path)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        action = params.get("action", "get")

        if action == "get":
            if self._path.exists():
                return to_json_output(json.loads(self._path.read_text()))
            return to_json_output(self.DEFAULTS)

        if action == "set":
            overrides = params.get("config", {})
            current = json.loads(self._path.read_text()) if self._path.exists() else dict(self.DEFAULTS)
            for section, values in overrides.items():
                current.setdefault(section, {}).update(values)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(current, indent=2))
            return to_json_output(current)

        raise ToolExecutionError(f"Unknown action '{action}'. Use get or set.")
