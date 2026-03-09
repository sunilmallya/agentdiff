"""End-to-end integration test.

Simulates a full Claude Code session:
  SessionStart → SubagentStart → PostToolUse (Write) → PostToolUse (Edit)
  → TaskCompleted → SubagentStop → Stop

Then verifies: change log, blame, log CLI, session state.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from agentdiff.daemon.handlers import handle_event
from agentdiff.store.change_log import read_changes, read_all_changes
from agentdiff.store.session_store import load_session_state, load_task_state
from agentdiff.blame.engine import blame_file
from agentdiff.cli.app import cli


SESSION_ID = "integ-session-001"
AGENT_ID = "agent-task-42"


def _fire(payload: dict, project_root: str) -> None:
    """Send an event through the handler, same as the daemon would."""
    handle_event(payload, project_root)


def _setup_transcript(tmp_path: Path) -> str:
    """Write a minimal transcript JSONL so prompt extraction works."""
    transcript = tmp_path / "transcript.jsonl"
    entries = [
        {"type": "user", "message": {"content": "add login endpoint with JWT"}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "I'll create the login endpoint."},
            {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "src/auth.py"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Now I'll add the algorithm parameter."},
            {"type": "tool_use", "id": "t2", "name": "Edit", "input": {"file_path": "src/auth.py"}},
        ]}},
    ]
    with open(transcript, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return str(transcript)


def test_full_session_flow(project_dir, tmp_path):
    """Simulate a complete session and verify the full pipeline."""
    root = str(project_dir)
    transcript_path = _setup_transcript(tmp_path)

    # Create the actual file the agent will "write"
    src_dir = project_dir / "src"
    src_dir.mkdir()
    auth_file = src_dir / "auth.py"

    # --- 1. SessionStart ---
    _fire({
        "hook_event_name": "SessionStart",
        "session_id": SESSION_ID,
        "transcript_path": transcript_path,
        "cwd": root,
    }, root)

    state = load_session_state(root, SESSION_ID)
    assert state.status == "active"
    assert state.session_id == SESSION_ID

    # --- 2. SubagentStart ---
    _fire({
        "hook_event_name": "SubagentStart",
        "session_id": SESSION_ID,
        "agent_id": AGENT_ID,
        "agent_type": "general-purpose",
        "transcript_path": transcript_path,
    }, root)

    state = load_session_state(root, SESSION_ID)
    assert AGENT_ID in state.active_tasks
    task = load_task_state(root, SESSION_ID, AGENT_ID)
    assert task is not None
    assert task.agent_type == "general-purpose"

    # --- 3. PostToolUse (Write) ---
    file_content = (
        "import jwt, os\n"
        "\n"
        "def login(email, password):\n"
        "    user = find_user(email)\n"
        "    token = jwt.encode({'user_id': user.id}, os.environ['SECRET'])\n"
        "    return {'token': token}\n"
    )
    _fire({
        "hook_event_name": "PostToolUse",
        "session_id": SESSION_ID,
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(auth_file),
            "content": file_content,
        },
        "transcript_path": transcript_path,
    }, root)

    # Write the file to disk so blame can read it later
    auth_file.write_text(file_content)

    changes = read_changes(root, SESSION_ID)
    assert len(changes) == 1
    assert changes[0].tool_name == "Write"
    assert changes[0].provenance == "agent"
    assert changes[0].task_id == AGENT_ID
    # Should be stored as relative path
    assert not Path(changes[0].file_path).is_absolute()

    # --- 4. PostToolUse (Edit) ---
    new_content = (
        "import jwt, os\n"
        "\n"
        "def login(email, password):\n"
        "    user = find_user(email)\n"
        "    token = jwt.encode({'user_id': user.id}, os.environ['SECRET'], algorithm='HS256')\n"
        "    return {'token': token}\n"
    )
    _fire({
        "hook_event_name": "PostToolUse",
        "session_id": SESSION_ID,
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(auth_file),
            "old_string": "    token = jwt.encode({'user_id': user.id}, os.environ['SECRET'])",
            "new_string": "    token = jwt.encode({'user_id': user.id}, os.environ['SECRET'], algorithm='HS256')",
        },
        "transcript_path": transcript_path,
    }, root)

    # Update the file on disk
    auth_file.write_text(new_content)

    changes = read_changes(root, SESSION_ID)
    assert len(changes) == 2
    assert changes[1].tool_name == "Edit"

    # --- 5. TaskCompleted ---
    _fire({
        "hook_event_name": "TaskCompleted",
        "session_id": SESSION_ID,
        "task_id": AGENT_ID,
        "task_subject": "Add JWT login",
        "task_description": "Create login endpoint that returns signed JWT tokens",
    }, root)

    task = load_task_state(root, SESSION_ID, AGENT_ID)
    assert task.task_subject == "Add JWT login"
    assert task.completed_at is not None

    # --- 6. SubagentStop ---
    _fire({
        "hook_event_name": "SubagentStop",
        "session_id": SESSION_ID,
        "agent_id": AGENT_ID,
        "last_assistant_message": "Done. Login endpoint created with JWT.",
    }, root)

    state = load_session_state(root, SESSION_ID)
    assert AGENT_ID not in state.active_tasks

    # --- 7. Stop (skip _enrich_reasoning which calls Claude CLI) ---
    with patch("agentdiff.daemon.handlers._enrich_reasoning"):
        _fire({
            "hook_event_name": "Stop",
            "session_id": SESSION_ID,
        }, root)

    state = load_session_state(root, SESSION_ID)
    assert state.status == "stopped"
    assert state.change_count == 2

    # --- Verify blame ---
    blame_lines = blame_file(root, str(auth_file))
    assert len(blame_lines) == 6  # 6 lines in the file

    # Line 5 was edited — should be attributed to the Edit
    line5 = blame_lines[4]
    assert line5.change is not None
    assert line5.change.tool_name == "Edit"
    assert line5.version == 2  # Write v1 + Edit v2

    # Line 1 was only written — should be attributed to the Write
    line1 = blame_lines[0]
    assert line1.change is not None
    assert line1.change.tool_name == "Write"

    # --- Verify read_all_changes ---
    all_changes = read_all_changes(root)
    assert len(all_changes) == 2

    # --- Verify CLI log output ---
    runner = CliRunner()
    with runner.isolated_filesystem():
        pass
    # Run from project dir
    result = runner.invoke(cli, ["log"], catch_exceptions=False,
                           env={"PWD": root})
    # log searches up from cwd; set it explicitly
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(root)
        result = runner.invoke(cli, ["log"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Edit" in result.output
        assert "Write" in result.output
    finally:
        os.chdir(old_cwd)

    # --- Verify CLI blame output ---
    try:
        os.chdir(root)
        result = runner.invoke(cli, ["blame", str(auth_file)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "agent" in result.output
        assert "user-prompt" in result.output or "human" in result.output
    finally:
        os.chdir(old_cwd)


def test_non_write_edit_events_ignored(project_dir):
    """PostToolUse for non-Write/Edit tools should be silently ignored."""
    root = str(project_dir)

    _fire({
        "hook_event_name": "SessionStart",
        "session_id": SESSION_ID,
        "cwd": root,
    }, root)

    _fire({
        "hook_event_name": "PostToolUse",
        "session_id": SESSION_ID,
        "tool_name": "Read",
        "tool_input": {"file_path": "/some/file.py"},
    }, root)

    changes = read_changes(root, SESSION_ID)
    assert len(changes) == 0


def test_missing_session_id_ignored(project_dir):
    """Events without session_id should be silently dropped."""
    root = str(project_dir)
    # Should not raise
    _fire({"hook_event_name": "SessionStart"}, root)
    _fire({"hook_event_name": "PostToolUse", "tool_name": "Write"}, root)
