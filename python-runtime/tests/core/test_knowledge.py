from app.core.knowledge import KnowledgeIndex, extract_document


def _document(name: str, body: str):
    return extract_document(name, body.encode("utf-8"), media_type="text/plain")


def test_knowledge_index_uses_fts5_and_tracks_insert_delete(tmp_path):
    index = KnowledgeIndex(tmp_path / "knowledge.sqlite3")
    first = _document("architecture.md", "RunnerCore coordinates execution. FTS5 indexes searchable architecture notes.")
    second = _document("recipes.md", "A simple recipe uses flour, water, and yeast.")
    index.ingest(first)
    index.ingest(second)

    hits = index.search("RunnerCore execution")
    assert hits
    assert hits[0].chunk.source_name == "architecture.md"
    assert hits[0].lexical_score > 0

    assert index.remove_source(first.source_id) is True
    assert index.search("RunnerCore execution") == []


def test_knowledge_index_lexical_fallback_remains_available(tmp_path):
    index = KnowledgeIndex(tmp_path / "knowledge.sqlite3")
    index._fts5_available = False
    document = _document("notes.txt", "A distinctive phrase supports lexical fallback retrieval.")
    index.ingest(document)

    hits = index.search("distinctive phrase")
    assert hits
    assert hits[0].chunk.source_id == document.source_id


def test_knowledge_index_handles_query_syntax_as_plain_text(tmp_path):
    index = KnowledgeIndex(tmp_path / "knowledge.sqlite3")
    document = _document("code.py", "The parser handles unusual identifiers and safe search input.")
    index.ingest(document)

    # FTS operators and quotes are treated as query text, not executable MATCH syntax.
    hits = index.search('"safe" OR NEAR(parser, input)')
    assert isinstance(hits, list)
