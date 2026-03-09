"""Daemon lifecycle: start, stop, health check, PID management."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from agentdiff.shared.paths import get_pid_path, get_socket_path


def start_daemon(project_root: str) -> int:
    """Start daemon as a detached subprocess. Returns PID."""
    if is_daemon_running(project_root):
        pid_path = get_pid_path(project_root)
        return _read_pid(pid_path)

    _cleanup_stale(project_root)

    log_path = Path(project_root) / ".agentdiff" / "daemon.log"
    log_file = open(str(log_path), "a")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "agentdiff.daemon.server", "--project-root", project_root],
            stdout=subprocess.DEVNULL,
            stderr=log_file,
            start_new_session=True,
        )
    finally:
        log_file.close()

    # Wait for socket to appear (up to 2s)
    sock_path = get_socket_path(project_root)
    for _ in range(20):
        if sock_path.exists():
            return proc.pid
        # Check if process died
        if proc.poll() is not None:
            break
        time.sleep(0.1)

    return proc.pid


def stop_daemon(project_root: str) -> bool:
    """Stop daemon gracefully. Returns True if stopped."""
    pid_path = get_pid_path(project_root)
    if not pid_path.exists():
        _cleanup_stale(project_root)
        return False

    try:
        pid = _read_pid(pid_path)
    except (ValueError, FileNotFoundError):
        _cleanup_stale(project_root)
        return False

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break
    except ProcessLookupError:
        pass

    _cleanup_stale(project_root)
    return True


def is_daemon_running(project_root: str) -> bool:
    """Check if daemon is alive."""
    pid_path = get_pid_path(project_root)
    if not pid_path.exists():
        return False
    try:
        pid = _read_pid(pid_path)
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, ValueError, FileNotFoundError):
        return False


def _read_pid(pid_path: Path) -> int:
    text = pid_path.read_text().strip()
    if not text:
        raise ValueError("empty PID file")
    return int(text)


def _cleanup_stale(project_root: str):
    pid_path = get_pid_path(project_root)
    sock_path = get_socket_path(project_root)
    try:
        if pid_path.exists():
            pid_path.unlink()
    except OSError:
        pass
    try:
        if sock_path.exists():
            sock_path.unlink()
    except OSError:
        pass
