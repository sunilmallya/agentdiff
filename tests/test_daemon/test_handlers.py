"""Test daemon event handlers."""

import time

from agentdiff.daemon.handlers import handle_event
from agentdiff.store.change_log import read_changes
from agentdiff.store.session_store import load_session_state, load_task_state


def test_session_start(project_dir):
    handle_event({
        "hook_event_name": "SessionStart",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
    }, str(project_dir))

    state = load_session_state(str(project_dir), "sess-1")
    assert state.session_id == "sess-1"
    assert state.status == "active"


def test_post_tool_use_write(project_dir):
    # First create session
    handle_event({
        "hook_event_name": "SessionStart",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
    }, str(project_dir))

    handle_event({
        "hook_event_name": "PostToolUse",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "src/auth.py",
            "content": "def hello(): pass",
        },
    }, str(project_dir))

    changes = read_changes(str(project_dir), "sess-1")
    assert len(changes) == 1
    assert changes[0].file_path == "src/auth.py"
    assert changes[0].tool_name == "Write"
    assert changes[0].provenance == "agent"


def test_post_tool_use_edit(project_dir):
    handle_event({
        "hook_event_name": "SessionStart",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
    }, str(project_dir))

    handle_event({
        "hook_event_name": "PostToolUse",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "src/auth.py",
            "old_string": "foo",
            "new_string": "bar",
        },
    }, str(project_dir))

    changes = read_changes(str(project_dir), "sess-1")
    assert len(changes) == 1
    assert changes[0].old_string == "foo"
    assert changes[0].new_string == "bar"


def test_post_tool_use_ignores_non_write_edit(project_dir):
    handle_event({
        "hook_event_name": "SessionStart",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
    }, str(project_dir))

    handle_event({
        "hook_event_name": "PostToolUse",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }, str(project_dir))

    changes = read_changes(str(project_dir), "sess-1")
    assert len(changes) == 0


def test_subagent_start_stop(project_dir):
    handle_event({
        "hook_event_name": "SessionStart",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
    }, str(project_dir))

    handle_event({
        "hook_event_name": "SubagentStart",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
        "agent_id": "agent-42",
        "agent_type": "general-purpose",
    }, str(project_dir))

    state = load_session_state(str(project_dir), "sess-1")
    assert "agent-42" in state.active_tasks

    handle_event({
        "hook_event_name": "SubagentStop",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
        "agent_id": "agent-42",
        "last_assistant_message": "Done with the task.",
    }, str(project_dir))

    state = load_session_state(str(project_dir), "sess-1")
    assert "agent-42" not in state.active_tasks

    task = load_task_state(str(project_dir), "sess-1", "agent-42")
    assert task is not None
    assert task.completed_at is not None


def test_stop_finalizes(project_dir):
    handle_event({
        "hook_event_name": "SessionStart",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
    }, str(project_dir))

    handle_event({
        "hook_event_name": "Stop",
        "session_id": "sess-1",
        "cwd": str(project_dir),
        "transcript_path": "",
    }, str(project_dir))

    state = load_session_state(str(project_dir), "sess-1")
    assert state.status == "stopped"
    assert state.active_tasks == []
