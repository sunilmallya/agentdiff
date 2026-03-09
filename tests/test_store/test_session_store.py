"""Test session and task state persistence."""

from agentdiff.models.session import SessionState
from agentdiff.models.tasks import TaskState
from agentdiff.store.session_store import (
    ensure_session_dir, load_session_state, save_session_state,
    load_task_state, save_task_state,
)


def test_session_state_roundtrip(project_dir):
    state = SessionState(session_id="s1", cwd="/tmp", status="active")
    save_session_state(str(project_dir), "s1", state)
    loaded = load_session_state(str(project_dir), "s1")
    assert loaded.session_id == "s1"
    assert loaded.status == "active"


def test_task_state_roundtrip(project_dir):
    task = TaskState(task_id="t1", session_id="s1", prompt="fix the bug")
    save_task_state(str(project_dir), "s1", task)
    loaded = load_task_state(str(project_dir), "s1", "t1")
    assert loaded is not None
    assert loaded.prompt == "fix the bug"


def test_missing_task_returns_none(project_dir):
    assert load_task_state(str(project_dir), "s1", "nonexistent") is None


def test_session_defaults(project_dir):
    state = load_session_state(str(project_dir), "new-session")
    assert state.session_id == "new-session"
    assert state.status == "active"
