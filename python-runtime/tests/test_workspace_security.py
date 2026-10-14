from __future__ import annotations

import socket

import pytest

from app.infra.ssrf import UnsafeURL, assert_public_url
from app.infra.workspace import RunWorkspace, safe_id
from app.services.core_adapters import Workspace
from app.tools.base import ToolExecutionError


def test_workspace_rejects_traversal_absolute_and_drive_paths(tmp_path):
    workspace = RunWorkspace('test-run', root=tmp_path / 'run', assets_root=tmp_path / 'assets')
    for value in ('', '../escape.txt', 'nested/../../escape.txt', '/etc/passwd', r'C:\\secret.txt'):
        with pytest.raises(ToolExecutionError):
            workspace.resolve(value)


def test_workspace_rejects_symlink_escape(tmp_path):
    workspace = RunWorkspace('test-run', root=tmp_path / 'run', assets_root=tmp_path / 'assets')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (workspace.root / 'escape').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ToolExecutionError):
        workspace.resolve('escape/payload.txt')


def test_new_path_is_unique_and_relative(tmp_path):
    workspace = RunWorkspace('test-run', root=tmp_path / 'run', assets_root=tmp_path / 'assets')
    first = workspace.new_path('reports/result.txt')
    first.write_text('first', encoding='utf-8')
    second = workspace.new_path('reports/result.txt')
    assert first != second
    assert workspace.relative(second) == 'reports/result_2.txt'


def test_safe_id_rejects_path_syntax():
    assert safe_id('project_123-abc') == 'project_123-abc'
    for value in ('../x', 'with space', '', 'a' * 65):
        with pytest.raises(ToolExecutionError):
            safe_id(value)


def test_ssrf_rejects_private_dns_result(monkeypatch):
    def fake_getaddrinfo(host, port, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', port))]
    monkeypatch.setattr(socket, 'getaddrinfo', fake_getaddrinfo)
    with pytest.raises(UnsafeURL):
        assert_public_url('https://example.com')


def test_ssrf_rejects_localhost_and_app_port():
    for url in ('http://localhost/', 'http://127.0.0.1/', 'http://169.254.169.254/'):
        with pytest.raises(UnsafeURL):
            assert_public_url(url)
    with pytest.raises(UnsafeURL):
        assert_public_url('https://example.com:8000/', app_port=8000)


def test_ssrf_rejects_non_http_and_url_credentials():
    for url in ('file:///etc/passwd', 'ftp://example.com', 'https://user:pass@example.com'):
        with pytest.raises(UnsafeURL):
            assert_public_url(url)



def test_runner_workspace_exposes_shared_asset_resolver(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    workspace = Workspace("asset-run")
    asset = workspace.asset("voices/default.onnx")
    assert asset == (tmp_path / "agentforge-data" / "assets" / "voices" / "default.onnx").resolve()
    with pytest.raises(ToolExecutionError):
        workspace.asset("../outside.txt")


def test_shared_asset_resolver_rejects_symlink_escape(tmp_path):
    workspace = RunWorkspace("asset-link-run", root=tmp_path / "run", assets_root=tmp_path / "assets")
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace.assets_root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ToolExecutionError):
        workspace.asset("escape/secret.txt")
