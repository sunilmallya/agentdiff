"""Tests for agentdiff tour command."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from click.testing import CliRunner

from agentdiff.cli.app import cli
from agentdiff.models.changes import ChangeRecord


def _populate_session(project_dir: Path, session_id: str = "tour-test-001"):
    """Create a session with changes and matching files on disk."""
    session_dir = project_dir / ".agentdiff" / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create the target file
    src_dir = project_dir / "src"
    src_dir.mkdir(exist_ok=True)
    auth_file = src_dir / "auth.py"
    auth_file.write_text(
        "import jwt\n"
        "\n"
        "def login(email, password):\n"
        "    user = find_user(email)\n"
        "    token = jwt.encode({'id': user.id}, 'secret', algorithm='HS256')\n"
        "    return {'token': token}\n"
    )

    changes = [
        ChangeRecord(
            change_id="t001",
            timestamp=time.time() - 60,
            session_id=session_id,
            file_path="src/auth.py",
            tool_name="Write",
            content="import jwt\n\ndef login(email, password):\n    user = find_user(email)\n    token = jwt.encode({'id': user.id}, 'secret')\n    return {'token': token}\n",
            prompt="add login endpoint with JWT",
            reasoning="Created login function with JWT token generation.",
            provenance="agent",
        ),
        ChangeRecord(
            change_id="t002",
            timestamp=time.time() - 30,
            session_id=session_id,
            file_path="src/auth.py",
            tool_name="Edit",
            old_string="token = jwt.encode({'id': user.id}, 'secret')",
            new_string="token = jwt.encode({'id': user.id}, 'secret', algorithm='HS256')",
            prompt="add login endpoint with JWT",
            reasoning="Pinned algorithm to HS256 to prevent confusion attacks.",
            provenance="agent",
        ),
    ]

    changes_path = session_dir / "changes.jsonl"
    with open(changes_path, "w") as f:
        for c in changes:
            f.write(json.dumps(asdict(c), default=str) + "\n")

    return changes


def test_tour_generates_file(project_dir):
    """Tour command should create a .tour file."""
    _populate_session(project_dir)
    runner = CliRunner()

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        result = runner.invoke(cli, ["tour"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Tour written" in result.output
        assert "2 steps" in result.output

        # Verify tour file exists
        tour_files = list((project_dir / ".tours").glob("*.tour"))
        assert len(tour_files) == 1

        # Verify tour content
        tour = json.loads(tour_files[0].read_text())
        assert tour["$schema"] == "https://aka.ms/codetour-schema"
        assert "AgentDiff" in tour["title"]
        assert len(tour["steps"]) == 2

        # First step: Write
        step0 = tour["steps"][0]
        assert step0["file"] == "src/auth.py"
        assert "Created file" in step0["description"]
        assert "user-prompt" in step0["description"]
        assert step0["line"] == 1

        # Second step: Edit with diff
        step1 = tour["steps"][1]
        assert step1["file"] == "src/auth.py"
        assert "```diff" in step1["description"]
        assert "algorithm='HS256'" in step1["description"]
        assert step1["line"] == 5  # Line where the edit landed
    finally:
        os.chdir(old_cwd)


def test_tour_session_filter(project_dir):
    """--session flag should filter changes."""
    _populate_session(project_dir, "session-a")
    _populate_session(project_dir, "session-b")
    runner = CliRunner()

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        result = runner.invoke(cli, ["tour", "--session", "session-a"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "2 steps" in result.output

        tour_files = list((project_dir / ".tours").glob("*.tour"))
        assert len(tour_files) == 1
        tour = json.loads(tour_files[0].read_text())
        # All steps should be from session-a only
        assert len(tour["steps"]) == 2
    finally:
        os.chdir(old_cwd)


def test_tour_no_changes(project_dir):
    """Tour with no changes should show message."""
    runner = CliRunner()

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        result = runner.invoke(cli, ["tour"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No changes to tour" in result.output
    finally:
        os.chdir(old_cwd)


def test_tour_custom_output(project_dir):
    """--output flag should write to specified path."""
    _populate_session(project_dir)
    runner = CliRunner()
    out_path = str(project_dir / "my-tour.tour")

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        result = runner.invoke(cli, ["tour", "-o", out_path], catch_exceptions=False)
        assert result.exit_code == 0
        assert Path(out_path).exists()
        tour = json.loads(Path(out_path).read_text())
        assert len(tour["steps"]) == 2
    finally:
        os.chdir(old_cwd)
