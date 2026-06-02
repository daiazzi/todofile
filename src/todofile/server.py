from __future__ import annotations

import json
import socket
import threading
import webbrowser
from datetime import date
from pathlib import Path

import anyio
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

from . import parser as parser_mod
from . import store
from . import writer as writer_mod
from .models import ParsedDocument


STATIC_DIR = Path(__file__).parent / "static"


def _serialise(doc: ParsedDocument, todo_path: Path) -> dict:
    cfg = store.load_config(todo_path)
    def task_dict(task) -> dict:
        return {
            "hash": task.hash,
            "tag": task.tag,
            "description": task.description,
            "done": task.done,
            "parent_hash": task.parent_hash,
            "project": task.project,
            "start": task.start.isoformat() if task.start else None,
            "end": task.end.isoformat() if task.end else None,
            "created": task.created.isoformat(timespec="seconds") if task.created else None,
            "completed": task.completed.isoformat(timespec="seconds") if task.completed else None,
            "subtasks": [task_dict(c) for c in doc.children_of(task.hash)],
        }

    return {
        "todo_path": str(todo_path),
        "title": doc.title,
        "colors": cfg.colors,
        "theme": cfg.theme,
        "text_size": cfg.text_size,
        "show_dates": cfg.show_dates,
        "show_gantt": cfg.show_gantt,
        "show_calendar": cfg.show_calendar,
        "show_weekends": cfg.show_weekends,
        "auto_refresh": cfg.auto_refresh,
        "projects": [
            {
                "name": p.name,
                "notes": [{"hash": n.hash, "content": n.content} for n in p.notes],
                "tasks": [task_dict(t) for t in p.tasks],
            }
            for p in doc.projects
        ],
        "warnings": doc.warnings,
    }


def _reload(todo_path: Path) -> ParsedDocument:
    text = todo_path.read_text(encoding="utf-8")
    existing = parser_mod.existing_hashes(text)
    existing_notes = parser_mod.existing_note_ids(text)
    doc = parser_mod.parse_text(text, path=todo_path)
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
        todo_path.write_text(new_text, encoding="utf-8")
        doc = parser_mod.parse(todo_path)
    store.sync(doc, todo_path)
    return doc


