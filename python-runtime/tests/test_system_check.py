from pathlib import Path

from app.routers.system import build_system_checks


def test_system_check_returns_actionable_named_results(tmp_path):
    checks = build_system_checks(tmp_path)
    by_name = {check.name: check for check in checks}
    expected = {
        "ffmpeg", "ffprobe", "piper", "python:matplotlib", "python:ddgs",
        "data-directory", "database", "disk-space", "provider-key:anthropic",
        "provider-key:openai", "provider-key:google",
    }
    assert expected <= by_name.keys()
    assert all(isinstance(item.ok, bool) for item in checks)
    assert all(item.detail for item in checks)
    assert all(item.fix for item in checks if not item.ok)
    assert Path(tmp_path).is_dir()
