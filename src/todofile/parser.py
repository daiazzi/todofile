from __future__ import annotations

import re
from pathlib import Path

from .models import NO_PROJECT, Note, ParsedDocument, Project, Task


_BULLET_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*])\s+\[(?P<check>[ xX])\]\s*(?P<body>.*)$")
_NOTE_BULLET_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<marker>[-*])\s+(?!\[(?: |x|X)\])(?P<body>.*)$"
)
_NOTE_ID_PREFIX_RE = re.compile(r"^\((?P<hash>x[0-9a-fA-F]{5})\)\s*:\s*(?P<rest>.*)$")
_BODY_STAMPED_RE = re.compile(
    r"^(?:(?P<tag>[A-Za-z0-9_\-]+))?\((?P<hash>[0-9a-fA-F]{5})\)\s*:\s*(?P<desc>.*)$"
)
_BODY_FALLBACK_TAG_RE = re.compile(r"^(?P<tag>[A-Za-z0-9_\-]+):\s*(?P<desc>.*)$")
_HASH_PATTERN = re.compile(r"\(([0-9a-fA-F]{5})\)")
_NOTE_ID_PATTERN = re.compile(r"\((x[0-9a-fA-F]{5})\)")


def _indent_width(s: str) -> int:
    w = 0
    for ch in s:
        if ch == " ":
            w += 1
        elif ch == "\t":
            w += 4
        else:
            break
    return w


def _parse_bullet_body(body: str, line_no: int, warnings: list[str]):
    """Return (tag, hash_or_None, description). hash is normalised to lowercase."""
    body = body.strip()
    m = _BODY_STAMPED_RE.match(body)
    if m:
        tag = m.group("tag")
        h = m.group("hash")
        if any(c.isupper() for c in h):
            warnings.append(f"line {line_no}: hash '{h}' normalised to lowercase")
            h = h.lower()
        return tag, h, m.group("desc").strip()
    # unstamped — try fallback tag
    m2 = _BODY_FALLBACK_TAG_RE.match(body)
    if m2:
        return m2.group("tag"), None, m2.group("desc").strip()
    return None, None, body


def _common_leading_ws(lines: list[str]) -> int:
    """Minimum leading whitespace among non-blank lines."""
    widths: list[int] = []
    for ln in lines:
        if ln.strip():
            widths.append(len(ln) - len(ln.lstrip(" \t")))
    return min(widths) if widths else 0


