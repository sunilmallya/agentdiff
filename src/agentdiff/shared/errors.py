"""Fail-open error handling."""

from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar, Callable, Optional

T = TypeVar("T")


def fail_open(fn: Callable[[], T], context: str, fallback: T, project_root: Optional[str] = None) -> T:
    """Execute fn. On any error, log and return fallback."""
    try:
        return fn()
    except Exception as e:
        log_error(context, e, project_root=project_root)
        return fallback


def log_error(context: str, error: Exception, project_root: Optional[str] = None) -> None:
    """Append error to .agentdiff/errors.log."""
    try:
        if project_root is None:
            from agentdiff.shared.paths import find_project_root
            project_root = find_project_root(".")
        log_path = Path(project_root) / ".agentdiff" / "errors.log"
        ts = datetime.now(timezone.utc).isoformat()
        line = f"[{ts}] {context}: {error}\n"
        with open(log_path, "a") as f:
            f.write(line)
    except Exception:
        pass  # if we can't even log, silently continue
