import pytest
from app.tools.web_search import WebSearchTool
from app.tools.browser import BrowserTool
from app.tools.python_project import PythonProjectTool
from app.tools.python_exec import PythonExecTool
from app.infra.attachment_storage import copy_clean_attachment_to_workspace
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path
import tempfile

@pytest.mark.asyncio
async def test_web_search_flexible_input():
    mock_backend = AsyncMock(return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Sample"}])
    tool = WebSearchTool(search_fn=mock_backend)

    res1 = await tool.execute('{"query": "hello world"}', context=None)
    assert "Test" in res1
    mock_backend.assert_called_with("hello world")

    res2 = await tool.execute({"search_term": "python test"}, context=None)
    assert "Test" in res2
    mock_backend.assert_called_with("python test")

@pytest.mark.asyncio
async def test_browser_flexible_input():
    mock_http = AsyncMock()
    mock_http.execute.return_value = "HTTP/1.1 200 OK\nBody:\n<html><title>Page Title</title><body>Hello Page</body></html>"
    tool = BrowserTool(http_tool=mock_http)

    res = await tool.execute('{"url": "https://example.com"}', context=None)
    assert "Title: Page Title" in res
    assert "Hello Page" in res

@pytest.mark.asyncio
async def test_python_exec_flexible_input():
    tool = PythonExecTool()
    ctx = MagicMock()
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx.workspace.root = Path(tmpdir)
        res = await tool.execute('{"code": "print(123 + 456)"}', context=ctx)
        assert "579" in res

@pytest.mark.asyncio
async def test_python_project_auto_ensure():
    tool = PythonProjectTool()
    ctx = MagicMock()
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx.workspace.root = Path(tmpdir)
        ctx.workspace.resolve.side_effect = lambda p: Path(tmpdir) / p
        args = tool.Input(action="execute", input="print('auto initialized')")
        res = await tool.run(args, ctx)
        assert res.ok
        assert "auto initialized" in res.content
