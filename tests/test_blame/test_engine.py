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


def test_find_content_lines_fuzzy_after_human_insert():
    """Lines still match after a human inserts a line into an agent block."""
    # Agent wrote "line 1\nline 2\nline 3", then human inserted a line
    file_lines = ["line 0", "line 1", "human added this", "line 2", "line 3"]
    result = _find_content_lines(file_lines, "line 1\nline 2\nline 3")
    assert 1 in result  # "line 1" still matches
    assert 3 in result  # "line 2" at new position
    assert 4 in result  # "line 3" at new position
    assert 2 not in result  # human-inserted line should NOT match


def test_find_content_lines_fuzzy_after_human_edit():
    """Unmodified lines keep attribution when human edits one line in block."""
    file_lines = ["def foo():", "    x = 1", "    y = CHANGED", "    return x"]
    result = _find_content_lines(file_lines, "def foo():\n    x = 1\n    y = 2\n    return x")
    assert 0 in result  # "def foo():" unchanged
    assert 1 in result  # "    x = 1" unchanged
    assert 3 in result  # "    return x" unchanged
    assert 2 not in result  # "    y = CHANGED" was modified by human


def test_find_content_lines_duplicate_lines():
    """Common lines like 'return None' should match in contiguous blocks, not scattered."""
    file_lines = [
        "def foo():",
        "    return None",
        "",
        "def bar():",
        "    return None",
    ]
    # Edit was for the foo() function — should match the first contiguous block
    result = _find_content_lines(file_lines, "def foo():\n    return None")
    assert 0 in result  # "def foo():"
    assert 1 in result  # first "return None"
    # Should NOT match the second "return None" in bar()
    assert 4 not in result


def test_find_content_lines_trailing_newline():
    """Trailing newline in content should still match via fast path."""
    file_lines = ["line 0", "line 1", "line 2"]
    result = _find_content_lines(file_lines, "line 1\nline 2\n")
    assert result == [1, 2]


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


def test_blame_consecutive_writes(project_dir):
    """Unchanged lines keep attribution from the Write that introduced them."""
    target = project_dir / "test.py"
    target.write_text("line1\nchanged\nline3\n")

    now = time.time()
    changes = [
        ChangeRecord(
            change_id="c1", timestamp=now - 10, session_id="sess-1",
            file_path=str(target), tool_name="Write",
            content="line1\nline2\nline3\n",
            prompt="create file", provenance="agent",
        ),
        ChangeRecord(
            change_id="c2", timestamp=now - 5, session_id="sess-1",
            file_path=str(target), tool_name="Write",
            content="line1\nchanged\nline3\n",
            prompt="update file", provenance="agent",
        ),
    ]
    _setup_changes(project_dir, changes)

    blame = blame_file(str(project_dir), str(target))
    assert len(blame) == 3
    # line1 and line3 unchanged — should keep c1 attribution
    assert blame[0].change.change_id == "c1"
    assert blame[2].change.change_id == "c1"
    # "changed" was introduced by c2
    assert blame[1].change.change_id == "c2"


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


def test_blame_edit_survives_human_insert(project_dir):
    """Agent attribution persists when human inserts a line into an edited block."""
    # Current file has a human-inserted line between agent-written lines
    target = project_dir / "test.py"
    target.write_text("def foo():\n    x = 1\n    # human added\n    return x\n")

    now = time.time()
    changes = [
        ChangeRecord(
            change_id="c1", timestamp=now - 10, session_id="sess-1",
            file_path=str(target), tool_name="Edit",
            old_string="pass", new_string="def foo():\n    x = 1\n    return x",
            prompt="implement foo", reasoning="Added function", provenance="agent",
        ),
    ]
    _setup_changes(project_dir, changes)

    blame = blame_file(str(project_dir), str(target))
    # Agent-written lines should keep attribution
    assert blame[0].change is not None  # "def foo():"
    assert blame[0].change.change_id == "c1"
    assert blame[1].change is not None  # "    x = 1"
    assert blame[1].change.change_id == "c1"
    assert blame[3].change is not None  # "    return x"
    assert blame[3].change.change_id == "c1"
    # Human-inserted line should NOT have agent attribution
    assert blame[2].change is None  # "    # human added"


def test_blame_no_changes(project_dir):
    target = project_dir / "test.py"
    target.write_text("hello\n")
    blame = blame_file(str(project_dir), str(target))
    assert len(blame) == 1
    assert blame[0].change is None


def test_blame_no_git_repo_graceful(project_dir):
    """In a non-git directory, git_info should be None — no errors."""
    target = project_dir / "test.py"
    target.write_text("hello\nworld\n")
    blame = blame_file(str(project_dir), str(target))
    assert len(blame) == 2
    for bl in blame:
        assert bl.change is None
        assert bl.git_info is None


def test_get_uncommitted_lines_not_git_repo(tmp_path):
    """_get_uncommitted_lines returns {} for files outside a git repo."""
    from agentdiff.blame.engine import _get_uncommitted_lines
    target = tmp_path / "test.py"
    target.write_text("hello\n")
    result = _get_uncommitted_lines(str(target))
    assert result == {}


def test_get_uncommitted_lines_in_git_repo(tmp_path):
    """_get_uncommitted_lines detects modified lines in a git repo."""
    import subprocess
    from agentdiff.blame.engine import _get_uncommitted_lines

    # Set up a git repo
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

    target = tmp_path / "test.py"
    target.write_text("line1\nline2\nline3\n")
    subprocess.run(["git", "add", "test.py"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(tmp_path), capture_output=True)

    # Make an uncommitted change
    target.write_text("line1\nmodified_line2\nline3\n")

    result = _get_uncommitted_lines(str(target))
    # Line 2 should be detected as uncommitted
    assert 2 in result
    assert result[2].commit_hash == "uncommitted"
    assert result[2].author == "Test"
    # Line 1 and 3 should NOT be in the result
    assert 1 not in result
    assert 3 not in result
