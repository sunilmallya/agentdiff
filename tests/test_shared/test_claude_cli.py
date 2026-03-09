"""Test Claude CLI helper."""

import json
import subprocess
from unittest.mock import patch, MagicMock

from agentdiff.shared.claude_cli import ask_claude, ask_claude_json


def test_ask_claude_basic():
    """Successful call returns stdout."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Here is the summary of changes.\n"

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        result = ask_claude("summarize this")

    assert result == "Here is the summary of changes."
    args = mock_run.call_args
    cmd = args[0][0]
    assert "-p" in cmd
    assert "summarize this" in cmd
    assert "--model" in cmd
    assert "--no-session-persistence" in cmd


def test_ask_claude_no_binary():
    """Returns empty string when claude binary is not found."""
    with patch("shutil.which", return_value=None):
        result = ask_claude("test prompt")
    assert result == ""


def test_ask_claude_timeout():
    """Returns empty string on timeout."""
    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 30)):
        result = ask_claude("test prompt")
    assert result == ""


def test_ask_claude_nonzero_exit():
    """Returns empty string on non-zero exit code."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "error"

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", return_value=mock_result):
        result = ask_claude("test prompt")
    assert result == ""


def test_ask_claude_json_output():
    """JSON output mode extracts the result field."""
    response = json.dumps({"result": "the answer", "session_id": "abc"})
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = response

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", return_value=mock_result):
        result = ask_claude("test", output_format="json")
    assert result == "the answer"


def test_ask_claude_json_structured():
    """ask_claude_json returns parsed dict."""
    schema = {"type": "object", "properties": {"section": {"type": "string"}}}
    response = json.dumps({"result": json.dumps({"section": "## Auth"}), "session_id": "x"})
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = response

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", return_value=mock_result):
        result = ask_claude_json("link to spec", schema)
    assert result == {"section": "## Auth"}


def test_ask_claude_json_failure():
    """ask_claude_json returns None on failure."""
    with patch("shutil.which", return_value=None):
        result = ask_claude_json("test", {"type": "object"})
    assert result is None


def test_ask_claude_model_and_turns():
    """Custom model and max_turns are passed through."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "ok"

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        ask_claude("test", model="sonnet", max_turns=3)

    cmd = mock_run.call_args[0][0]
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "sonnet"
    turns_idx = cmd.index("--max-turns")
    assert cmd[turns_idx + 1] == "3"
