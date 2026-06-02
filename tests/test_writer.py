from __future__ import annotations

from todofile.parser import existing_hashes, existing_note_ids, parse_text
from todofile.writer import (
    ensure_blank_line_after_headings,
    insert_task,
    remove_note,
    remove_task,
    set_description,
    set_note_content,
    stamp_hashes,
    stamp_note_hashes,
)


def test_stamp_hashes_adds_to_unstamped():
    text = (
        "## p\n"
        "- [ ] (a4f9c): already stamped\n"
        "- [ ] api: needs hash\n"
        "- [ ] no tag here\n"
    )
    existing = existing_hashes(text)
    new_text, stamped = stamp_hashes(text, existing)
    assert len(stamped) == 2
    # Existing hash should still be there once
    assert new_text.count("(a4f9c)") == 1
    # The two new hashes appear in the text
    for line_no, h in stamped.items():
        assert f"({h})" in new_text


def test_stamp_preserves_tag():
    text = "## p\n- [ ] api: build it\n"
    existing = set()
    new_text, stamped = stamp_hashes(text, existing)
    h = list(stamped.values())[0]
    assert f"- [ ] api({h}): build it" in new_text


def test_stamp_no_tag_format():
    text = "## p\n- [ ] just text\n"
    existing = set()
    new_text, stamped = stamp_hashes(text, existing)
    h = list(stamped.values())[0]
    assert f"- [ ] ({h}): just text" in new_text


def test_stamp_then_parse_roundtrip():
    text = "## p\n- [ ] api: thing\n- [ ] (a4f9c): other\n"
    existing = existing_hashes(text)
    new_text, _ = stamp_hashes(text, existing)
    doc = parse_text(new_text)
    assert len(doc.tasks_by_hash) == 2
    assert "a4f9c" in doc.tasks_by_hash
    assert all(not h.startswith("__new") for h in doc.tasks_by_hash)


def test_insert_top_level():
    text = (
        "## backend\n"
        "- [ ] (aaaaa): existing\n"
    )
    new_text = insert_task(
        text,
        project="backend",
        parent_hash=None,
        tag=None,
        description="new task",
        hash="bbbbb",
    )
    assert "(bbbbb): new task" in new_text
    doc = parse_text(new_text)
    assert len(doc.projects[0].tasks) == 2


def test_insert_top_level_before_notes_section():
    text = (
        "## backend\n"
        "- [ ] (aaaaa): existing\n"
        "\n"
        "### Notes\n"
        "- note one\n"
    )
    new_text = insert_task(
        text,
        project="backend",
        parent_hash=None,
        tag=None,
        description="new task",
        hash="bbbbb",
    )
    lines = new_text.splitlines()
    idx_task = next(i for i, ln in enumerate(lines) if "(bbbbb): new task" in ln)
    idx_notes = next(i for i, ln in enumerate(lines) if ln.strip().lower().startswith("### notes"))
    assert idx_task < idx_notes


def test_insert_subtask_indent():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
    )
    new_text = insert_task(
        text,
        project="p",
        parent_hash="aaaaa",
        tag="t",
        description="child",
        hash="bbbbb",
    )
    doc = parse_text(new_text)
    assert doc.tasks_by_hash["bbbbb"].parent_hash == "aaaaa"


def test_insert_subtask_after_existing_subtasks():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
        "  - [ ] (bbbbb): existing child\n"
    )
    new_text = insert_task(
        text,
        project="p",
        parent_hash="aaaaa",
        tag=None,
        description="another",
        hash="ccccc",
    )
    doc = parse_text(new_text)
    assert doc.tasks_by_hash["ccccc"].parent_hash == "aaaaa"
    assert len(doc.children_of("aaaaa")) == 2


def test_insert_sub_subtask():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
        "  - [ ] (bbbbb): child\n"
    )
    new_text = insert_task(
        text,
        project="p",
        parent_hash="bbbbb",
        tag=None,
        description="grandchild",
        hash="ccccc",
    )
    doc = parse_text(new_text)
    assert doc.tasks_by_hash["ccccc"].parent_hash == "bbbbb"
    assert len(doc.children_of("bbbbb")) == 1


def test_remove_sub_subtask():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
        "  - [ ] (bbbbb): child\n"
        "    - [ ] (ccccc): grandchild\n"
    )
    new_text = remove_task(text, "ccccc")
    doc = parse_text(new_text)
    assert "ccccc" not in doc.tasks_by_hash
    assert "bbbbb" in doc.tasks_by_hash


