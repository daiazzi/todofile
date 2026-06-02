from __future__ import annotations

import os
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path

import yaml

from .models import Config, ParsedDocument, TaskMetadata


_AGENT_MD_SOURCE = Path(__file__).parent / "static" / "agent.md"


_DEFAULT_CONFIG_BODY = """\
# todofile config — edit and run `tsk` to apply.
port: null

theme: light            # "dark" or "light"
text_size: big          # "small", "medium", or "big"
show_dates: false       # default visibility of the start/end columns
show_gantt: false       # show the Gantt column (UI switch persists here)
show_calendar: false    # show the Calendar column (UI switch persists here)
show_weekends: false    # include Sat/Sun in the Gantt day grid (no UI switch)
auto_refresh: true      # refresh UI automatically on TODO.md edits

# New tasks get start=today, end=today+(default_duration-1) days. Use 0 for no default dates.
default_duration: 0

# Tag colours. The "default" entry colours tags without a specific mapping.
colors:
  default: "#8c8c8c"
  FIX: "#ff0000"
  FEAT: "#0080ff"
  REFACTOR: "#ffbf00"
  PERF: "#ff33ff"
  TESTS: "#269900"
  DOCS: "#663300"
  ENV: "#999900"
  MISC: "#339999"
"""


def sidecar_dir(todo_path: Path) -> Path:
    todo_path = Path(todo_path)
    return todo_path.parent / f".{todo_path.name}.dir"


def tasks_yaml_path(todo_path: Path) -> Path:
    return sidecar_dir(todo_path) / "tasks.yaml"


def config_yaml_path(todo_path: Path) -> Path:
    return sidecar_dir(todo_path) / "config.yaml"


def ensure_sidecar(todo_path: Path) -> Path:
    d = sidecar_dir(todo_path)
    d.mkdir(parents=True, exist_ok=True)
    tp = tasks_yaml_path(todo_path)
    if not tp.exists():
        _atomic_write(tp, "tasks: []\n")
    cp = config_yaml_path(todo_path)
    if not cp.exists():
        _atomic_write(cp, _DEFAULT_CONFIG_BODY)
    ap = d / "agent.md"
    if not ap.exists() and _AGENT_MD_SOURCE.exists():
        shutil.copyfile(_AGENT_MD_SOURCE, ap)
    return d


def load_tasks_yaml(todo_path: Path) -> dict[str, TaskMetadata]:
    p = tasks_yaml_path(todo_path)
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = raw.get("tasks") or []
    out: dict[str, TaskMetadata] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        h = row.get("hash")
        if not isinstance(h, str):
            continue
        known = {"hash", "start", "end", "created", "completed"}
        extra = {k: v for k, v in row.items() if k not in known}
        out[h] = TaskMetadata(
            hash=h,
            start=_to_date(row.get("start")),
            end=_to_date(row.get("end")),
            created=_to_datetime(row.get("created")),
            completed=_to_datetime(row.get("completed")),
            extra=extra,
        )
    return out


def save_tasks_yaml(todo_path: Path, data: dict[str, TaskMetadata]) -> None:
    rows = []
    for h in sorted(data.keys()):
        m = data[h]
        row = {
            "hash": m.hash,
            "start": m.start.isoformat() if m.start else None,
            "end": m.end.isoformat() if m.end else None,
            "created": m.created.isoformat(timespec="seconds") if m.created else None,
            "completed": m.completed.isoformat(timespec="seconds") if m.completed else None,
        }
        row.update(m.extra)
        rows.append(row)
    body = yaml.safe_dump({"tasks": rows}, sort_keys=False, default_flow_style=False)
    _atomic_write(tasks_yaml_path(todo_path), body)


_DEFAULT_COLORS = {
    "default": "#8c8c8c",
    "FIX": "#ff0000",
    "FEAT": "#0080ff",
    "REFACTOR": "#ffbf00",
    "PERF": "#ff33ff",
    "TESTS": "#269900",
    "DOCS": "#663300",
    "ENV": "#999900",
    "MISC": "#339999",
    "DEADLINE": "#ffff00"
}


