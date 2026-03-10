"""Terminal output formatting for CLI commands."""

import os
import time

from agentdiff.models.changes import ChangeRecord

# ANSI color palette — distinct colors readable on dark and light terminals
_PROMPT_COLORS = [
    "\033[38;5;75m",   # blue
    "\033[38;5;114m",  # green
    "\033[38;5;214m",  # orange
    "\033[38;5;141m",  # purple
    "\033[38;5;204m",  # pink
    "\033[38;5;80m",   # cyan
    "\033[38;5;209m",  # coral
    "\033[38;5;226m",  # yellow
]

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_WHITE = "\033[97m"
_LABEL = "\033[33m"  # yellow for labels
_PROMPT_TEXT = "\033[37m"  # white for prompt/reasoning text


def _relative_time(timestamp: float) -> str:
    """Convert timestamp to human-readable relative time."""
    delta = time.time() - timestamp
    if delta < 0:
        return "just now"
    if delta < 60:
        return f"{int(delta)}s ago"
    elif delta < 3600:
        return f"{int(delta / 60)}m ago"
    elif delta < 86400:
        return f"{int(delta / 3600)}h ago"
    else:
        return f"{int(delta / 86400)}d ago"


def _short_path(file_path: str, max_len: int = 40) -> str:
    """Shorten a file path to fit within max_len."""
    if len(file_path) <= max_len:
        return file_path
    # Try basename
    base = os.path.basename(file_path)
    if len(base) >= max_len:
        return base[:max_len - 3] + "..."
    # Show .../<parent>/<basename>
    parts = file_path.split(os.sep)
    for i in range(len(parts) - 1, 0, -1):
        suffix = os.sep.join(parts[i:])
        candidate = "..." + os.sep + suffix
        if len(candidate) <= max_len:
            return candidate
    return base


def _build_prompt_color_map(blame_lines: list) -> dict:
    """Assign a color to each unique prompt across all blame lines."""
    seen = {}
    for bl in blame_lines:
        if bl.change and bl.change.prompt:
            key = bl.change.prompt
            if key not in seen:
                seen[key] = _PROMPT_COLORS[len(seen) % len(_PROMPT_COLORS)]
    return seen


def format_blame_lines(blame_lines: list, *, color: bool = False) -> None:
    """Print blame output, grouping consecutive lines with the same change."""
    groups = _group_by_change(blame_lines)
    prompt_colors = _build_prompt_color_map(blame_lines) if color else {}

    if color and prompt_colors:
        print(f"  {_DIM}Legend: each color = a different user prompt{_RESET}")
        print()

    for group in groups:
        change = group[0].change
        prompt_color = ""
        if color and change and change.prompt:
            prompt_color = prompt_colors.get(change.prompt, "")

        # Print the code lines
        for bl in group:
            if color:
                pc = prompt_color or _DIM
                print(f"  {pc}{bl.line_number:>4}{_RESET} {_DIM}|{_RESET} {pc}{bl.content}{_RESET}")
            else:
                print(f"  {bl.line_number:>4} | {bl.content}")

        # Print the annotation once per group
        if change:
            c = change
            version_str = f"v{group[-1].version}" if group[-1].version > 0 else "v1"
            sid = c.session_id[:4] if c.session_id else "????"
            age = _relative_time(c.timestamp)
            line_range = f"L{group[0].line_number}-{group[-1].line_number}" if len(group) > 1 else f"L{group[0].line_number}"

            if color:
                pc = prompt_color or ""
                print(f"  {_DIM}{'':>5} {pc}-- {c.provenance} / {sid} / {age} ({version_str}, {line_range}){_RESET}")
            else:
                print(f"       -- {c.provenance} / {sid} / {age} ({version_str}, {line_range})")
            if c.prompt:
                wrapped = _wrap(c.prompt, 26)
                if color:
                    print(f"          {_LABEL}user-prompt:{_RESET} {_WHITE}\"{wrapped}\"{_RESET}")
                else:
                    print(f"          user-prompt: \"{wrapped}\"")
            if c.reasoning:
                wrapped = _wrap(c.reasoning, 26)
                if color:
                    print(f"          {_LABEL}reasoning:{_RESET}   {_PROMPT_TEXT}\"{wrapped}\"{_RESET}")
                else:
                    print(f"          reasoning:   \"{wrapped}\"")
            if c.task_subject:
                if color:
                    print(f"          {_LABEL}task:{_RESET} {c.task_id} ({c.task_subject})")
                else:
                    print(f"          task: {c.task_id} ({c.task_subject})")
            if c.spec_section:
                if color:
                    print(f"          {_LABEL}spec:{_RESET} {c.spec_section}")
                else:
                    print(f"          spec: {c.spec_section}")
            if c.in_scope is False:
                print(f"          {_BOLD}\033[31m!! OUT OF SCOPE{_RESET}" if color else
                      f"          !! OUT OF SCOPE")
        else:
            gi = group[0].git_info
            if gi and gi.commit_hash:
                age = _relative_time(gi.timestamp)
                hash_display = gi.commit_hash if gi.commit_hash == "uncommitted" else gi.commit_hash[:7]
                if color:
                    print(f"  {_DIM}{'':>5} -- human / {hash_display} / {age}{_RESET}")
                    if gi.author:
                        print(f"          {_LABEL}author:{_RESET} {_PROMPT_TEXT}{gi.author}{_RESET}")
                else:
                    print(f"       -- human / {hash_display} / {age}")
                    if gi.author:
                        print(f"          author: {gi.author}")
            else:
                if color:
                    print(f"  {_DIM}{'':>5} -- human (no agent change recorded){_RESET}")
                else:
                    print(f"       -- human (no agent change recorded)")

        print()


