from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from todofile.cli import cli
from todofile.parser import parse
from todofile.store import load_config, load_tasks_yaml, sidecar_dir


def test_init_creates_sidecar_and_stamps(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] api: needs stamp\n- [ ] (a4f9c): stamped\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--file", str(p)])
    assert result.exit_code == 0, result.output
    assert sidecar_dir(p).is_dir()
    doc = parse(p)
    assert all(not h.startswith("__new") for h in doc.tasks_by_hash)
    assert len(doc.tasks_by_hash) == 2


def test_init_creates_missing_file(tmp_path: Path):
    p = tmp_path / "fresh.md"
    assert not p.exists()
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--file", str(p)])
    assert result.exit_code == 0, result.output
    assert p.exists()
    text = p.read_text()
    assert "# fresh" in text
    assert "## Tasks" in text


def test_init_accepts_config_flags(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "init",
            "--file", str(p),
            "--light-mode",
            "--no-show-dates",
            "--text-size",
            "big",
            "--default-duration",
            "7",
            "--tag-col",
            "FEAT:blue,FIX:red",
        ],
    )
    assert result.exit_code == 0, result.output
    cfg = load_config(p)
    assert cfg.theme == "light"
    assert cfg.show_dates is False
    assert cfg.text_size == "big"
    assert cfg.default_duration == 7
    assert cfg.colors["FEAT"] == "#7aa2f7"
    assert cfg.colors["FIX"] == "#f7768e"


def test_init_errors_on_missing_parent(tmp_path: Path):
    p = tmp_path / "missing-dir" / "TODO.md"
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--file", str(p)])
    assert result.exit_code != 0
    assert "Parent directory does not exist" in result.output


def test_task_add_top_level(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): existing\n")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["add", "-f", str(p), "new task", "-t", "api"]
    )
    assert result.exit_code == 0, result.output
    doc = parse(p)
    assert len(doc.tasks_by_hash) == 2
    new_tasks = [t for t in doc.tasks_by_hash.values() if t.description == "new task"]
    assert len(new_tasks) == 1
    assert new_tasks[0].tag == "api"


def test_task_add_subtask(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): parent\n")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["add", "-f", str(p), "child", "-p", "a4f9c"]
    )
    assert result.exit_code == 0, result.output
    doc = parse(p)
    children = doc.children_of("a4f9c")
    assert len(children) == 1
    assert children[0].description == "child"


def test_task_add_unknown_parent(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["add", "-f", str(p), "y", "-p", "fffff"]
    )
    assert result.exit_code != 0
    assert "No task with hash 'fffff'" in result.output


def test_task_add_multiple_projects_requires_choice(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## a\n- [ ] (aaaaa): x\n## b\n- [ ] (bbbbb): y\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["add", "-f", str(p), "z"])
    assert result.exit_code != 0
    assert "--project" in result.output


def test_task_add_duration_with_start(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["add", "-f", str(p), "new", "-s", "2026-06-01", "--duration", "5"]
    )
    assert result.exit_code == 0, result.output
    data = load_tasks_yaml(p)
    # Find the new hash
    new_hash = next(h for h, m in data.items() if m.start is not None and m.start.isoformat() == "2026-06-01")
    assert data[new_hash].end.isoformat() == "2026-06-05"


def test_task_add_duration_alone_errors(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["add", "-f", str(p), "new", "--duration", "5"]
    )
    assert result.exit_code != 0
    assert "anchor" in result.output


def test_task_add_three_dates_errors(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "add", "-f", str(p), "new",
            "-s", "2026-06-01", "-e", "2026-06-10", "--duration", "5",
        ],
    )
    assert result.exit_code != 0
    assert "at most two" in result.output


def test_task_add_invalid_date(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["add", "-f", str(p), "new", "-s", "not-a-date"])
    assert result.exit_code != 0
    assert "Invalid date" in result.output


def test_task_remove(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): keep\n- [ ] (b3d8a): remove\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["remove", "b3d8a", "--file", str(p)])
    assert result.exit_code == 0, result.output
    doc = parse(p)
    assert "b3d8a" not in doc.tasks_by_hash
    assert "a4f9c" in doc.tasks_by_hash


def test_task_remove_unknown_hash(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): x\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["remove", "fffff", "--file", str(p)])
    assert result.exit_code != 0
    assert "No task with hash" in result.output


def test_annotate_requires_project_when_ambiguous(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## a\n- [ ] (aaaaa): x\n## b\n- [ ] (bbbbb): y\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["annotate", "hello", "--file", str(p)])
    assert result.exit_code != 0
    assert "--project" in result.output


def test_annotate_inserts_note_with_id(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## a\n- [ ] (aaaaa): x\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["annotate", "hello", "--file", str(p), "-P", "a"])
    assert result.exit_code == 0, result.output
    text = p.read_text()
    assert "### Notes" in text
    assert "hello" in text
    assert "(x" in text  # should have an x-prefixed note id


def test_remove_note_id(tmp_path: Path):
    p = tmp_path / "TODO.md"
    p.write_text("## p\n### Notes\n- (xabcde): first\n  cont\n- [ ] (aaaaa): task\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["remove", "xabcde", "--file", str(p)])
    assert result.exit_code == 0, result.output
    text = p.read_text()
    assert "xabcde" not in text
    assert "cont" not in text
    assert "(aaaaa)" in text


def test_help_format(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["help", "format"])
    assert result.exit_code == 0
    assert "TODO.md format" in result.output