def build_app(todo_path: Path) -> Starlette:
    todo_path = Path(todo_path).resolve()

    async def index(request: Request) -> Response:
        return FileResponse(STATIC_DIR / "index.html")

    async def get_tasks(request: Request) -> Response:
        doc = _reload(todo_path)
        return JSONResponse(_serialise(doc, todo_path))

    async def post_refresh(request: Request) -> Response:
        try:
            doc = _reload(todo_path)
        except OSError as e:
            return JSONResponse({"error": f"TODO.md not readable: {e}"}, status_code=500)
        return JSONResponse(_serialise(doc, todo_path))

    async def get_events(request: Request) -> Response:
        async def event_stream():
            last_mtime_ns: int | None = None
            last_sent_disabled = False
            while True:
                try:
                    cfg = store.load_config(todo_path)
                    if not cfg.auto_refresh:
                        if not last_sent_disabled:
                            last_sent_disabled = True
                            yield "event: disabled\ndata: 1\n\n"
                        await anyio.sleep(1.0)
                        continue
                    last_sent_disabled = False

                    st = todo_path.stat()
                    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
                    if last_mtime_ns is None:
                        last_mtime_ns = mtime_ns
                        yield "event: ready\ndata: 1\n\n"
                    elif mtime_ns != last_mtime_ns:
                        last_mtime_ns = mtime_ns
                        yield f"event: changed\ndata: {mtime_ns}\n\n"
                    await anyio.sleep(0.5)
                except Exception:
                    # Keep the connection alive even if the file is temporarily unreadable.
                    yield "event: error\ndata: 1\n\n"
                    await anyio.sleep(1.0)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    async def post_dates(request: Request) -> Response:
        hash_ = request.path_params["hash"]
        body = await request.body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

        doc = _reload(todo_path)
        if hash_ not in doc.tasks_by_hash:
            return JSONResponse({"error": f"No task with hash '{hash_}'."}, status_code=404)

        current = doc.tasks_by_hash[hash_]
        new_start = current.start
        new_end = current.end

        if "start" in data:
            v = data["start"]
            if v is None:
                new_start = None
            elif isinstance(v, str):
                try:
                    new_start = date.fromisoformat(v)
                except ValueError:
                    return JSONResponse(
                        {"error": f"Invalid date '{v}': expected YYYY-MM-DD."}, status_code=400
                    )
            else:
                return JSONResponse({"error": "start must be a date string or null."}, status_code=400)

        if "end" in data:
            v = data["end"]
            if v is None:
                new_end = None
            elif isinstance(v, str):
                try:
                    new_end = date.fromisoformat(v)
                except ValueError:
                    return JSONResponse(
                        {"error": f"Invalid date '{v}': expected YYYY-MM-DD."}, status_code=400
                    )
            else:
                return JSONResponse({"error": "end must be a date string or null."}, status_code=400)

        if new_start and new_end and new_end < new_start:
            return JSONResponse({"error": "end is before start."}, status_code=400)

        meta = store.set_dates(todo_path, hash_, new_start, new_end)
        return JSONResponse(
            {
                "hash": meta.hash,
                "start": meta.start.isoformat() if meta.start else None,
                "end": meta.end.isoformat() if meta.end else None,
            }
        )

    async def post_reorder(request: Request) -> Response:
        body = await request.body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

        project = data.get("project")
        parent_hash = data.get("parent_hash")
        order = data.get("order")
        if not isinstance(project, str):
            return JSONResponse({"error": "Expected `project` (string)."}, status_code=400)
        if parent_hash is not None and not isinstance(parent_hash, str):
            return JSONResponse(
                {"error": "Expected `parent_hash` (string or null)."}, status_code=400
            )
        if not isinstance(order, list) or not all(isinstance(h, str) for h in order):
            return JSONResponse(
                {"error": "Expected `order` (list of strings)."}, status_code=400
            )

        doc = _reload(todo_path)
        for h in order:
            t = doc.tasks_by_hash.get(h)
            if t is None:
                return JSONResponse(
                    {"error": f"Unknown hash '{h}'."}, status_code=404
                )
            if t.project != project:
                return JSONResponse(
                    {"error": f"Hash '{h}' is not in project '{project}'."},
                    status_code=400,
                )
            if (t.parent_hash or None) != (parent_hash or None):
                return JSONResponse(
                    {"error": f"Hash '{h}' has a different parent."}, status_code=400
                )

        if parent_hash is not None:
            siblings = {c.hash for c in doc.children_of(parent_hash)}
        else:
            proj = next((p for p in doc.projects if p.name == project), None)
            siblings = {t.hash for t in proj.tasks} if proj else set()
        if set(order) != siblings:
            return JSONResponse(
                {"error": "`order` must contain exactly the sibling hashes."},
                status_code=400,
            )

        text = todo_path.read_text(encoding="utf-8")
        try:
            new_text = writer_mod.reorder_tasks(text, order)
        except (KeyError, ValueError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        todo_path.write_text(new_text, encoding="utf-8")
        doc2 = _reload(todo_path)
        return JSONResponse(_serialise(doc2, todo_path))

    async def post_done(request: Request) -> Response:
        hash_ = request.path_params["hash"]
        body = await request.body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON body."}, status_code=400)
        if "done" not in data or not isinstance(data["done"], bool):
            return JSONResponse({"error": "Expected JSON body {\"done\": bool}."}, status_code=400)

        text = todo_path.read_text(encoding="utf-8")
        try:
            new_text = writer_mod.set_done(text, hash_, data["done"])
        except KeyError:
            return JSONResponse({"error": f"No task with hash '{hash_}'."}, status_code=404)
        todo_path.write_text(new_text, encoding="utf-8")
        doc = _reload(todo_path)
        return JSONResponse(_serialise(doc, todo_path))

    async def post_description(request: Request) -> Response:
        hash_ = request.path_params["hash"]
        body = await request.body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON body."}, status_code=400)
        if "description" not in data or not isinstance(data["description"], str):
            return JSONResponse(
                {"error": "Expected JSON body {\"description\": string}."}, status_code=400
            )

        text = todo_path.read_text(encoding="utf-8")
        try:
            new_text = writer_mod.set_description(text, hash_, data["description"])
        except KeyError:
            return JSONResponse({"error": f"No task with hash '{hash_}'."}, status_code=404)
        todo_path.write_text(new_text, encoding="utf-8")
        doc = _reload(todo_path)
        return JSONResponse(_serialise(doc, todo_path))

    async def post_remove_task(request: Request) -> Response:
        hash_ = request.path_params["hash"]
        text = todo_path.read_text(encoding="utf-8")
        try:
            new_text = writer_mod.remove_task(text, hash_)
        except KeyError:
            return JSONResponse({"error": f"No task with hash '{hash_}'."}, status_code=404)
        todo_path.write_text(new_text, encoding="utf-8")
        doc = _reload(todo_path)
        return JSONResponse(_serialise(doc, todo_path))

    async def post_config(request: Request) -> Response:
        body = await request.body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON body."}, status_code=400)
        if not isinstance(data, dict):
            return JSONResponse({"error": "Expected a JSON object."}, status_code=400)

        cfg = store.load_config(todo_path)
        allowed_bool = {"show_gantt", "show_calendar", "show_weekends", "show_dates"}
        for k, v in data.items():
            if k in allowed_bool:
                if not isinstance(v, bool):
                    return JSONResponse(
                        {"error": f"`{k}` must be a boolean."}, status_code=400
                    )
                setattr(cfg, k, v)
            else:
                return JSONResponse(
                    {"error": f"Unknown or read-only config key '{k}'."}, status_code=400
                )
        store.save_config(todo_path, cfg)
        return JSONResponse(
            {
                "show_gantt": cfg.show_gantt,
                "show_calendar": cfg.show_calendar,
                "show_weekends": cfg.show_weekends,
                "show_dates": cfg.show_dates,
            }
        )

    async def post_note(request: Request) -> Response:
        note_id = request.path_params["note_id"]
        body = await request.body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON body."}, status_code=400)
        if "content" not in data or not isinstance(data["content"], str):
            return JSONResponse(
                {"error": "Expected JSON body {\"content\": string}."}, status_code=400
            )

        text = todo_path.read_text(encoding="utf-8")
        try:
            new_text = writer_mod.set_note_content(text, note_id, data["content"])
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except KeyError:
            return JSONResponse({"error": f"No note with id '{note_id}'."}, status_code=404)
        todo_path.write_text(new_text, encoding="utf-8")
        doc = _reload(todo_path)
        return JSONResponse(_serialise(doc, todo_path))

    async def post_remove_note(request: Request) -> Response:
        note_id = request.path_params["note_id"]
        text = todo_path.read_text(encoding="utf-8")
        try:
            new_text = writer_mod.remove_note(text, note_id)
        except KeyError:
            return JSONResponse({"error": f"No note with id '{note_id}'."}, status_code=404)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        todo_path.write_text(new_text, encoding="utf-8")
        doc = _reload(todo_path)
        return JSONResponse(_serialise(doc, todo_path))

    routes = [
        Route("/", index),
        Route("/api/tasks", get_tasks),
        Route("/api/refresh", post_refresh, methods=["POST"]),
        Route("/api/events", get_events),
        Route("/api/tasks/reorder", post_reorder, methods=["POST"]),
        Route("/api/tasks/{hash}/dates", post_dates, methods=["POST"]),
        Route("/api/tasks/{hash}/done", post_done, methods=["POST"]),
        Route("/api/tasks/{hash}/description", post_description, methods=["POST"]),
        Route("/api/tasks/{hash}/remove", post_remove_task, methods=["POST"]),
        Route("/api/notes/{note_id}/content", post_note, methods=["POST"]),
        Route("/api/notes/{note_id}/remove", post_remove_note, methods=["POST"]),
        Route("/api/config", post_config, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
    ]

    return Starlette(routes=routes)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run(
    todo_path: Path,
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_browser: bool = True,
) -> None:
    if port is None:
        port = _find_free_port()

    app = build_app(todo_path)
    url = f"http://{host}:{port}"

    print(f"tsk: serving {todo_path}")
    print(f"tsk: open {url}")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    print("tsk: stopped")