def _group_by_change(blame_lines: list) -> list:
    """Group consecutive blame lines that share the same change_id or git commit."""
    if not blame_lines:
        return []

    def _group_key(bl):
        if bl.change:
            return bl.change.change_id
        gi = bl.git_info
        if gi and gi.commit_hash:
            return f"git:{gi.commit_hash}"
        return None

    groups = []
    current_group = [blame_lines[0]]
    current_id = _group_key(blame_lines[0])

    for bl in blame_lines[1:]:
        bl_id = _group_key(bl)
        if bl_id == current_id:
            current_group.append(bl)
        else:
            groups.append(current_group)
            current_group = [bl]
            current_id = bl_id
    groups.append(current_group)
    return groups


def format_blame_history(hist) -> None:
    """Print version history for a line."""
    print(f"  {hist.line_number} | {hist.current_content}")
    print()

    for i, change in enumerate(reversed(hist.versions)):
        version_num = len(hist.versions) - i
        label = "(latest)" if i == 0 else ""
        age = _relative_time(change.timestamp)
        print(f"     v{version_num} {label} -- change #{change.change_id[-8:]}, {age}")
        if change.reasoning:
            print(f"        reasoning: \"{change.reasoning}\"")
        if change.old_string and change.new_string:
            print(f"        diff: - {_truncate(change.old_string, 60)}")
            print(f"              + {_truncate(change.new_string, 60)}")
        print()


def format_change_log_entry(change: ChangeRecord, index: int) -> None:
    """Print one entry in the change log."""
    age = _relative_time(change.timestamp)
    scope_flag = "  !! OUT OF SCOPE" if change.in_scope is False else ""
    task_info = f"{change.task_id} ({change.task_subject})" if change.task_subject else (change.task_id or "")
    path = _short_path(change.file_path)

    print(f"  #{index:<4} {age:<10} {change.tool_name:<6} {path:<40} {task_info}{scope_flag}")
    if change.prompt:
        print(f"         user-prompt: \"{_truncate(change.prompt, 80)}\"")
    if change.reasoning:
        print(f"         reasoning:   \"{_truncate(change.reasoning, 80)}\"")


def _flatten(text: str) -> str:
    """Collapse newlines to spaces but show the full text."""
    return text.replace("\n", " ").strip()


def _truncate(text: str, max_len: int) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def _wrap(text: str, indent: int, width: int = 100) -> str:
    """Word-wrap text with a hanging indent."""
    text = text.replace("\n", " ").strip()
    if len(text) + indent <= width:
        return text
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) + indent > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    pad = " " * indent
    return ("\n" + pad).join(lines)
