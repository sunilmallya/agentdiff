"""Resolve .agentdiff/ paths."""

from __future__ import annotations

from pathlib import Path


def get_agentdiff_root(project_root: str) -> Path:
    return Path(project_root) / ".agentdiff"


def get_session_dir(project_root: str, session_id: str) -> Path:
    # Sanitize session_id to prevent path traversal
    safe_id = session_id.replace("/", "_").replace("..", "_").replace("\\", "_")
    return get_agentdiff_root(project_root) / "sessions" / safe_id


def get_socket_path(project_root: str) -> Path:
    return get_agentdiff_root(project_root) / "daemon.sock"


def get_pid_path(project_root: str) -> Path:
    return get_agentdiff_root(project_root) / "daemon.pid"


def find_project_root(start: Path | str) -> str:
    """Walk up from start to find directory containing .agentdiff/."""
    current = Path(start).resolve()
    while current != current.parent:
        if (current / ".agentdiff").is_dir():
            return str(current)
        current = current.parent
    raise FileNotFoundError(
        "No .agentdiff/ directory found. Run 'agentdiff init' first."
    )
