from __future__ import annotations

from datetime import date
from pathlib import Path

from todofile.parser import parse_text
from todofile.store import (
    ensure_sidecar,
    load_config,
    load_tasks_yaml,
    save_tasks_yaml,
    set_dates,
    sidecar_dir,
    sync,
)
from todofile.models import TaskMetadata


def test_sidecar_naming(tmp_path: Path):
    p = tmp_path / "myTODO.md"
    assert sidecar_dir(p) == tmp_path / ".myTODO.md.dir"


def test_ensure_sidecar_creates_files(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    d = ensure_sidecar(p)
    assert d.is_dir()
    assert (d / "tasks.yaml").exists()
    assert (d / "config.yaml").exists()


def test_ensure_sidecar_idempotent(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    (sidecar_dir(p) / "tasks.yaml").write_text("tasks:\n  - hash: a4f9c\n")
    ensure_sidecar(p)
    # The pre-existing tasks.yaml is not overwritten
    content = (sidecar_dir(p) / "tasks.yaml").read_text()
    assert "a4f9c" in content


def test_save_load_roundtrip(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    from datetime import datetime

    data = {
        "a4f9c": TaskMetadata(
            hash="a4f9c",
            start=date(2026, 6, 1),
            end=date(2026, 6, 10),
            created=datetime(2026, 5, 27, 14, 0, 0),
        )
    }
    save_tasks_yaml(p, data)
    loaded = load_tasks_yaml(p)
    assert "a4f9c" in loaded
    assert loaded["a4f9c"].start == date(2026, 6, 1)
    assert loaded["a4f9c"].end == date(2026, 6, 10)


def test_sync_adds_new_yaml_entries(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    doc = parse_text(p.read_text(), path=p)
    sync(doc, p)
    loaded = load_tasks_yaml(p)
    assert "a4f9c" in loaded
    assert loaded["a4f9c"].created is not None


def test_sync_drops_missing(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    sync(parse_text(p.read_text(), path=p), p)

    p.write_text("## p\n")
    sync(parse_text(p.read_text(), path=p), p)
    loaded = load_tasks_yaml(p)
    assert "a4f9c" not in loaded


def test_sync_sets_completed_on_done(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    sync(parse_text(p.read_text(), path=p), p)

    p.write_text("## p\n- [x] (a4f9c): x\n")
    sync(parse_text(p.read_text(), path=p), p)
    loaded = load_tasks_yaml(p)
    assert loaded["a4f9c"].completed is not None


def test_sync_clears_completed_on_undone(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [x] (a4f9c): x\n")
    ensure_sidecar(p)
    sync(parse_text(p.read_text(), path=p), p)
    assert load_tasks_yaml(p)["a4f9c"].completed is not None

    p.write_text("## p\n- [ ] (a4f9c): x\n")
    sync(parse_text(p.read_text(), path=p), p)
    assert load_tasks_yaml(p)["a4f9c"].completed is None


def test_set_dates(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    ensure_sidecar(p)
    sync(parse_text(p.read_text(), path=p), p)
    meta = set_dates(p, "a4f9c", date(2026, 6, 1), date(2026, 6, 10))
    assert meta.start == date(2026, 6, 1)
    loaded = load_tasks_yaml(p)
    assert loaded["a4f9c"].start == date(2026, 6, 1)
    assert loaded["a4f9c"].end == date(2026, 6, 10)


def test_load_config_defaults(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    cfg = load_config(p)
    assert cfg.port is None


def test_load_config_with_port(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    (sidecar_dir(p) / "config.yaml").write_text("port: 8421\n")
    cfg = load_config(p)
    assert cfg.port == 8421


def test_load_config_colors(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    (sidecar_dir(p) / "config.yaml").write_text(
        "colors:\n  default: '#000000'\n  api: '#9ece6a'\n"
    )
    cfg = load_config(p)
    assert cfg.colors["default"] == "#000000"
    assert cfg.colors["api"] == "#9ece6a"


def test_load_config_theme(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    (sidecar_dir(p) / "config.yaml").write_text("theme: light\n")
    assert load_config(p).theme == "light"


def test_load_config_invalid_theme_falls_back(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    (sidecar_dir(p) / "config.yaml").write_text("theme: rainbow\n")
    assert load_config(p).theme == "light"


def test_load_config_panel_flags_defaults(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    cfg = load_config(p)
    assert cfg.show_gantt is False
    assert cfg.show_calendar is False
    assert cfg.show_weekends is False


def test_load_config_panel_flags_true(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    (sidecar_dir(p) / "config.yaml").write_text(
        "show_gantt: true\nshow_calendar: true\nshow_weekends: true\n"
    )
    cfg = load_config(p)
    assert cfg.show_gantt is True
    assert cfg.show_calendar is True
    assert cfg.show_weekends is True


def test_load_config_panel_flags_invalid_fall_back(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    (sidecar_dir(p) / "config.yaml").write_text(
        "show_gantt: nope\nshow_calendar: 5\nshow_weekends: hi\n"
    )
    cfg = load_config(p)
    assert cfg.show_gantt is False
    assert cfg.show_calendar is False
    assert cfg.show_weekends is False


def test_save_config_roundtrips_panel_flags(tmp_path: Path):
    from todofile.store import save_config

    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    cfg = load_config(p)
    cfg.show_gantt = True
    cfg.show_calendar = True
    cfg.show_weekends = True
    save_config(p, cfg)
    cfg2 = load_config(p)
    assert cfg2.show_gantt is True
    assert cfg2.show_calendar is True
    assert cfg2.show_weekends is True


def test_load_config_ignores_legacy_show_panel(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    (sidecar_dir(p) / "config.yaml").write_text("show_panel: false\n")
    cfg = load_config(p)
    # Legacy key is dropped silently in dev stage; new flags use their defaults.
    assert not hasattr(cfg, "show_panel")
    assert cfg.show_gantt is False
    assert cfg.show_calendar is False


def test_ensure_sidecar_copies_agent_md(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("# x\n")
    ensure_sidecar(p)
    agent = sidecar_dir(p) / "agent.md"
    assert agent.exists()
    assert "Agent instructions" in agent.read_text()
