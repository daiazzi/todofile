from __future__ import annotations

from todofile.models import NO_PROJECT
from todofile.parser import parse_text


def test_simple_task():
    text = "## backend\n\n- [ ] (a4f9c): build parser\n"
    doc = parse_text(text)
    assert len(doc.projects) == 1
    p = doc.projects[0]
    assert p.name == "backend"
    assert len(p.tasks) == 1
    t = p.tasks[0]
    assert t.hash == "a4f9c"
    assert t.description == "build parser"
    assert t.tag is None
    assert t.done is False
    assert t.parent_hash is None


def test_task_with_tag():
    text = "## backend\n- [ ] api(a4f9c): build parser\n"
    doc = parse_text(text)
    t = doc.projects[0].tasks[0]
    assert t.tag == "api"
    assert t.description == "build parser"


def test_done_task():
    text = "## backend\n- [x] (a4f9c): done\n"
    t = parse_text(text).projects[0].tasks[0]
    assert t.done is True


def test_uppercase_x():
    text = "## backend\n- [X] (a4f9c): done\n"
    t = parse_text(text).projects[0].tasks[0]
    assert t.done is True


def test_subtask():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
        "  - [ ] (bbbbb): child\n"
    )
    doc = parse_text(text)
    parent = doc.tasks_by_hash["aaaaa"]
    child = doc.tasks_by_hash["bbbbb"]
    assert child.parent_hash == "aaaaa"
    assert doc.children_of("aaaaa") == [child]
    # Subtask is NOT in project.tasks
    assert len(doc.projects[0].tasks) == 1


def test_three_level_nesting():
    text = (
        "## p\n"
        "- [ ] (aaaaa): root\n"
        "  - [ ] (bbbbb): level2\n"
        "    - [ ] (ccccc): level3\n"
    )
    doc = parse_text(text)
    assert doc.tasks_by_hash["bbbbb"].parent_hash == "aaaaa"
    assert doc.tasks_by_hash["ccccc"].parent_hash == "bbbbb"
    assert doc.children_of("bbbbb") == [doc.tasks_by_hash["ccccc"]]
    assert not any("flattened" in w for w in doc.warnings)


def test_deep_nesting_flattened():
    text = (
        "## p\n"
        "- [ ] (aaaaa): root\n"
        "  - [ ] (bbbbb): level2\n"
        "    - [ ] (ccccc): level3\n"
        "      - [ ] (ddddd): level4\n"
    )
    doc = parse_text(text)
    assert doc.tasks_by_hash["ddddd"].parent_hash == "bbbbb"
    assert any("flattened" in w for w in doc.warnings)


def test_unstamped_task_gets_placeholder():
    text = "## p\n- [ ] api: build it\n"
    doc = parse_text(text)
    tasks = list(doc.tasks_by_hash.values())
    assert tasks[0].hash.startswith("__new")
    assert tasks[0].tag == "api"
    assert tasks[0].description == "build it"


def test_unstamped_no_tag():
    text = "## p\n- [ ] just a thing\n"
    doc = parse_text(text)
    t = list(doc.tasks_by_hash.values())[0]
    assert t.tag is None
    assert t.description == "just a thing"


def test_description_continuation():
    text = (
        "## p\n"
        "- [ ] (aaaaa): line one\n"
        "  line two\n"
        "  line three\n"
        "- [ ] (bbbbb): next task\n"
    )
    doc = parse_text(text)
    a = doc.tasks_by_hash["aaaaa"]
    assert "line two" in a.description
    assert "line three" in a.description


def test_description_with_sub_bullet():
    text = (
        "## p\n"
        "- [ ] (aaaaa): root\n"
        "  - a sub-bullet of the description\n"
        "  - another one\n"
        "- [ ] (bbbbb): next\n"
    )
    doc = parse_text(text)
    a = doc.tasks_by_hash["aaaaa"]
    assert "a sub-bullet" in a.description
    assert "another one" in a.description


def test_no_project_synthetic():
    text = "- [ ] (aaaaa): no header above\n"
    doc = parse_text(text)
    assert doc.projects[0].name == NO_PROJECT


