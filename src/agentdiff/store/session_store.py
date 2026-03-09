"""Per-session state management with file locking."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from agentdiff.models.session import SessionState
from agentdiff.models.tasks import TaskState
from agentdiff.shared.paths import get_session_dir


def ensure_session_dir(project_root: str, session_id: str) -> Path:
    session_dir = get_session_dir(project_root, session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _safe_dataclass_from_dict(cls, data: dict):
    """Construct a dataclass, ignoring unknown keys."""
    known = {f.name for f in cls.__dataclass_fields__.values()}
    return cls(**{k: v for k, v in data.items() if k in known})


def _atomic_write(path: Path, content: str) -> None:
    """Write atomically via temp file + rename."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, content.encode())
        os.close(fd)
        fd = -1  # mark as closed
        os.replace(tmp, str(path))
    except Exception:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class SessionLock:
    """File-based lock for session state. Use as context manager."""

    def __init__(self, project_root: str, session_id: str):
        session_dir = ensure_session_dir(project_root, session_id)
        self._lock_path = session_dir / ".lock"
        self._fd = None

    def __enter__(self):
        self._fd = open(self._lock_path, "w")
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *args):
        if self._fd:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()


def load_session_state(project_root: str, session_id: str) -> SessionState:
    state_path = get_session_dir(project_root, session_id) / "state.json"
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text())
            return _safe_dataclass_from_dict(SessionState, data)
        except (json.JSONDecodeError, TypeError):
            return SessionState(session_id=session_id)
    return SessionState(session_id=session_id)


def save_session_state(project_root: str, session_id: str, state: SessionState) -> None:
    session_dir = ensure_session_dir(project_root, session_id)
    state_path = session_dir / "state.json"
    _atomic_write(state_path, json.dumps(asdict(state), default=str))


def load_task_state(project_root: str, session_id: str, task_id: str) -> TaskState | None:
    tasks_dir = get_session_dir(project_root, session_id) / "tasks"
    task_path = tasks_dir / f"{task_id}.json"
    if task_path.exists():
        try:
            data = json.loads(task_path.read_text())
            return _safe_dataclass_from_dict(TaskState, data)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def save_task_state(project_root: str, session_id: str, task: TaskState) -> None:
    tasks_dir = get_session_dir(project_root, session_id) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_path = tasks_dir / f"{task.task_id}.json"
    _atomic_write(task_path, json.dumps(asdict(task), default=str))
