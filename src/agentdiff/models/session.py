"""Per-session runtime state."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SessionState:
    session_id: str = ""
    transcript_path: str = ""
    cwd: str = ""
    started_at: float = 0.0
    status: str = "active"

    active_tasks: list[str] = field(default_factory=list)

    change_count: int = 0
    last_event_at: float = 0.0
