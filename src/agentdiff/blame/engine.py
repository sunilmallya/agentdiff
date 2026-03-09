"""Content matching to map change records to current file lines.

For each ChangeRecord, find where its new_string (Edit) or content (Write)
appears in the current file. Uses difflib to compare consecutive Writes
so that unchanged lines keep their original attribution.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from agentdiff.models.changes import ChangeRecord


@dataclass
class BlameLine:
    """One line of blame output."""
    line_number: int
    content: str
    change: ChangeRecord | None = None
    version: int = 0
    overwritten: bool = False


@dataclass
class BlameHistory:
    """Version history for a single line."""
    line_number: int
    current_content: str
    versions: list[ChangeRecord]


def blame_file(project_root: str, file_path: str) -> list[BlameLine]:
    """Map each line of the current file to its most recent ChangeRecord."""
    from agentdiff.store.change_log import read_all_changes

    abs_path = Path(file_path)
    if not abs_path.is_absolute():
        abs_path = Path(project_root) / abs_path
    if not abs_path.exists():
        return []

    current_lines = abs_path.read_text().splitlines()
    changes = read_all_changes(project_root)

    file_changes = [
        c for c in changes
        if _paths_match(c.file_path, str(abs_path), project_root)
    ]
    file_changes.sort(key=lambda c: c.timestamp)

    blame = [BlameLine(line_number=i + 1, content=line) for i, line in enumerate(current_lines)]
    version_counts: dict[int, int] = {}

    writes = [c for c in file_changes if c.tool_name == "Write" and c.content is not None]
    edits = [c for c in file_changes if c.tool_name == "Edit" and c.new_string is not None]

    # Pass 1: Attribute lines to the Write that FIRST introduced them.
    # Diff consecutive Writes so unchanged lines keep earlier attribution.
    if writes:
        # Build attribution map: for each line index in the last Write,
        # which Write first authored it?
        first_write = writes[0]
        first_lines = first_write.content.splitlines()
        # line_index -> ChangeRecord
        line_attr: dict[int, ChangeRecord] = {i: first_write for i in range(len(first_lines))}

        prev_lines = first_lines
        for write_change in writes[1:]:
            curr_lines = write_change.content.splitlines()
            matcher = difflib.SequenceMatcher(None, prev_lines, curr_lines)
            new_attr: dict[int, ChangeRecord] = {}
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal":
                    # Unchanged lines carry forward their attribution
                    for offset in range(j2 - j1):
                        new_attr[j1 + offset] = line_attr.get(i1 + offset, write_change)
                else:
                    # New or changed lines belong to this Write
                    for idx in range(j1, j2):
                        new_attr[idx] = write_change
            line_attr = new_attr
            prev_lines = curr_lines

        # Map last Write's attributions onto current file lines
        last_write_lines = writes[-1].content.splitlines()
        matcher = difflib.SequenceMatcher(None, last_write_lines, current_lines)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for offset in range(j2 - j1):
                    write_idx = i1 + offset
                    current_idx = j1 + offset
                    if 0 <= current_idx < len(blame):
                        change = line_attr.get(write_idx, writes[-1])
                        blame[current_idx].change = change
                        ln = current_idx + 1
                        version_counts[ln] = version_counts.get(ln, 0) + 1
                        blame[current_idx].version = version_counts[ln]
            elif tag in ("replace", "insert"):
                # Lines that differ from the Write content still get Write
                # attribution as a baseline — Edits will override in Pass 2
                for current_idx in range(j1, j2):
                    if 0 <= current_idx < len(blame):
                        blame[current_idx].change = writes[-1]
                        ln = current_idx + 1
                        version_counts[ln] = version_counts.get(ln, 0) + 1
                        blame[current_idx].version = version_counts[ln]

    # Pass 2: Edits override specific lines (more precise than Writes)
    for change in edits:
        matched_lines = _find_content_lines(current_lines, change.new_string)
        for line_idx in matched_lines:
            if 0 <= line_idx < len(blame):
                blame[line_idx].change = change
                ln = line_idx + 1
                version_counts[ln] = version_counts.get(ln, 0) + 1
                blame[line_idx].version = version_counts[ln]

    return blame


def blame_line_history(project_root: str, file_path: str, line_number: int) -> BlameHistory:
    """Get full version history for a specific line."""
    from agentdiff.store.change_log import read_all_changes

    abs_path = Path(file_path)
    if not abs_path.is_absolute():
        abs_path = Path(project_root) / abs_path
    current_lines = abs_path.read_text().splitlines() if abs_path.exists() else []
    current_content = current_lines[line_number - 1] if 1 <= line_number <= len(current_lines) else ""

    changes = read_all_changes(project_root)
    file_changes = [
        c for c in changes
        if _paths_match(c.file_path, str(abs_path), project_root)
    ]
    file_changes.sort(key=lambda c: c.timestamp)

    versions = []
    for change in file_changes:
        if change.tool_name == "Write":
            versions.append(change)
        elif change.tool_name == "Edit" and change.new_string is not None:
            matched = _find_content_lines(current_lines, change.new_string)
            if (line_number - 1) in matched:
                versions.append(change)

    return BlameHistory(
        line_number=line_number,
        current_content=current_content,
        versions=versions,
    )


def _find_content_lines(file_lines: list[str], content: str) -> list[int]:
    """Find which line indices in file_lines contain the given content."""
    if not content or not file_lines:
        return []

    content_lines = content.splitlines()
    if not content_lines:
        return []

    matched_indices = set()
    file_text = "\n".join(file_lines)

    # Find first occurrence only — avoids false positives when content
    # appears multiple times (e.g., "return None" in many functions)
    idx = file_text.find(content)
    if idx != -1:
        prefix = file_text[:idx]
        start_line = prefix.count("\n")
        end_line = start_line + len(content_lines) - 1
        matched_indices.update(range(start_line, end_line + 1))

    return sorted(matched_indices)


def _paths_match(stored_path: str, current_path: str, project_root: str = "") -> bool:
    """Check if two file paths refer to the same file."""
    sp = Path(stored_path)
    cp = Path(current_path)

    # Try direct resolve match
    try:
        if sp.resolve() == cp.resolve():
            return True
    except OSError:
        pass

    # Try relative-to-project match
    if project_root:
        sp_rel = sp if sp.is_absolute() else Path(project_root) / sp
        cp_rel = cp if cp.is_absolute() else Path(project_root) / cp
        try:
            if sp_rel.resolve() == cp_rel.resolve():
                return True
        except OSError:
            pass

    return False
