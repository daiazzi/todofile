from __future__ import annotations

import re
import sys
import webbrowser
from datetime import date, timedelta
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.panel import Panel

from . import daemon as daemon_mod
from . import parser as parser_mod
from . import writer as writer_mod
from . import store

_console = Console()
_HASH_RE = re.compile(r"^[0-9a-f]{5}$")
_NOTE_ID_RE = re.compile(r"^x[0-9a-f]{5}$")
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


PALETTE: dict[str, str] = {
    "red":    "#f7768e",
    "orange": "#ff9e64",
    "yellow": "#e0af68",
    "green":  "#9ece6a",
    "cyan":   "#7dcfff",
    "blue":   "#7aa2f7",
    "purple": "#bb9af7",
    "pink":   "#ff79c6",
    "gray":   "#565f89",
}


def _discover_todo_in_cwd() -> Path:
    cwd = Path.cwd()
    with_sidecar: list[Path] = []
    for entry in cwd.iterdir():
        if entry.is_file() and entry.suffix == ".md":
            sidecar = cwd / f".{entry.name}.dir"
            if sidecar.is_dir():
                with_sidecar.append(entry)
    if len(with_sidecar) == 1:
        return with_sidecar[0].resolve()
    if len(with_sidecar) > 1:
        names = ", ".join(sorted(p.name for p in with_sidecar))
        raise click.ClickException(
            f"Multiple initialized TODO files in {cwd}: {names}. Pass the path explicitly."
        )
    fallback = cwd / "TODO.md"
    if fallback.is_file():
        return fallback.resolve()
    raise click.ClickException(
        f"No TODO file found in {cwd}. Pass a path, or run `tsk init` first."
    )


def _resolve_path(arg: Path | None) -> Path:
    """Resolve an optional path argument. None → discover from cwd."""
    if arg is None:
        return _discover_todo_in_cwd()
    p = arg.expanduser().resolve()
    if not p.exists():
        raise click.ClickException(f"File not found: {p}")
    if not p.is_file():
        raise click.ClickException(f"Not a regular file: {p}")
    return p


def _load_doc(path: Path):
    """Parse, stamp hashes if needed, sync yaml. Returns the final ParsedDocument."""
    store.ensure_sidecar(path)
    text = path.read_text(encoding="utf-8")
    existing = parser_mod.existing_hashes(text)
    existing_notes = parser_mod.existing_note_ids(text)
    doc = parser_mod.parse_text(text, path=path)

    unstamped = [h for h in doc.tasks_by_hash if h.startswith("__new")]
    new_text = text
    changed = False
    if unstamped:
        new_text, _ = writer_mod.stamp_hashes(new_text, existing)
        changed = True
    new_text, note_stamped = writer_mod.stamp_note_hashes(new_text, existing_notes)
    if note_stamped:
        changed = True
    if changed:
        path.write_text(new_text, encoding="utf-8")
        doc = parser_mod.parse(path)

    store.sync(doc, path)

    for w in doc.warnings:
        _console.print(f"[yellow]warning:[/yellow] {w}")
    return doc


@click.group(invoke_without_command=False)
@click.version_option(package_name="todofile", prog_name="tsk")
def cli() -> None:
    """Local task manager backed by a TODO.md.

    Default invocation: `tsk <path/to/TODO.md>` starts the web UI.
    """


