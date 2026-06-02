from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from todofile import daemon as daemon_mod
from todofile.cli import cli
from todofile.store import ensure_sidecar


def test_status_with_path(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    runner = CliRunner()
    result = runner.invoke(cli, ["status", "--file", str(p)])
    assert result.exit_code == 0, result.output
    assert str(p) in result.output
    assert "down" in result.output


def test_status_auto_resolve(tmp_path: Path, monkeypatch):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0, result.output
    assert str(p) in result.output
    assert "down" in result.output


def test_status_reports_up_when_daemon_running(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    pid, url = daemon_mod.start(p)
    try:
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--file", str(p)])
        assert result.exit_code == 0, result.output
        assert "up" in result.output
        assert str(pid) in result.output
        assert "127.0.0.1" in result.output
    finally:
        daemon_mod.stop(p)


def test_status_no_file(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code != 0
    assert "No TODO file" in result.output


def test_restart_replaces_running_daemon(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n\n## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    pid, _ = daemon_mod.start(p)
    try:
        runner = CliRunner()
        result = runner.invoke(cli, ["restart", "--file", str(p)])
        assert result.exit_code == 0, result.output
        new_pid, _ = daemon_mod.read_status(p)
        assert new_pid is not None
        assert new_pid != pid
    finally:
        daemon_mod.stop(p)