def parse_text(text: str, path: Path | None = None) -> ParsedDocument:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    projects: dict[str, Project] = {}
    project_order: list[str] = []
    current_project: Project | None = None

    tasks_by_hash: dict[str, Task] = {}
    children: dict[str, list[Task]] = {}
    warnings: list[str] = []
    title: str | None = None

    # Nesting stack: list of (indent, task) at each level — level-1 (top),
    # level-2 (subtask), level-3 (sub-subtask).
    stack: list[tuple[int, Task]] = []

    pending_task: Task | None = None
    pending_lines: list[str] = []

    in_notes_section = False
    pending_note_lines: list[str] | None = None
    pending_note_indent: int | None = None

    placeholder_count = 0

    def flush_note() -> None:
        nonlocal pending_note_lines, pending_note_indent
        if pending_note_lines is None or current_project is None:
            pending_note_lines = None
            pending_note_indent = None
            return
        while pending_note_lines and not pending_note_lines[-1].strip():
            pending_note_lines.pop()
        if pending_note_lines:
            note_hash: str | None = None
            if pending_note_lines:
                m_id = _NOTE_ID_PREFIX_RE.match(pending_note_lines[0].strip())
                if m_id:
                    note_hash = m_id.group("hash").lower()
                    pending_note_lines[0] = m_id.group("rest")
            common = _common_leading_ws([ln for ln in pending_note_lines if ln.strip()])
            stripped = [ln[common:] if len(ln) >= common else ln for ln in pending_note_lines]
            content = "\n".join(stripped).strip()
            if content:
                current_project.notes.append(Note(hash=note_hash, content=content))
        pending_note_lines = None
        pending_note_indent = None

    def flush_description() -> None:
        nonlocal pending_task, pending_lines
        if pending_task is None:
            pending_lines = []
            return
        while pending_lines and not pending_lines[-1].strip():
            pending_lines.pop()
        if pending_lines:
            common = _common_leading_ws(pending_lines)
            stripped = [ln[common:] if len(ln) >= common else ln for ln in pending_lines]
            cont = "\n".join(stripped)
            if pending_task.description:
                pending_task.description = pending_task.description + "\n" + cont
            else:
                pending_task.description = cont
        pending_task = None
        pending_lines = []

    def get_or_create_project(name: str) -> Project:
        if name not in projects:
            p = Project(name=name, tasks=[])
            projects[name] = p
            project_order.append(name)
        return projects[name]

    for idx, raw in enumerate(lines):
        line_no = idx + 1
        stripped = raw.lstrip()

        # Heading detection (H1, H2, H3+)
        if stripped.startswith("#"):
            hash_count = 0
            for c in stripped:
                if c == "#":
                    hash_count += 1
                else:
                    break
            if hash_count >= 1 and (len(stripped) == hash_count or stripped[hash_count] in (" ", "\t")):
                flush_description()
                if hash_count == 2:
                    flush_note()
                    in_notes_section = False
                    name = stripped[hash_count:].strip()
                    if not name:
                        name = NO_PROJECT
                    current_project = get_or_create_project(name)
                    stack.clear()
                elif hash_count == 3:
                    section = stripped[hash_count:].strip()
                    if section.lower() == "notes":
                        if current_project is None:
                            current_project = get_or_create_project(NO_PROJECT)
                        flush_note()
                        in_notes_section = True
                    else:
                        flush_note()
                        in_notes_section = False
                elif hash_count == 1 and title is None:
                    text_title = stripped[hash_count:].strip()
                    if text_title:
                        title = text_title
                else:
                    flush_note()
                    in_notes_section = False
                continue

        if in_notes_section:
            m_note = _NOTE_BULLET_RE.match(raw)
            if m_note:
                indent = _indent_width(m_note.group("indent"))
                if pending_note_lines is not None and pending_note_indent is not None:
                    if indent > pending_note_indent:
                        pending_note_lines.append(raw)
                        continue
                    if indent == pending_note_indent:
                        flush_note()
                body = m_note.group("body")
                pending_note_indent = indent
                pending_note_lines = [body] if body else []
                continue
            if _BULLET_RE.match(raw):
                flush_note()
                in_notes_section = False
            elif pending_note_lines is not None:
                pending_note_lines.append(raw)
                continue
            else:
                continue

        # Checkbox bullet
        m = _BULLET_RE.match(raw)
        if m:
            flush_description()
            indent = _indent_width(m.group("indent"))
            check = m.group("check")
            body = m.group("body")
            done = check in ("x", "X")

            while stack and stack[-1][0] >= indent:
                stack.pop()

            if len(stack) == 0:
                parent_hash = None
                push_level = 1
            elif len(stack) == 1:
                parent_hash = stack[0][1].hash
                push_level = 2
            elif len(stack) == 2:
                parent_hash = stack[1][1].hash
                push_level = 3
            else:
                # 4+ levels → flatten to sub-subtask of the level-2 parent
                parent_hash = stack[1][1].hash
                push_level = 3
                warnings.append(f"line {line_no}: deep nesting flattened to sub-subtask")

            tag, h, desc = _parse_bullet_body(body, line_no, warnings)

            if h is None:
                placeholder_count += 1
                h = f"__new{placeholder_count}__"

            if h in tasks_by_hash:
                warnings.append(f"line {line_no}: duplicate hash '{h}' ignored")
                continue

            if current_project is None:
                current_project = get_or_create_project(NO_PROJECT)

            task = Task(
                hash=h,
                tag=tag,
                description=desc,
                done=done,
                project=current_project.name,
                parent_hash=parent_hash,
            )
            tasks_by_hash[h] = task

            if parent_hash is None:
                current_project.tasks.append(task)
            else:
                children.setdefault(parent_hash, []).append(task)

            # Reset stack to the new task's level
            stack = stack[: push_level - 1]
            stack.append((indent, task))

            pending_task = task
            pending_lines = []
            continue

        # Otherwise: candidate for description continuation
        if pending_task is not None:
            pending_lines.append(raw)

    flush_description()
    flush_note()

    return ParsedDocument(
        path=path,
        projects=[projects[n] for n in project_order],
        tasks_by_hash=tasks_by_hash,
        children=children,
        warnings=warnings,
        title=title,
    )


def parse(path: Path) -> ParsedDocument:
    text = Path(path).read_text(encoding="utf-8")
    return parse_text(text, path=Path(path))


def existing_hashes(text: str) -> set[str]:
    return {m.group(1).lower() for m in _HASH_PATTERN.finditer(text)}


def existing_note_ids(text: str) -> set[str]:
    return {m.group(1).lower() for m in _NOTE_ID_PATTERN.finditer(text)}
