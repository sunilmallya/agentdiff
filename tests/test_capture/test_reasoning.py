"""Test reasoning extraction from transcripts."""

import json
from pathlib import Path

from agentdiff.capture.reasoning import (
    extract_reasoning, read_transcript_tail,
    extract_post_tool_summaries, _is_substantive_summary,
)


def test_extract_reasoning_basic(sample_transcript):
    reasoning = extract_reasoning(sample_transcript)
    assert "options parameter" in reasoning


def test_extract_reasoning_last_paragraph(tmp_path):
    transcript = tmp_path / "t.jsonl"
    entries = [
        {"type": "user", "message": {"content": "fix the auth"}},
        {"type": "assistant", "message": {"content": "First paragraph about context.\n\nSecond paragraph with the actual plan to use options."}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Edit", "input": {}}
        ]}},
    ]
    with open(transcript, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    reasoning = extract_reasoning(str(transcript))
    assert "actual plan" in reasoning
    assert "First paragraph" not in reasoning


def test_extract_reasoning_no_transcript():
    assert extract_reasoning("/nonexistent/path.jsonl") == ""


def test_read_transcript_tail(sample_transcript):
    entries = read_transcript_tail(sample_transcript, max_lines=10)
    assert len(entries) == 4
    assert entries[0]["type"] == "user"


def test_extract_reasoning_content_as_list(tmp_path):
    """Text and tool_use in the same assistant entry."""
    transcript = tmp_path / "t.jsonl"
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "I'll refactor the function.\n\nUsing options pattern for flexibility."},
            {"type": "tool_use", "id": "t1", "name": "Edit", "input": {}}
        ]}},
    ]
    with open(transcript, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    reasoning = extract_reasoning(str(transcript))
    assert "options pattern" in reasoning


def test_is_substantive_summary():
    """Transition text should be filtered out, summaries kept."""
    # Transitions — not substantive
    assert not _is_substantive_summary("Now let me update the README to document the new usage.")
    assert not _is_substantive_summary("Let me also fix the tests.")
    assert not _is_substantive_summary("Next I'll add error handling.")
    assert not _is_substantive_summary("I'll now update the config.")

    # Summaries — substantive
    assert _is_substantive_summary("Changes made:\n\n1. Removed hardcoded API key\n2. Added env var lookup")
    assert _is_substantive_summary("I've updated the authentication to use bearer tokens.")
    assert _is_substantive_summary("Done. Here's what changed:\n\n- MODELS dict maps short names")
    assert _is_substantive_summary("Added model selection support with a configurable MODELS dictionary.")


def test_post_tool_summary_mixed_entry(tmp_path):
    """Summary text before tool_use in a mixed entry should be captured."""
    transcript = tmp_path / "t.jsonl"
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "code.py", "content": "x=1"}}
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
        ]}},
        # Summary + next tool call in same entry
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "I've added the model selection with bearer token auth and validation."},
            {"type": "tool_use", "id": "t2", "name": "Write", "input": {"file_path": "readme.md", "content": "docs"}}
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": "ok"}
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Done. Updated the README with the new API documentation."}
        ]}},
    ]
    with open(transcript, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    summaries = extract_post_tool_summaries(str(transcript))
    assert len(summaries) == 2
    # First Write (code.py) should get the mixed-entry summary
    assert "model selection" in summaries[0]["summary"]
    assert summaries[0]["file_path"] == "code.py"
    # Second Write (readme.md) should get the standalone summary
    assert "README" in summaries[1]["summary"]
    assert summaries[1]["file_path"] == "readme.md"


def test_post_tool_summary_skips_transition(tmp_path):
    """Transition-only post-tool text should be filtered out."""
    transcript = tmp_path / "t.jsonl"
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "code.py", "old_string": "a", "new_string": "b"}}
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
        ]}},
        # Just a transition, not a summary
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Now let me update the README."},
            {"type": "tool_use", "id": "t2", "name": "Edit", "input": {"file_path": "readme.md", "old_string": "x", "new_string": "y"}}
        ]}},
    ]
    with open(transcript, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    summaries = extract_post_tool_summaries(str(transcript))
    # The Edit to code.py should NOT get "Now let me update the README" as summary
    code_summary = [s for s in summaries if s["file_path"] == "code.py"][0]
    assert code_summary["summary"] == ""