def load_config(todo_path: Path) -> Config:
    p = config_yaml_path(todo_path)
    if not p.exists():
        return Config(colors=dict(_DEFAULT_COLORS))
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return Config(colors=dict(_DEFAULT_COLORS))
    port = raw.get("port")
    if port is not None and not isinstance(port, int):
        port = None
    colors_raw = raw.get("colors") or {}
    colors = dict(_DEFAULT_COLORS)
    if isinstance(colors_raw, dict):
        for k, v in colors_raw.items():
            if isinstance(k, str) and isinstance(v, str):
                colors[k] = v
    theme = raw.get("theme")
    if theme not in ("dark", "light"):
        theme = "light"
    duration = raw.get("default_duration", 0)
    if not isinstance(duration, int) or duration < 0:
        duration = 0
    show_dates = raw.get("show_dates", False)
    if not isinstance(show_dates, bool):
        show_dates = False
    show_gantt = raw.get("show_gantt", False)
    if not isinstance(show_gantt, bool):
        show_gantt = False
    show_calendar = raw.get("show_calendar", False)
    if not isinstance(show_calendar, bool):
        show_calendar = False
    show_weekends = raw.get("show_weekends", False)
    if not isinstance(show_weekends, bool):
        show_weekends = False
    text_size = raw.get("text_size", "big")
    if text_size not in ("small", "medium", "big"):
        text_size = "big"
    auto_refresh = raw.get("auto_refresh", True)
    if not isinstance(auto_refresh, bool):
        auto_refresh = True
    known = {
        "port",
        "colors",
        "theme",
        "default_duration",
        "show_dates",
        "show_gantt",
        "show_calendar",
        "show_weekends",
        "text_size",
        "auto_refresh",
    }
    # Legacy keys that have been removed; dropped silently.
    legacy = {"show_panel"}
    extra = {k: v for k, v in raw.items() if k not in known and k not in legacy}
    return Config(
        port=port,
        colors=colors,
        theme=theme,
        default_duration=duration,
        show_dates=show_dates,
        show_gantt=show_gantt,
        show_calendar=show_calendar,
        show_weekends=show_weekends,
        text_size=text_size,
        auto_refresh=auto_refresh,
        extra=extra,
    )


def save_config(todo_path: Path, cfg: Config) -> None:
    """Write the config back to config.yaml. Comments in the file are lost."""
    body: dict = {
        "port": cfg.port,
        "theme": cfg.theme,
        "text_size": cfg.text_size,
        "show_dates": cfg.show_dates,
        "show_gantt": cfg.show_gantt,
        "show_calendar": cfg.show_calendar,
        "show_weekends": cfg.show_weekends,
        "auto_refresh": cfg.auto_refresh,
        "default_duration": cfg.default_duration,
        "colors": dict(cfg.colors),
    }
    body.update(cfg.extra)
    yaml_text = yaml.safe_dump(body, sort_keys=False, default_flow_style=False)
    _atomic_write(config_yaml_path(todo_path), yaml_text)


def sync(doc: ParsedDocument, todo_path: Path) -> ParsedDocument:
    """Merge yaml metadata into the parsed doc. Mutates tasks in `doc` and writes back yaml if changed."""
    from datetime import timedelta

    yaml_data = load_tasks_yaml(todo_path)
    cfg = load_config(todo_path)
    now = datetime.now().replace(microsecond=0)
    today = now.date()
    changed = False

    # Walk parsed tasks
    for h, task in doc.tasks_by_hash.items():
        meta = yaml_data.get(h)
        if meta is None:
            if cfg.default_duration == 0:
                meta = TaskMetadata(hash=h, created=now)
            else:
                default_end = today + timedelta(days=cfg.default_duration - 1)
                meta = TaskMetadata(
                    hash=h, created=now, start=today, end=default_end
                )
            yaml_data[h] = meta
            changed = True
        else:
            if meta.created is None:
                meta.created = now
                changed = True

        # Sync done state with completed
        if task.done and meta.completed is None:
            meta.completed = now
            changed = True
        elif not task.done and meta.completed is not None:
            meta.completed = None
            changed = True

        task.start = meta.start
        task.end = meta.end
        task.created = meta.created
        task.completed = meta.completed

    # Drop yaml entries no longer in md
    to_drop = [h for h in yaml_data if h not in doc.tasks_by_hash]
    for h in to_drop:
        del yaml_data[h]
        changed = True

    if changed:
        save_tasks_yaml(todo_path, yaml_data)
    return doc


def set_dates(todo_path: Path, hash: str, start: date | None, end: date | None) -> TaskMetadata:
    data = load_tasks_yaml(todo_path)
    if hash not in data:
        data[hash] = TaskMetadata(hash=hash, created=datetime.now().replace(microsecond=0))
    data[hash].start = start
    data[hash].end = end
    save_tasks_yaml(todo_path, data)
    return data[hash]


# --- helpers ----------------------------------------------------------------


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _to_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


def _to_datetime(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(microsecond=0)
    if isinstance(v, date):
        return datetime.combine(v, datetime.min.time())
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v).replace(microsecond=0)
        except ValueError:
            return None
    return None
