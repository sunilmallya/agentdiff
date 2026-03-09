"""Shared test fixtures."""

import json
import time
from pathlib import Path

import pytest

from agentdiff.models.changes import ChangeRecord
from agentdiff.shared.paths import get_agentdiff_root


@pytest.fixture
def project_dir(tmp_path):
    """Temp directory with .agentdiff/ initialized."""
    agentdiff_dir = tmp_path / ".agentdiff"
    agentdiff_dir.mkdir()
    (agentdiff_dir / "sessions").mkdir()
    (agentdiff_dir / "config.yaml").write_text("# test config\n")
    return tmp_path


@pytest.fixture
def sample_changes(project_dir):
    """Pre-populate changes.jsonl with sample data."""
    session_id = "test-session-001"
    session_dir = project_dir / ".agentdiff" / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    changes = [
        ChangeRecord(
            change_id="001",
            timestamp=time.time() - 30,
            session_id=session_id,
            file_path=str(project_dir / "src" / "auth.py"),
            tool_name="Write",
            content="def validate_token(token):\n    return True\n",
            prompt="implement token validation",
            reasoning="Starting with a basic implementation",
            task_id="task-1",
            task_subject="auth refactor",
            provenance="agent",
        ),
        ChangeRecord(
            change_id="002",
            timestamp=time.time() - 20,
            session_id=session_id,
            file_path=str(project_dir / "src" / "auth.py"),
            tool_name="Edit",
            old_string="def validate_token(token):\n    return True",
            new_string="def validate_token(token, options=None):\n    if options is None:\n        options = {}\n    return check_hash(token)",
            prompt="implement token validation",
            reasoning="Switched to options parameter pattern",
            task_id="task-1",
            task_subject="auth refactor",
            provenance="agent",
        ),
    ]

    from dataclasses import asdict
    changes_path = session_dir / "changes.jsonl"
    with open(changes_path, "w") as f:
        for c in changes:
            f.write(json.dumps(asdict(c), default=str) + "\n")

    return changes


@pytest.fixture
def sample_transcript(tmp_path):
    """Write a JSONL transcript matching real Claude Code format."""
    transcript_path = tmp_path / "transcript.jsonl"
    entries = [
        {"type": "user", "message": {"content": "implement token validation for auth"}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "I'll implement the token validation.\n\nI'll add an options parameter to match the existing pattern in validateSession()."}
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "tool_1", "name": "Edit", "input": {"file_path": "src/auth.py"}}
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tool_1", "content": "success"}
        ]}},
    ]
    with open(transcript_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return str(transcript_path)
