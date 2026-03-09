"""Test blame engine content matching."""

import json
import time
from dataclasses import asdict
from pathlib import Path

from agentdiff.blame.engine import blame_file, blame_line_history, _find_content_lines
from agentdiff.models.changes import ChangeRecord


def _setup_changes(project_dir, changes):
    """Helper to write changes to JSONL."""
    session_dir = project_dir / ".agentdiff" / "sessions" / "sess-1"
    session_dir.mkdir(parents=True, exist_ok=True)
    with open(session_dir / "changes.jsonl", "w") as f:
        for c in changes:
            f.write(json.dumps(asdict(c), default=str) + "\n")


def test_find_content_lines():
    file_lines = ["line 0", "line 1", "line 2", "line 3"]
    assert _find_content_lines(file_lines, "line 1") == [1]
    assert _find_content_lines(file_lines, "line 1\nline 2") == [1, 2]
    assert _find_content_lines(file_lines, "nonexistent") == []


def test_blame_write(project_dir):
    target = project_dir / "test.py"
    target.write_text("line1\nline2\nline3\n")

    changes = [
        ChangeRecord(
            change_id="c1", timestamp=time.time(), session_id="sess-1",
            file_path=str(target), tool_name="Write",
            content="line1\nline2\nline3\n",
            prompt="create the file", provenance="agent",
        ),
    ]
    _setup_changes(project_dir, changes)

    blame = blame_file(str(project_dir), str(target))
    assert len(blame) == 3
    assert blame[0].change is not None
    assert blame[0].change.change_id == "c1"
    assert blame[0].version == 1


def test_blame_edit_overrides(project_dir):
    target = project_dir / "test.py"
    target.write_text("def foo():\n    return bar\n")

    now = time.time()
    changes = [
        ChangeRecord(
            change_id="c1", timestamp=now - 10, session_id="sess-1",
            file_path=str(target), tool_name="Write",
            content="def foo():\n    return baz\n",
            prompt="create", provenance="agent",
        ),
        ChangeRecord(
            change_id="c2", timestamp=now - 5, session_id="sess-1",
            file_path=str(target), tool_name="Edit",
            old_string="return baz", new_string="return bar",
            prompt="fix", reasoning="Changed return value", provenance="agent",
        ),
    ]
    _setup_changes(project_dir, changes)

    blame = blame_file(str(project_dir), str(target))
    # "return bar" line should be attributed to edit c2
    return_line = [bl for bl in blame if "return bar" in bl.content][0]
    assert return_line.change.change_id == "c2"
    assert return_line.version == 2


def test_blame_line_history(project_dir):
    target = project_dir / "test.py"
    target.write_text("def foo():\n    return bar\n")

    now = time.time()
    changes = [
        ChangeRecord(
            change_id="c1", timestamp=now - 10, session_id="sess-1",
            file_path=str(target), tool_name="Write",
            content="def foo():\n    return baz\n",
            prompt="create", provenance="agent",
        ),
        ChangeRecord(
            change_id="c2", timestamp=now - 5, session_id="sess-1",
            file_path=str(target), tool_name="Edit",
            old_string="return baz", new_string="return bar",
            prompt="fix", provenance="agent",
        ),
    ]
    _setup_changes(project_dir, changes)

    hist = blame_line_history(str(project_dir), str(target), 2)
    assert len(hist.versions) == 2
    assert hist.versions[0].change_id == "c1"
    assert hist.versions[1].change_id == "c2"


def test_blame_no_changes(project_dir):
    target = project_dir / "test.py"
    target.write_text("hello\n")
    blame = blame_file(str(project_dir), str(target))
    assert len(blame) == 1
    assert blame[0].change is None
