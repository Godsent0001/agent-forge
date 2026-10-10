import pytest
from pathlib import Path
import tempfile
from app.core.lessons import InMemoryLessonStore, format_lessons_block, reflect_on_signal
from app.core.tools.plan import PlanTool, PlanInput, PlanItemSpec
from app.core.tools.summarize import SummarizeTool, SummarizeInput
from app.core.tools.doc_search import DocSearchTool, DocSearchInput
from app.core.tools.analyze_image import AnalyzeImageTool, AnalyzeImageInput


class DummyWorkspace:
    def __init__(self, root: Path):
        self.root = root

    def resolve(self, rel: str) -> Path:
        return self.root / rel

    def relative(self, p: Path) -> str:
        return str(p.relative_to(self.root))


class DummyCtx:
    def __init__(self, root: Path):
        self.workspace = DummyWorkspace(root)


@pytest.mark.asyncio
async def test_plan_tool():
    tool = PlanTool()
    ctx = DummyCtx(Path("/tmp"))
    inp = PlanInput(items=[
        PlanItemSpec(text="Step 1", status="done"),
        PlanItemSpec(text="Step 2", status="doing"),
    ])
    res = await tool.run(inp, ctx)
    assert res.ok is True
    assert "[done] Step 1" in res.content
    assert res.data["plan"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_summarize_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        file_p = root / "sample.txt"
        file_p.write_text("Hello world! " * 100, encoding="utf-8")

        tool = SummarizeTool()
        ctx = DummyCtx(root)
        res = await tool.run(SummarizeInput(source="sample.txt"), ctx)
        assert res.ok is True
        assert "Summary of sample.txt" in res.content


@pytest.mark.asyncio
async def test_doc_search_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        file_p = root / "code.py"
        file_p.write_text("def fibonacci(n):\n    return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)\n", encoding="utf-8")

        tool = DocSearchTool()
        ctx = DummyCtx(root)
        res = await tool.run(DocSearchInput(source="code.py", query="fibonacci"), ctx)
        assert res.ok is True
        assert "code.py:1" in res.content


@pytest.mark.asyncio
async def test_lessons_system():
    store = InMemoryLessonStore()
    await reflect_on_signal("agent_1", "exec_1", "Tool crashed", "Used fallback parameter", store)

    block = await format_lessons_block(store, "agent_1")
    assert "inspect the error" in block
    assert "validate inputs before retrying" in block
    # Durable lessons should generalize the failure without retaining raw details.
    assert "Tool crashed" not in block