@cli.command(hidden=True)
@click.option("--file", "-f", "path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to the TODO.md file.")  
@click.option("--no-browser", is_flag=True, help="Do not open the browser on launch.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=None, help="Override the port from config.yaml.")
def serve(path: Path | None, no_browser: bool, host: str, port: int | None) -> None:
    """Start the web server for the given TODO.md."""
    from .server import run

    todo = _resolve_path(path)
    _load_doc(todo)
    cfg = store.load_config(todo)
    final_port = port if port is not None else cfg.port
    run(todo, host=host, port=final_port, open_browser=not no_browser)


@cli.command()
@click.option("--file", "-f", "path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to the TODO.md file.")
@click.option("--dark-mode", "dark_mode", is_flag=True, help="Set the UI theme to dark.")
@click.option("--light-mode", "light_mode", is_flag=True, help="Set the UI theme to light.")
@click.option(
    "--tag-col",
    "tag_cols",
    multiple=True,
    help='Set a tag colour. Format: "TAG:color" (palette name or hex). Repeatable.',
)
@click.option(
    "--show-dates/--no-show-dates",
    "show_dates",
    default=None,
    help="Show or hide the start/end columns in the UI by default.",
)
@click.option(
    "--show-gantt/--no-show-gantt",
    "show_gantt",
    default=None,
    help="Show or hide the Gantt column by default.",
)
@click.option(
    "--show-calendar/--no-show-calendar",
    "show_calendar",
    default=None,
    help="Show or hide the Calendar column by default.",
)
@click.option(
    "--show-weekends/--no-show-weekends",
    "show_weekends",
    default=None,
    help="Include Sat/Sun in the Gantt day grid.",
)
@click.option(
    "--default-duration",
    "default_duration",
    type=int,
    default=None,
    help="Default span (days) for new task dates; 0 disables automatic dates.",
)
@click.option(
    "--text-size",
    "text_size",
    type=click.Choice(["small", "medium", "big"]),
    default=None,
    help="UI text size.",
)
@click.option(
    "--auto-refresh/--no-auto-refresh",
    "auto_refresh",
    default=None,
    help="Automatically refresh the UI when the TODO file changes.",
)
@click.option("--list-colors", "list_colors", is_flag=True, help="Print the colour palette and exit.")
def init(
    path: Path | None,
    dark_mode: bool,
    light_mode: bool,
    tag_cols: tuple[str, ...],
    show_dates: bool | None,
    show_gantt: bool | None,
    show_calendar: bool | None,
    show_weekends: bool | None,
    default_duration: int | None,
    text_size: str | None,
    auto_refresh: bool | None,
    list_colors: bool,
) -> None:
    """Create the sidecar directory and stamp hashes into the markdown.

    If --file is not given, defaults to ./TODO.md in the current directory.
    If the TODO file does not exist, it is created with a default scaffold.
    The parent directory must exist.
    """
    if list_colors:
        _show_palette()
        return

    if dark_mode and light_mode:
        raise click.ClickException("--dark-mode and --light-mode are mutually exclusive.")
    if default_duration is not None and default_duration < 0:
        raise click.ClickException("--default-duration must be zero or a positive integer.")

    if path is None:
        path = Path.cwd() / "TODO.md"
    path = path.expanduser().resolve()
    parent = path.parent
    if not parent.is_dir():
        raise click.ClickException(f"Parent directory does not exist: {parent}")

    created = False
    if not path.exists():
        title = path.stem
        path.write_text(f"# {title}\n\n## Tasks\n", encoding="utf-8")
        created = True

    store.ensure_sidecar(path)

    # Apply config flags (same surface as `tsk config`) during init.
    parsed_colors: dict[str, str] = {}
    for entry in tag_cols:
        for piece in entry.split(","):
            piece = piece.strip()
            if not piece:
                continue
            if ":" not in piece:
                raise click.ClickException(
                    f"--tag-col entry '{piece}' is missing ':'; expected TAG:color."
                )
            tag_name, _, color_value = piece.partition(":")
            tag_name = tag_name.strip()
            color_value = color_value.strip()
            if not tag_name:
                raise click.ClickException("--tag-col entry is missing the tag name.")
            parsed_colors[tag_name] = _resolve_color(color_value)

    any_cfg_change = (
        dark_mode
        or light_mode
        or bool(parsed_colors)
        or show_dates is not None
        or show_gantt is not None
        or show_calendar is not None
        or show_weekends is not None
        or default_duration is not None
        or text_size is not None
        or auto_refresh is not None
    )
    if any_cfg_change:
        cfg = store.load_config(path)
        if dark_mode:
            cfg.theme = "dark"
        if light_mode:
            cfg.theme = "light"
        if show_dates is not None:
            cfg.show_dates = show_dates
        if show_gantt is not None:
            cfg.show_gantt = show_gantt
        if show_calendar is not None:
            cfg.show_calendar = show_calendar
        if show_weekends is not None:
            cfg.show_weekends = show_weekends
        if default_duration is not None:
            cfg.default_duration = default_duration
        if text_size is not None:
            cfg.text_size = text_size
        if auto_refresh is not None:
            cfg.auto_refresh = auto_refresh
        for tag_name, hex_value in parsed_colors.items():
            cfg.colors[tag_name] = hex_value
        store.save_config(path, cfg)

    text = path.read_text(encoding="utf-8")
    existing = parser_mod.existing_hashes(text)
    existing_notes = parser_mod.existing_note_ids(text)
    new_text, stamped = writer_mod.stamp_hashes(text, existing)
    new_text, note_stamped = writer_mod.stamp_note_hashes(new_text, existing_notes)
    if stamped:
        path.write_text(new_text, encoding="utf-8")
    elif note_stamped:
        path.write_text(new_text, encoding="utf-8")
    doc = parser_mod.parse(path)
    store.sync(doc, path)
    if created:
        _console.print(f"tsk: created {path}")
    _console.print(f"tsk: initialized {store.sidecar_dir(path).name}")
    _console.print(f"tsk: stamped {len(stamped)} new task(s)")
    if note_stamped:
        _console.print(f"tsk: stamped {len(note_stamped)} new note id(s)")
    for w in doc.warnings:
        _console.print(f"[yellow]warning:[/yellow] {w}")


@cli.command()
@click.option("--file", "-f", "path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to the TODO.md file.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=None, help="Override the port from config.yaml.")
def up(path: Path | None, host: str, port: int | None) -> None:
    """Start the server detached from the terminal (background)."""
    todo = _resolve_path(path)
    _load_doc(todo)
    try:
        pid, url = daemon_mod.start(todo, host=host, port=port)
    except RuntimeError as e:
        raise click.ClickException(str(e))
    _console.print(f"tsk: started daemon (pid {pid})")
    _console.print(f"tsk: open {url}")


@cli.command()
@click.option("--file", "-f", "path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to the TODO.md file.")
def down(path: Path | None) -> None:
    """Stop the daemon associated with the given TODO file."""
    todo = _resolve_path(path)
    pid = daemon_mod.stop(todo)
    if pid is None:
        _console.print("tsk: no daemon running")
    else:
        _console.print(f"tsk: stopped daemon (pid {pid})")


@cli.command()
@click.option("--file", "-f", "path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to the TODO.md file.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=None, help="Override the port from config.yaml.")
def restart(path: Path | None, host: str, port: int | None) -> None:
    """Restart the daemon associated with the given TODO file."""
    todo = _resolve_path(path)
    _load_doc(todo)
    stopped = daemon_mod.stop(todo)
    if stopped is None:
        _console.print("tsk: daemon was already down")
    else:
        _console.print(f"tsk: stopped daemon (pid {stopped})")
    try:
        pid, url = daemon_mod.start(todo, host=host, port=port)
    except RuntimeError as e:
        raise click.ClickException(str(e))
    _console.print(f"tsk: started daemon (pid {pid})")
    _console.print(f"tsk: open {url}")

@cli.command()
@click.option("--file", "-f", "path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to the TODO.md file.")
def status(path: Path | None) -> None:
    """Show the resolved TODO path and daemon state."""
    todo = _resolve_path(path)
    _console.print(f"tsk: using [cyan]{todo}[/]")
    pid, url = daemon_mod.read_status(todo)
    if pid is None:
        _console.print("tsk: daemon is [yellow]down[/]")
    else:
        suffix = f" at [cyan]{url}[/]" if url else ""
        _console.print(f"tsk: daemon is [green]up[/] (pid [bold]{pid}[/]){suffix}")


def _add_task(
    path: Path | None,
    description: str,
    tag: str | None,
    parent_hash: str | None,
    project: str | None,
    start: str | None,
    end: str | None,
    duration: int | None,
) -> None:
    path = _resolve_path(path)
    doc = _load_doc(path)

    if parent_hash:
        if not _HASH_RE.match(parent_hash):
            raise click.ClickException(
                f"Invalid hash '{parent_hash}': expected 5 lowercase hex chars."
            )
        parent_task = doc.tasks_by_hash.get(parent_hash)
        if parent_task is None:
            raise click.ClickException(f"No task with hash '{parent_hash}' in {path}.")
        if parent_task.parent_hash is not None:
            raise click.ClickException(
                f"Cannot nest under '{parent_hash}': only one level of subtasks is supported."
            )
        resolved_project = parent_task.project
    else:
        existing_projects = [p.name for p in doc.projects]
        if project is None:
            if len(existing_projects) == 0:
                from .models import NO_PROJECT

                resolved_project = NO_PROJECT
            elif len(existing_projects) == 1:
                resolved_project = existing_projects[0]
            else:
                avail = ", ".join(existing_projects)
                raise click.ClickException(
                    f"Must pass --project when the file has more than one project. Available: {avail}."
                )
        else:
            if project not in existing_projects:
                avail = ", ".join(existing_projects) or "(none)"
                raise click.ClickException(
                    f"No project named '{project}'. Available: {avail}."
                )
            resolved_project = project

    start_d, end_d = _resolve_dates(start, end, duration)

    new_h = writer_mod.new_hash(set(doc.tasks_by_hash.keys()))
    text = path.read_text(encoding="utf-8")
    new_text = writer_mod.insert_task(
        text,
        project=resolved_project,
        parent_hash=parent_hash,
        tag=tag,
        description=description,
        hash=new_h,
    )
    path.write_text(new_text, encoding="utf-8")

    if start_d is not None or end_d is not None:
        store.set_dates(path, new_h, start_d, end_d)

    doc2 = parser_mod.parse(path)
    store.sync(doc2, path)
    _console.print(f"tsk: added ({new_h}).")


def _remove_task(hash: str, path: Path | None) -> None:
    if not _HASH_RE.match(hash):
        raise click.ClickException(
            f"Invalid hash '{hash}': expected 5 lowercase hex chars."
        )

    path = _resolve_path(path)
    doc = _load_doc(path)
    if hash not in doc.tasks_by_hash:
        raise click.ClickException(f"No task with hash '{hash}' in {path}.")

    subtasks = doc.children_of(hash)
    text = path.read_text(encoding="utf-8")
    try:
        new_text = writer_mod.remove_task(text, hash)
    except KeyError:
        raise click.ClickException(f"No task with hash '{hash}' in {path}.")
    path.write_text(new_text, encoding="utf-8")

    doc2 = parser_mod.parse(path)
    store.sync(doc2, path)
    _console.print(f"tsk: removed ({hash}) and {len(subtasks)} subtask(s).")


@cli.command("add")
@click.argument("description", type=str, required=True, help="Task description.")
@click.option("--file", "-f", "path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to the TODO.md file.")
@click.option("--tag", "-t", default=None, help="Optional category tag.")
@click.option("--parent", "-p", "parent_hash", default=None, help="Parent task hash for a subtask.")
@click.option("--project", "-P", default=None, help="Project to add under.")
@click.option("--start-date", "-s", "start", type=str, default=None, help="Start date YYYY-MM-DD.")
@click.option("--end-date", "-e", "end", type=str, default=None, help="End date YYYY-MM-DD.")
@click.option("--duration", type=int, default=None, help="Duration in days (positive).")
def add(
    description: str,
    path: Path | None,
    tag: str | None,
    parent_hash: str | None,
    project: str | None,
    start: str | None,
    end: str | None,
    duration: int | None,
) -> None:
    """Add a new task to the markdown."""
    _add_task(path, description, tag, parent_hash, project, start, end, duration)


@cli.command("remove")
@click.argument("hash")
@click.option("--file", "-f", "path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to the TODO.md file.")
def remove(hash: str, path: Path | None) -> None:
    """Remove the task with the given hash."""
    if _NOTE_ID_RE.match(hash):
        todo = _resolve_path(path)
        _load_doc(todo)
        text = todo.read_text(encoding="utf-8")
        try:
            new_text = writer_mod.remove_note(text, hash)
        except KeyError:
            raise click.ClickException(f"No note with id '{hash}' in {todo}.")
        except ValueError:
            raise click.ClickException(
                f"Invalid note id '{hash}': expected x + 5 lowercase hex chars."
            )
        todo.write_text(new_text, encoding="utf-8")
        doc2 = parser_mod.parse(todo)
        store.sync(doc2, todo)
        _console.print(f"tsk: removed note ({hash}).")
        return
    _remove_task(hash, path)


@cli.command("annotate")
@click.argument("note_text")
@click.option("--file", "-f", "path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to the TODO.md file.")
@click.option("--project", "-P", "project", default=None, help="Project to add the note under.")
def annotate(note_text: str, path: Path | None, project: str | None) -> None:
    """Add a note under a project's ### Notes section."""
    todo = _resolve_path(path)
    doc = _load_doc(todo)

    projects = [p.name for p in doc.projects]
    if project is None:
        if len(projects) > 1:
            avail = ", ".join(projects)
            raise click.ClickException(
                f"Must pass --project when the file has more than one project. Available: {avail}."
            )
        project = projects[0] if projects else None

    if project is None:
        from .models import NO_PROJECT

        project = NO_PROJECT
    elif project not in projects:
        avail = ", ".join(projects) or "(none)"
        raise click.ClickException(f"No project named '{project}'. Available: {avail}.")

    existing_notes = parser_mod.existing_note_ids(todo.read_text(encoding="utf-8"))
    note_id = writer_mod.new_note_id(existing_notes)
    text = todo.read_text(encoding="utf-8")
    new_text = writer_mod.insert_note(text, project=project, note_id=note_id, note_text=note_text)
    todo.write_text(new_text, encoding="utf-8")

    doc2 = parser_mod.parse(todo)
    store.sync(doc2, todo)
    _console.print(f"tsk: annotated ({note_id}).")



@cli.command("config")
@click.option("--dark-mode", "dark_mode", is_flag=True, help="Set the UI theme to dark.")
@click.option("--light-mode", "light_mode", is_flag=True, help="Set the UI theme to light.")
@click.option(
    "--tag-col",
    "tag_cols",
    multiple=True,
    help='Set a tag colour. Format: "TAG:color" (palette name or hex). Repeatable.',
)
@click.option(
    "--show-dates/--no-show-dates",
    "show_dates",
    default=None,
    help="Show or hide the start/end columns in the UI by default.",
)
@click.option(
    "--show-gantt/--no-show-gantt",
    "show_gantt",
    default=None,
    help="Show or hide the Gantt column by default.",
)
@click.option(
    "--show-calendar/--no-show-calendar",
    "show_calendar",
    default=None,
    help="Show or hide the Calendar column by default.",
)
@click.option(
    "--show-weekends/--no-show-weekends",
    "show_weekends",
    default=None,
    help="Include Sat/Sun in the Gantt day grid.",
)
@click.option(
    "--default-duration",
    "default_duration",
    type=int,
    default=None,
    help="Default span (days) for new task dates; 0 disables automatic dates.",
)
@click.option(
    "--text-size",
    "text_size",
    type=click.Choice(["small", "medium", "big"]),
    default=None,
    help="UI text size.",
)
@click.option(
    "--auto-refresh/--no-auto-refresh",
    "auto_refresh",
    default=None,
    help="Automatically refresh the UI when the TODO file changes.",
)
@click.option("--list-colors", "list_colors", is_flag=True, help="Print the colour palette and exit.")
@click.pass_context
def config(
    ctx: click.Context,
    dark_mode: bool,
    light_mode: bool,
    tag_cols: tuple[str, ...],
    show_dates: bool | None,
    show_gantt: bool | None,
    show_calendar: bool | None,
    show_weekends: bool | None,
    default_duration: int | None,
    text_size: str | None,
    auto_refresh: bool | None,
    list_colors: bool,
) -> None:
    """Inspect or modify the per-project config.yaml.

    \b
    Examples:
      tsk config --dark-mode
      tsk config --tag-col DEV:green --tag-col DATA:yellow
      tsk config --show-dates --default-duration 5
      tsk config --text-size big
      tsk config --list-colors
    """
    if list_colors:
        _show_palette()
        return

    if dark_mode and light_mode:
        raise click.ClickException("--dark-mode and --light-mode are mutually exclusive.")

    if default_duration is not None and default_duration < 0:
        raise click.ClickException("--default-duration must be zero or a positive integer.")

    parsed_colors: dict[str, str] = {}
    for entry in tag_cols:
        for piece in entry.split(","):
            piece = piece.strip()
            if not piece:
                continue
            if ":" not in piece:
                raise click.ClickException(
                    f"--tag-col entry '{piece}' is missing ':'; expected TAG:color."
                )
            tag_name, _, color_value = piece.partition(":")
            tag_name = tag_name.strip()
            color_value = color_value.strip()
            if not tag_name:
                raise click.ClickException("--tag-col entry is missing the tag name.")
            parsed_colors[tag_name] = _resolve_color(color_value)

    any_change = (
        dark_mode
        or light_mode
        or parsed_colors
        or show_dates is not None
        or show_gantt is not None
        or show_calendar is not None
        or show_weekends is not None
        or default_duration is not None
        or text_size is not None
        or auto_refresh is not None
    )
    if not any_change:
        click.echo(ctx.get_help())
        return

    todo = _resolve_path(None)
    store.ensure_sidecar(todo)
    cfg = store.load_config(todo)

    summary: list[str] = []
    if dark_mode:
        cfg.theme = "dark"
        summary.append("theme = [bold]dark[/]")
    if light_mode:
        cfg.theme = "light"
        summary.append("theme = [bold]light[/]")
    if show_dates is not None:
        cfg.show_dates = show_dates
        summary.append(f"show_dates = [bold]{str(show_dates).lower()}[/]")
    if show_gantt is not None:
        cfg.show_gantt = show_gantt
        summary.append(f"show_gantt = [bold]{str(show_gantt).lower()}[/]")
    if show_calendar is not None:
        cfg.show_calendar = show_calendar
        summary.append(f"show_calendar = [bold]{str(show_calendar).lower()}[/]")
    if show_weekends is not None:
        cfg.show_weekends = show_weekends
        summary.append(f"show_weekends = [bold]{str(show_weekends).lower()}[/]")
    if default_duration is not None:
        cfg.default_duration = default_duration
        if default_duration == 0:
            summary.append("default_duration = [bold]0[/] (no automatic dates)")
        else:
            summary.append(f"default_duration = [bold]{default_duration}[/] day(s)")
    if text_size is not None:
        cfg.text_size = text_size
        summary.append(f"text_size = [bold]{text_size}[/]")
    if auto_refresh is not None:
        cfg.auto_refresh = auto_refresh
        summary.append(f"auto_refresh = [bold]{str(auto_refresh).lower()}[/]")
    for tag_name, hex_value in parsed_colors.items():
        cfg.colors[tag_name] = hex_value
        summary.append(
            f"colors.{tag_name} = [on {hex_value}]      [/] [bold]{hex_value}[/]"
        )

    store.save_config(todo, cfg)
    for line in summary:
        _console.print(f"tsk: {line}")


def _show_palette() -> None:
    _console.print("[bold]Available palette colours[/bold]")
    _console.print("Use a name below or any [cyan]#rrggbb[/] hex value.\n")
    for name, hex_value in PALETTE.items():
        _console.print(f"  [on {hex_value}]      [/] [bold]{name:<8}[/]  {hex_value}")


def _resolve_color(value: str) -> str:
    if value in PALETTE:
        return PALETTE[value]
    if _HEX_COLOR_RE.match(value):
        return value.lower()
    palette_names = ", ".join(PALETTE.keys())
    raise click.ClickException(
        f"Invalid colour '{value}'. Use a hex like #abcdef or a palette name: {palette_names}."
    )


@cli.group(name="help")
def help_group() -> None:
    """Show documentation on specific topics."""


@help_group.command(name="format")
def help_format() -> None:
    """Print the TODO.md format spec."""
    _console.print(
        Panel.fit(
            _FORMAT_HELP_TEXT,
            title="TODO.md format",
            border_style="cyan",
        )
    )


_FORMAT_HELP_TEXT = """\
[bold]File structure[/bold]
  # Document title             (ignored)
  ## Project name              (starts a project)
  ### Notes                    (optional project notes)
  - A note bullet; content until the next - or * bullet is markdown.
  - [ ] tag(hash): task         (a task)
    continued description on indented lines
    - sub-bullet of description (no checkbox)
    - [ ] tag(hash): subtask   (a subtask)
  - [x] (hash): done task

[bold]Rules[/bold]
  • H1 is ignored.
  • H2 starts a project. Tasks belong to the most recent H2.
  • [cyan]### Notes[/cyan] under a project holds notes: plain [cyan]-[/cyan] or [cyan]*[/cyan]
    bullets (not checkboxes). Each bullet starts a note; lines until the next bullet
    at the same indent are rendered as markdown in the UI.
  • A [italic]task[/italic] is any indented bullet starting with [cyan]- [ ][/cyan] or [cyan]- [x][/cyan].
  • Indentation is lenient (tabs or spaces). Tabs count as 4 spaces.
  • [italic]Subtasks[/italic] are checkbox bullets indented deeper than their parent.
    Maximum nesting is 2 levels; deeper bullets are flattened with a warning.
  • [italic]Description[/italic] is the text after `:` plus subsequent non-checkbox lines
    up to the next checkbox bullet or H2.
  • [italic]Tag[/italic] is optional. Format: [cyan]tag(hash):[/cyan] or [cyan](hash):[/cyan] without tag.
  • [italic]Hash[/italic] is 5 lowercase hex chars. The manager stamps one into new
    tasks automatically.
  • [cyan][x][/cyan] / [cyan][X][/cyan] marks a task as done; [cyan][ ][/cyan] as not done.

[bold]Storage[/bold]
  Metadata (dates, timestamps) lives in [cyan].<filename>.dir/tasks.yaml[/cyan]
  next to the TODO file. The markdown is never written for dates — only for
  hash stamping and explicit `add` / `remove`.
"""


def _resolve_dates(
    start_s: str | None, end_s: str | None, duration: int | None
) -> tuple[date | None, date | None]:
    set_count = sum(x is not None for x in (start_s, end_s, duration))
    if set_count == 3:
        raise click.ClickException("Pass at most two of --start-date, --end-date, --duration.")
    if duration is not None and duration <= 0:
        raise click.ClickException("--duration must be a positive integer.")
    if duration is not None and start_s is None and end_s is None:
        raise click.ClickException("--duration needs --start-date or --end-date as an anchor.")

    start_d = _parse_date(start_s) if start_s else None
    end_d = _parse_date(end_s) if end_s else None

    if start_d and end_d and end_d < start_d:
        raise click.ClickException("--end-date is before --start-date.")

    if duration is not None:
        if start_d is not None and end_d is None:
            end_d = start_d + timedelta(days=duration - 1)
        elif end_d is not None and start_d is None:
            start_d = end_d - timedelta(days=duration - 1)
    return start_d, end_d


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise click.ClickException(f"Invalid date '{s}': expected YYYY-MM-DD.")


def main() -> None:
    argv = sys.argv[1:]
    known_top = {
        "init",
        "add",
        "remove",
        "annotate",
        "help",
        "serve",
        "up",
        "down",
        "restart",
        "config",
        "status",
    }
    if not argv:
        argv = ["serve"]
    elif not argv[0].startswith("-") and argv[0] not in known_top:
        argv = ["serve", "--file"] + argv
    cli.main(args=argv, prog_name="tsk", standalone_mode=True)


if __name__ == "__main__":
    main()
