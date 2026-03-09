"""Dataclasses for Claude Code hook event payloads (received on stdin)."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HookInput:
    """Common fields on every hook event."""
    session_id: str = ""
    transcript_path: str = ""
    cwd: str = ""
    hook_event_name: str = ""

    @classmethod
    def from_dict(cls, data: dict):
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class PostToolUseInput(HookInput):
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    tool_response: dict = field(default_factory=dict)


@dataclass
class SessionStartInput(HookInput):
    source: str = "startup"


@dataclass
class SubagentStartInput(HookInput):
    agent_id: str = ""
    agent_type: str = ""


@dataclass
class SubagentStopInput(HookInput):
    agent_id: str = ""
    agent_type: str = ""
    last_assistant_message: str = ""


@dataclass
class TaskCompletedInput(HookInput):
    task_id: str = ""
    task_subject: str = ""
    task_description: str = ""


@dataclass
class StopInput(HookInput):
    stop_hook_active: bool = False
    last_assistant_message: str = ""
