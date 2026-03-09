"""Task boundary state."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class TaskState:
    """Represents an active or completed task boundary."""
    task_id: str = ""
    session_id: str = ""
    agent_type: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    prompt: str = ""
    task_subject: str = ""
    task_description: str = ""
    last_assistant_message: str = ""

    scope_files: list[str] = field(default_factory=list)
    spec_section: str = ""
    change_count: int = 0