def test_duplicate_h2_merges():
    text = (
        "## p\n"
        "- [ ] (aaaaa): one\n"
        "## p\n"
        "- [ ] (bbbbb): two\n"
    )
    doc = parse_text(text)
    assert len(doc.projects) == 1
    assert len(doc.projects[0].tasks) == 2


def test_duplicate_hash_warns():
    text = (
        "## p\n"
        "- [ ] (aaaaa): one\n"
        "- [ ] (aaaaa): again\n"
    )
    doc = parse_text(text)
    assert any("duplicate" in w for w in doc.warnings)
    assert len(doc.tasks_by_hash) == 1


def test_uppercase_hash_normalised():
    text = "## p\n- [ ] (A4F9C): cap\n"
    doc = parse_text(text)
    assert "a4f9c" in doc.tasks_by_hash
    assert any("lowercase" in w for w in doc.warnings)


def test_crlf_normalised():
    text = "## p\r\n- [ ] (aaaaa): x\r\n"
    doc = parse_text(text)
    assert doc.tasks_by_hash["aaaaa"].description == "x"


def test_empty_file():
    doc = parse_text("")
    assert doc.projects == []
    assert doc.warnings == []


def test_h1_ignored():
    text = "# Title\n\n## p\n- [ ] (aaaaa): x\n"
    doc = parse_text(text)
    assert doc.projects[0].name == "p"


def test_title_captured():
    text = "# My Project\n\n## p\n- [ ] (aaaaa): x\n"
    doc = parse_text(text)
    assert doc.title == "My Project"


def test_only_first_h1_is_title():
    text = "# First\n\n# Second\n\n## p\n"
    doc = parse_text(text)
    assert doc.title == "First"


def test_no_h1_no_title():
    text = "## p\n- [ ] (aaaaa): x\n"
    doc = parse_text(text)
    assert doc.title is None


def test_mixed_indent_tabs_spaces():
    text = (
        "## p\n"
        "- [ ] (aaaaa): root\n"
        "\t- [ ] (bbbbb): tab-indented child\n"
    )
    doc = parse_text(text)
    assert doc.tasks_by_hash["bbbbb"].parent_hash == "aaaaa"


def test_star_marker():
    text = "## p\n* [ ] (aaaaa): with asterisk\n"
    doc = parse_text(text)
    assert "aaaaa" in doc.tasks_by_hash


def test_existing_hashes_extraction():
    from todofile.parser import existing_hashes
    text = "- [ ] (a4f9c): x\n- [ ] foo(b3d8a): y\n"
    assert existing_hashes(text) == {"a4f9c", "b3d8a"}


def test_project_notes():
    text = (
        "## backend\n"
        "### Notes\n"
        "- (xabcde): Chose PostgreSQL.\n"
        "  More detail on the next line.\n"
        "- Idea: add caching.\n"
        "\n"
        "- [ ] (aaaaa): build parser\n"
    )
    doc = parse_text(text)
    p = doc.projects[0]
    assert p.name == "backend"
    assert len(p.notes) == 2
    assert p.notes[0].hash == "xabcde"
    assert "PostgreSQL" in p.notes[0].content
    assert "More detail" in p.notes[0].content
    assert "caching" in p.notes[1].content
    assert len(p.tasks) == 1


def test_notes_case_insensitive_heading():
    text = "## p\n### notes\n- one\n"
    doc = parse_text(text)
    assert len(doc.projects[0].notes) == 1


def test_notes_star_marker():
    text = "## p\n### Notes\n* first\n* second\n"
    doc = parse_text(text)
    assert [n.content for n in doc.projects[0].notes] == ["first", "second"]


def test_other_h3_ends_notes_section():
    text = (
        "## p\n"
        "### Notes\n"
        "- kept\n"
        "### Other\n"
        "- not a note\n"
        "- [ ] (aaaaa): task\n"
    )
    doc = parse_text(text)
    assert len(doc.projects[0].notes) == 1
    assert doc.projects[0].notes[0].content == "kept"


def test_notes_without_tasks():
    text = "## p\n### Notes\n- only notes here\n"
    doc = parse_text(text)
    assert len(doc.projects[0].notes) == 1
    assert doc.projects[0].tasks == []
