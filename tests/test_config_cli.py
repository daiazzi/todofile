from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from todofile.cli import cli
from todofile.store import ensure_sidecar, load_config, sidecar_dir


@pytest.fixture
def init_todo(tmp_path: Path) -> Path:
    p = tmp_path / "TODO.md"
    p.write_text("# Sample\n\n## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    return p


# --- theme -------------------------------------------------------------------


def test_config_dark_mode(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--dark-mode"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).theme == "dark"


def test_config_light_mode(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--light-mode"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).theme == "light"


def test_config_mode_mutually_exclusive(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--dark-mode", "--light-mode"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


# --- tag colours -------------------------------------------------------------


def test_config_tag_col_palette_name(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--tag-col", "api:green"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).colors["api"] == "#9ece6a"


def test_config_tag_col_hex(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--tag-col", "db:#abcdef"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).colors["db"] == "#abcdef"


def test_config_tag_col_repeatable(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "--tag-col", "api:green", "--tag-col", "db:red"],
    )
    assert result.exit_code == 0, result.output
    cfg = load_config(init_todo)
    assert cfg.colors["api"] == "#9ece6a"
    assert cfg.colors["db"] == "#f7768e"


def test_config_tag_col_comma_separated(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--tag-col", "api:green,db:red"])
    assert result.exit_code == 0, result.output
    cfg = load_config(init_todo)
    assert cfg.colors["api"] == "#9ece6a"
    assert cfg.colors["db"] == "#f7768e"


def test_config_tag_col_invalid_color(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--tag-col", "api:not-a-color"])
    assert result.exit_code != 0
    assert "Invalid colour" in result.output


def test_config_tag_col_missing_colon(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--tag-col", "api-green"])
    assert result.exit_code != 0
    assert "missing ':'" in result.output


def test_config_list_colors():
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--list-colors"])
    assert result.exit_code == 0, result.output
    for name in ("red", "green", "blue", "purple"):
        assert name in result.output


# --- show_dates --------------------------------------------------------------


def test_config_show_dates_off(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--no-show-dates"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).show_dates is False


def test_config_show_dates_on(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    # Flip to false first, then back to true
    cfg = load_config(init_todo)
    cfg.show_dates = False
    from todofile.store import save_config
    save_config(init_todo, cfg)

    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--show-dates"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).show_dates is True


# --- show_gantt / show_calendar / show_weekends -------------------------------


def test_config_show_gantt(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--show-gantt"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).show_gantt is True

    result = runner.invoke(cli, ["config", "--no-show-gantt"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).show_gantt is False


def test_config_show_calendar(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--show-calendar"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).show_calendar is True


def test_config_show_weekends(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--show-weekends"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).show_weekends is True


def test_init_panel_flags(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "--show-gantt", "--show-calendar", "--show-weekends"],
    )
    assert result.exit_code == 0, result.output
    cfg = load_config(tmp_path / "TODO.md")
    assert cfg.show_gantt is True
    assert cfg.show_calendar is True
    assert cfg.show_weekends is True


# --- text_size ---------------------------------------------------------------


def test_config_text_size(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--text-size", "big"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).text_size == "big"


def test_config_text_size_invalid(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--text-size", "huge"])
    assert result.exit_code != 0


# --- auto_refresh -------------------------------------------------------------


def test_config_auto_refresh_off(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--no-auto-refresh"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).auto_refresh is False


def test_config_auto_refresh_on(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    # Flip to false first, then back to true
    cfg = load_config(init_todo)
    cfg.auto_refresh = False
    from todofile.store import save_config
    save_config(init_todo, cfg)

    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--auto-refresh"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).auto_refresh is True


# --- combined ----------------------------------------------------------------


def test_config_multiple_flags_in_one_call(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "config",
            "--dark-mode",
            "--tag-col", "api:green",
            "--no-show-dates",
            "--default-duration", "5",
            "--text-size", "small",
        ],
    )
    assert result.exit_code == 0, result.output
    cfg = load_config(init_todo)
    assert cfg.theme == "dark"
    assert cfg.colors["api"] == "#9ece6a"
    assert cfg.show_dates is False
    assert cfg.default_duration == 5
    assert cfg.text_size == "small"


def test_config_help_when_no_flags(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config"])
    assert result.exit_code == 0
    assert "Usage" in result.output or "Inspect" in result.output


# --- auto-resolution ---------------------------------------------------------


def test_auto_resolve_uses_initialized_file_in_cwd(init_todo: Path, monkeypatch):
    monkeypatch.chdir(init_todo.parent)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--light-mode"])
    assert result.exit_code == 0, result.output
    assert load_config(init_todo).theme == "light"


def test_auto_resolve_errors_when_no_file(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--dark-mode"])
    assert result.exit_code != 0
    assert "No TODO file found" in result.output


def test_auto_resolve_errors_when_ambiguous(tmp_path: Path, monkeypatch):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("# a\n")
    b.write_text("# b\n")
    ensure_sidecar(a)
    ensure_sidecar(b)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--dark-mode"])
    assert result.exit_code != 0
    assert "Multiple initialized" in result.output


def test_auto_resolve_falls_back_to_TODO_md(tmp_path: Path, monkeypatch):
    p = tmp_path / "TODO.md"
    p.write_text("# t\n\n## p\n- [ ] (a4f9c): x\n")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--dark-mode"])
    assert result.exit_code == 0, result.output
    assert sidecar_dir(p).is_dir()


def test_init_defaults_to_TODO_md_in_cwd(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "TODO.md").exists()


def test_serve_file_option_works():
    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--file", "/no/such/file/exists.md"])
    assert result.exit_code != 0
    assert "File not found" in result.output
