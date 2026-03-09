"""Extract reasoning from Claude Code transcript."""

import json
from pathlib import Path


def read_transcript_tail(transcript_path: str, max_lines: int = 50) -> list[dict]:
    """Read the last N lines of a JSONL transcript. Fast tail read.

    For files under 1MB, reads the entire file to ensure we capture
    early entries like the initial user prompt.
    """
    path = Path(transcript_path)
    if not path.exists():
        return []

    entries = []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            # For files under 1MB, read the whole thing (transcripts are
            # typically small). For larger files, read from the tail.
            if file_size <= 1_000_000:
                f.seek(0)
            else:
                f.seek(file_size - 1_000_000)
            data = f.read().decode("utf-8", errors="replace")
            lines = data.strip().split("\n")
            for line in lines[-max_lines:]:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        pass
    return entries


def read_transcript_head(transcript_path: str, max_lines: int = 20) -> list[dict]:
    """Read the first N lines of a JSONL transcript.

    In long agentic sessions the user prompt is near the top — hundreds
    of tool_result entries push it out of the tail window.
    """
    path = Path(transcript_path)
    if not path.exists():
        return []

    entries = []
    try:
        with open(path) as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        pass
    return entries


def extract_reasoning(transcript_path: str) -> str:
    """Extract reasoning: the assistant text just before the most recent tool_use.

    The transcript is JSONL with entries that have a "type" field.
    Tool uses appear as blocks inside "assistant" entries (content is a list
    with blocks of type "text" and "tool_use"). The reasoning is the text
    the agent wrote explaining what it's about to do.

    Cases:
    1. Text and tool_use in the SAME assistant entry — extract text blocks
    2. Text in one assistant entry, tool_use in the NEXT — extract from the text entry
    """
    entries = read_transcript_tail(transcript_path, max_lines=30)
    if not entries:
        return ""

    # Walk backward to find the last assistant entry with a tool_use block
    found_tool_use_idx = None
    for i in range(len(entries) - 1, -1, -1):
        entry = entries[i]
        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content", "")
        if isinstance(content, list):
            has_tool_use = any(b.get("type") == "tool_use" for b in content)
            if has_tool_use:
                # Check if this same entry also has text (case 1)
                text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                text = "\n".join(t for t in text_parts if t).strip()
                if text:
                    return _last_paragraph(text)
                # No text in same entry — look at previous assistant entry (case 2)
                found_tool_use_idx = i
                break

    if found_tool_use_idx is None:
        return ""

    # Walk backward from tool_use entry to find the preceding assistant text
    for i in range(found_tool_use_idx - 1, -1, -1):
        entry = entries[i]
        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content", "")
        text = ""
        if isinstance(content, list):
            text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
            text = "\n".join(t for t in text_parts if t).strip()
        elif isinstance(content, str):
            text = content.strip()
        if text:
            return _last_paragraph(text)
        break  # stop at the first assistant entry even if empty

    return ""


def extract_post_tool_summaries(transcript_path: str) -> list[dict]:
    """Walk the full transcript and extract the assistant summary after each Write/Edit.

    Returns a list of dicts: {tool_name, file_path, summary}
    in order of appearance.
    """
    path = Path(transcript_path)
    if not path.exists():
        return []

    try:
        entries = []
        for line in path.read_text().splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except (OSError, IOError):
        return []

    summaries = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        if entry.get("type") != "assistant":
            i += 1
            continue

        content = entry.get("message", {}).get("content", "")
        if not isinstance(content, list):
            i += 1
            continue

        # Look for Write/Edit tool_use blocks
        for block in content:
            if block.get("type") != "tool_use":
                continue
            tool_name = block.get("name", "")
            if tool_name not in ("Write", "Edit"):
                continue
            file_path = block.get("input", {}).get("file_path", "")

            # Now find the assistant text that comes AFTER the tool_result
            # Walk forward past tool_result entries to find the next assistant text
            summary = _find_post_tool_text(entries, i + 1)
            summaries.append({
                "tool_name": tool_name,
                "file_path": file_path,
                "summary": summary,
            })

        i += 1

    return summaries


def _find_post_tool_text(entries: list[dict], start_idx: int) -> str:
    """Find the assistant text that follows a tool_result.

    When Claude summarizes what it did and immediately starts the next tool
    call in the same assistant entry, the summary appears as text BEFORE the
    tool_use block.  We extract that text rather than skipping the entry.

    We also filter out pure transition text like "Now let me update X" which
    describes the NEXT action, not a summary of what was just done.
    """
    for j in range(start_idx, min(start_idx + 5, len(entries))):
        entry = entries[j]
        if entry.get("type") == "assistant":
            content = entry.get("message", {}).get("content", "")
            text = ""
            if isinstance(content, list):
                has_tool_use = any(b.get("type") == "tool_use" for b in content)
                if has_tool_use:
                    # Extract text blocks BEFORE the first tool_use —
                    # that's the summary of the previous action
                    pre_tool_texts = []
                    for b in content:
                        if b.get("type") == "tool_use":
                            break
                        if b.get("type") == "text" and b.get("text", "").strip():
                            pre_tool_texts.append(b["text"])
                    text = "\n".join(pre_tool_texts).strip()
                else:
                    text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                    text = "\n".join(t for t in text_parts if t).strip()
            elif isinstance(content, str):
                text = content.strip()
            if text and _is_substantive_summary(text):
                return text
    return ""


def _is_substantive_summary(text: str) -> bool:
    """Check if text is an actual summary vs. a forward-looking transition.

    Transitions like "Now let me update the README" or "Let me also fix the
    tests" describe the NEXT action, not what was just done.  A real summary
    describes changes: "Changes made: 1. Removed hardcoded key 2. Added auth".

    Heuristics:
    - Transition phrases at start → not a summary (unless multi-paragraph)
    - Very short text (< 80 chars) with no descriptive content → not a summary
    - Contains list items, numbered steps, or "changed/added/removed" → summary
    """
    lower = text.lower().strip()

    # Multi-paragraph or list-bearing text is almost always substantive
    has_list_items = any(line.strip().startswith(("-", "*", "1.", "2.", "3."))
                        for line in text.split("\n") if line.strip())
    if has_list_items:
        return True
    if "\n\n" in text and len(text) > 120:
        return True

    # Single short sentence starting with a transition phrase → not a summary
    transition_starts = (
        "now let me", "let me ", "next ", "i'll now", "i'll also",
        "now i'll", "now i need", "let's ", "time to ",
    )
    if any(lower.startswith(t) for t in transition_starts):
        return False

    # Descriptive verbs suggest a real summary
    summary_signals = (
        "changed", "added", "removed", "updated", "created", "fixed",
        "modified", "refactored", "implemented", "replaced", "moved",
        "changes made", "here's what", "done.", "i've ",
    )
    if any(s in lower for s in summary_signals):
        return True

    # Longer text (> 100 chars) is more likely to be substantive
    if len(text) > 100:
        return True

    return False


def _last_paragraph(text: str) -> str:
    """Return the last non-empty paragraph from text."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return paragraphs[-1] if paragraphs else ""
