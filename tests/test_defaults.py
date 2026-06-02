from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from click.testing import CliRunner

from todofile.cli import cli
from todofile.parser import parse_text
from todofile.store import (
    ensure_sidecar,
    load_config,
    load_tasks_yaml,
    save_config,
    sidecar_dir,
    sync,
)


def test_sync_no_default_dates_on_new_task(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    sync(parse_text(p.read_text(), path=p), p)
    row = load_tasks_yaml(p)["a4f9c"]
    # default_duration is 0 → no dates assigned automatically
    assert row.start is None
    assert row.end is None
    assert row.created is not None


def test_sync_respects_configured_duration(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    cfg = load_config(p)
    cfg.default_duration = 5
    save_config(p, cfg)

    sync(parse_text(p.read_text(), path=p), p)
    row = load_tasks_yaml(p)["a4f9c"]
    today = date.today()
    assert row.start == today
    assert row.end == today + timedelta(days=4)


def test_sync_does_not_overwrite_existing_dates(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    sync(parse_text(p.read_text(), path=p), p)
    from todofile.store import set_dates
    set_dates(p, "a4f9c", date(2030, 1, 1), date(2030, 1, 5))

    sync(parse_text(p.read_text(), path=p), p)
    row = load_tasks_yaml(p)["a4f9c"]
    assert row.start == date(2030, 1, 1)
    assert row.end == date(2030, 1, 5)


def test_config_default_duration_flag(tmp_path: Path, monkeypatch):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n\n## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--default-duration", "7"])
    assert result.exit_code == 0, result.output
    cfg = load_config(p)
    assert cfg.default_duration == 7


def test_config_default_duration_zero_disables_dates(tmp_path: Path, monkeypatch):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n\n## p\n")
    ensure_sidecar(p)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--default-duration", "0"])
    assert result.exit_code == 0, result.output
    cfg = load_config(p)
    assert cfg.default_duration == 0


def test_sync_skips_default_dates_when_duration_zero(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    cfg = load_config(p)
    cfg.default_duration = 0
    save_config(p, cfg)

    sync(parse_text(p.read_text(), path=p), p)
    row = load_tasks_yaml(p)["a4f9c"]
    assert row.start is None
    assert row.end is None
    assert row.created is not None


def test_config_default_duration_rejects_negative(tmp_path: Path, monkeypatch):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n\n## p\n")
    ensure_sidecar(p)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--default-duration", "-1"])
    assert result.exit_code != 0
    assert "zero or a positive integer" in result.output


def test_default_duration_zero_persists_in_yaml(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n")
    ensure_sidecar(p)
    cfg = load_config(p)
    cfg.default_duration = 0
    save_config(p, cfg)

    cfg2 = load_config(p)
    assert cfg2.default_duration == 0


def test_config_help_when_no_args(tmp_path: Path, monkeypatch):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n\n## p\n")
    ensure_sidecar(p)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["config"])
    assert result.exit_code == 0
    assert "Inspect or modify" in result.output or "Usage" in result.output


def test_default_duration_persists_in_yaml(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n")
    ensure_sidecar(p)
    cfg = load_config(p)
    cfg.default_duration = 14
    save_config(p, cfg)

    cfg2 = load_config(p)
    assert cfg2.default_duration == 14


def test_auto_refresh_defaults_on(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n")
    ensure_sidecar(p)
    cfg = load_config(p)
    assert cfg.auto_refresh is True
