"""Test append-only JSONL change log."""

from agentdiff.models.changes import ChangeRecord
from agentdiff.store.change_log import append_change, read_changes, read_all_changes, update_changes


def test_append_and_read(project_dir):
    session_id = "sess-1"
    r = ChangeRecord(session_id=session_id, file_path="test.py", tool_name="Write")
    append_change(str(project_dir), session_id, r)

    records = read_changes(str(project_dir), session_id)
    assert len(records) == 1
    assert records[0].file_path == "test.py"


def test_multiple_appends(project_dir):
    session_id = "sess-1"
    for i in range(5):
        r = ChangeRecord(session_id=session_id, file_path=f"file{i}.py")
        append_change(str(project_dir), session_id, r)

    records = read_changes(str(project_dir), session_id)
    assert len(records) == 5


def test_read_all_across_sessions(project_dir):
    for sid in ["sess-a", "sess-b"]:
        r = ChangeRecord(session_id=sid, file_path="x.py")
        append_change(str(project_dir), sid, r)

    all_records = read_all_changes(str(project_dir))
    assert len(all_records) == 2


def test_read_empty(project_dir):
    assert read_changes(str(project_dir), "nonexistent") == []
    assert read_all_changes(str(project_dir)) == []


def test_update_changes(project_dir):
    session_id = "sess-1"
    r = ChangeRecord(session_id=session_id, file_path="test.py", tool_name="Write", spec_section="")
    append_change(str(project_dir), session_id, r)

    # Update spec_section
    count = update_changes(str(project_dir), {r.change_id: {"spec_section": "## Auth"}})
    assert count == 1

    # Verify it persisted
    records = read_changes(str(project_dir), session_id)
    assert records[0].spec_section == "## Auth"


def test_update_changes_no_match(project_dir):
    session_id = "sess-1"
    r = ChangeRecord(session_id=session_id, file_path="test.py")
    append_change(str(project_dir), session_id, r)

    count = update_changes(str(project_dir), {"nonexistent-id": {"spec_section": "## Auth"}})
    assert count == 0
