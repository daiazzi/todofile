from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import store


def _pid_file(todo_path: Path) -> Path:
    return store.sidecar_dir(todo_path) / "daemon.pid"


def _url_file(todo_path: Path) -> Path:
    return store.sidecar_dir(todo_path) / "daemon.url"


def _log_file(todo_path: Path) -> Path:
    return store.sidecar_dir(todo_path) / "daemon.log"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_status(todo_path: Path) -> tuple[int | None, str | None]:
    """Return (pid, url) if a daemon appears to be running, else (None, None)."""
    pf = _pid_file(todo_path)
    if not pf.exists():
        return None, None
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        return None, None
    if not _pid_alive(pid):
        return None, None
    url = None
    uf = _url_file(todo_path)
    if uf.exists():
        url = uf.read_text().strip()
    return pid, url


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(todo_path: Path, *, host: str = "127.0.0.1", port: int | None = None) -> tuple[int, str]:
    """Spawn the server in a detached process. Returns (pid, url)."""
    existing_pid, existing_url = read_status(todo_path)
    if existing_pid is not None:
        raise RuntimeError(f"daemon already running (pid {existing_pid}) at {existing_url}")

    store.ensure_sidecar(todo_path)

    if port is None:
        cfg = store.load_config(todo_path)
        port = cfg.port or _find_free_port()

    log = open(_log_file(todo_path), "ab", buffering=0)
    cmd = [
        sys.executable,
        "-m",
        "todofile.cli",
        "serve",
        "--file", str(todo_path),
        "--no-browser",
        "--host",
        host,
        "--port",
        str(port),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    url = f"http://{host}:{port}"
    _pid_file(todo_path).write_text(f"{proc.pid}\n")
    _url_file(todo_path).write_text(f"{url}\n")

    # Give the child a moment to fail-fast if something is wrong (e.g., port in use).
    time.sleep(0.3)
    if proc.poll() is not None:
        _pid_file(todo_path).unlink(missing_ok=True)
        _url_file(todo_path).unlink(missing_ok=True)
        raise RuntimeError(f"daemon exited immediately; see {_log_file(todo_path)}")
    return proc.pid, url


def stop(todo_path: Path, *, timeout: float = 5.0) -> int | None:
    """Send SIGTERM to the daemon. Returns the killed pid, or None if not running."""
    pid, _ = read_status(todo_path)
    if pid is None:
        _pid_file(todo_path).unlink(missing_ok=True)
        _url_file(todo_path).unlink(missing_ok=True)
        return None
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid = None
    if pid is not None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not _pid_alive(pid):
                break
            time.sleep(0.05)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    _pid_file(todo_path).unlink(missing_ok=True)
    _url_file(todo_path).unlink(missing_ok=True)
    return pid
