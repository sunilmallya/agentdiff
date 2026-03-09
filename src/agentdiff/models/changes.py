"""ChangeRecord — one line in changes.jsonl. The core data unit."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal
import time
import uuid


def _ulid_like() -> str:
    """Time-sortable unique ID."""
    ts = int(time.time() * 1000)
    return f"{ts:013x}-{uuid.uuid4().hex[:8]}"


@dataclass
class ChangeRecord:
    """One line in changes.jsonl."""
    change_id: str = field(default_factory=_ulid_like)
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""

    # What changed
    file_path: str = ""
    tool_name: str = "Write"  # "Write" or "Edit"
    content: Optional[str] = None       # Write: full file content
    old_string: Optional[str] = None    # Edit: before
    new_string: Optional[str] = None    # Edit: after

    # Why it changed
    prompt: str = ""
    reasoning: str = ""

    # Task context
    task_id: str = ""
    task_subject: str = ""
    task_description: str = ""

    # Spec link
    spec_section: str = ""

    # Provenance
    provenance: str = "agent"  # "agent" or "human"

    # Scope
    in_scope: Optional[bool] = None
    scope_files: list[str] = field(default_factory=list)