def test_insert_creates_missing_project():
    text = "## one\n- [ ] (aaaaa): a\n"
    new_text = insert_task(
        text,
        project="two",
        parent_hash=None,
        tag=None,
        description="b",
        hash="bbbbb",
    )
    doc = parse_text(new_text)
    names = [p.name for p in doc.projects]
    assert "two" in names


def test_remove_leaf():
    text = (
        "## p\n"
        "- [ ] (aaaaa): keep\n"
        "- [ ] (bbbbb): remove\n"
    )
    new_text = remove_task(text, "bbbbb")
    doc = parse_text(new_text)
    assert "bbbbb" not in doc.tasks_by_hash
    assert "aaaaa" in doc.tasks_by_hash


def test_remove_parent_removes_subtree():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
        "  - [ ] (bbbbb): child\n"
        "  description line\n"
        "- [ ] (ccccc): sibling\n"
    )
    new_text = remove_task(text, "aaaaa")
    doc = parse_text(new_text)
    assert "aaaaa" not in doc.tasks_by_hash
    assert "bbbbb" not in doc.tasks_by_hash
    assert "ccccc" in doc.tasks_by_hash


def test_remove_unknown_hash_raises():
    import pytest
    text = "## p\n- [ ] (aaaaa): x\n"
    with pytest.raises(KeyError):
        remove_task(text, "fffff")


def test_stamp_note_hashes_adds_ids_under_notes_only():
    text = (
        "## p\n"
        "### Notes\n"
        "- first\n"
        "  more\n"
        "- (xabcde): already\n"
        "\n"
        "- [ ] (aaaaa): task\n"
        "### Notes\n"
        "- second\n"
    )
    existing = existing_note_ids(text)
    new_text, stamped = stamp_note_hashes(text, existing)
    assert "(xabcde): already" in new_text
    assert len(stamped) == 2
    for _, note_id in stamped.items():
        assert f"({note_id}):" in new_text


def test_remove_note_removes_entire_block():
    text = (
        "## p\n"
        "### Notes\n"
        "- (xabcde): first\n"
        "  cont\n"
        "- second\n"
        "- [ ] (aaaaa): task\n"
    )
    new_text = remove_note(text, "xabcde")
    assert "xabcde" not in new_text
    assert "cont" not in new_text
    assert "- second" in new_text


def test_set_description_replaces_inline_and_continuation_only():
    text = (
        "## p\n"
        "- [ ] api(aaaaa): line one\n"
        "  line two\n"
        "  - a sub-bullet of the description\n"
        "  another line\n"
        "  - [ ] (bbbbb): child\n"
        "    child desc\n"
        "- [ ] (ccccc): sibling\n"
    )
    new_text = set_description(text, "aaaaa", "new first\nnew second\n")
    doc = parse_text(new_text)
    assert doc.tasks_by_hash["aaaaa"].description == "new first\nnew second"
    # Subtask preserved
    assert "bbbbb" in doc.tasks_by_hash
    assert doc.tasks_by_hash["bbbbb"].parent_hash == "aaaaa"
    # Sibling preserved
    assert "ccccc" in doc.tasks_by_hash


def test_set_description_empty_allowed():
    text = "## p\n- [ ] (aaaaa): something\n  more\n"
    new_text = set_description(text, "aaaaa", "")
    doc = parse_text(new_text)
    assert doc.tasks_by_hash["aaaaa"].description == ""


def test_set_note_content_replaces_note_block_only():
    text = (
        "## p\n"
        "### Notes\n"
        "- (xabcde): first\n"
        "  cont\n"
        "- (x99999): second\n"
        "\n"
        "- [ ] (aaaaa): task\n"
    )
    new_text = set_note_content(text, "xabcde", "updated\nmore\n")
    assert "(xabcde): updated" in new_text
    assert "more" in new_text
    # Old continuation removed
    assert "cont" not in new_text
    # Other note preserved
    assert "(x99999): second" in new_text
    # Task preserved
    assert "(aaaaa): task" in new_text


def test_ensure_blank_line_after_headings_inserts_missing_blank():
    text = "# Title\n## p\n- [ ] (aaaaa): x\n### Notes\n- (xabcde): note\n"
    fixed = ensure_blank_line_after_headings(text)
    lines = fixed.splitlines()
    assert lines[1] == ""  # after H1
    # After H2 "## p" should be blank
    idx_h2 = lines.index("## p")
    assert lines[idx_h2 + 1] == ""
    idx_h3 = lines.index("### Notes")
    assert lines[idx_h3 + 1] == ""
