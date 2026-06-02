from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from todofile.parser import parse
from todofile.server import build_app
from todofile.store import ensure_sidecar, load_tasks_yaml
from todofile.writer import set_done


# --- writer.set_done ---------------------------------------------------------


def test_set_done_marks_done():
    text = "## p\n- [ ] (a4f9c): x\n"
    new_text = set_done(text, "a4f9c", True)
    assert "- [x] (a4f9c): x" in new_text


def test_set_done_unmarks():
    text = "## p\n- [x] (a4f9c): x\n"
    new_text = set_done(text, "a4f9c", False)
    assert "- [ ] (a4f9c): x" in new_text


def test_set_done_with_tag_preserved():
    text = "## p\n- [ ] api(a4f9c): build\n"
    new_text = set_done(text, "a4f9c", True)
    assert "- [x] api(a4f9c): build" in new_text


def test_set_done_unknown_hash_raises():
    with pytest.raises(KeyError):
        set_done("## p\n- [ ] (a4f9c): x\n", "fffff", True)


def test_set_done_sub_subtask():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
        "  - [ ] (bbbbb): child\n"
        "    - [ ] (ccccc): grandchild\n"
    )
    new_text = set_done(text, "ccccc", True)
    assert "- [x] (ccccc):" in new_text or "- [X] (ccccc):" in new_text


# --- /api/tasks/{hash}/done ---------------------------------------------------


@pytest.fixture
def todo_with_tasks(tmp_path: Path) -> Path:
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): one\n- [x] (b3d8a): two\n")
    ensure_sidecar(p)
    return p


def test_post_done_marks_complete(todo_with_tasks: Path):
    client = TestClient(build_app(todo_with_tasks))
    r = client.post("/api/tasks/a4f9c/done", json={"done": True})
    assert r.status_code == 200
    doc = parse(todo_with_tasks)
    assert doc.tasks_by_hash["a4f9c"].done is True
    # tasks.yaml should now have a `completed` timestamp
    assert load_tasks_yaml(todo_with_tasks)["a4f9c"].completed is not None


def test_post_done_unmarks_complete(todo_with_tasks: Path):
    client = TestClient(build_app(todo_with_tasks))
    r = client.post("/api/tasks/b3d8a/done", json={"done": False})
    assert r.status_code == 200
    doc = parse(todo_with_tasks)
    assert doc.tasks_by_hash["b3d8a"].done is False
    assert load_tasks_yaml(todo_with_tasks)["b3d8a"].completed is None


def test_post_done_unknown_hash(todo_with_tasks: Path):
    client = TestClient(build_app(todo_with_tasks))
    r = client.post("/api/tasks/fffff/done", json={"done": True})
    assert r.status_code == 404


def test_post_done_invalid_body(todo_with_tasks: Path):
    client = TestClient(build_app(todo_with_tasks))
    r = client.post("/api/tasks/a4f9c/done", json={"done": "yes"})
    assert r.status_code == 400


def test_post_done_returns_full_state(todo_with_tasks: Path):
    client = TestClient(build_app(todo_with_tasks))
    r = client.post("/api/tasks/a4f9c/done", json={"done": True})
    data = r.json()
    assert "projects" in data
    assert "title" in data
    # the changed task is reflected in the returned state
    a = next(t for p in data["projects"] for t in p["tasks"] if t["hash"] == "a4f9c")
    assert a["done"] is True
