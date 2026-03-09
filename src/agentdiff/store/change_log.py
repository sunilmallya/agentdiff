"""Append-only JSONL change log. The source of truth."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from agentdiff.models.changes import ChangeRecord
from agentdiff.shared.paths import get_session_dir


def _safe_record(data: dict) -> ChangeRecord | None:
    """Construct a ChangeRecord, ignoring unknown keys and corrupt data."""
    try:
        known = {f.name for f in ChangeRecord.__dataclass_fields__.values()}
        return ChangeRecord(**{k: v for k, v in data.items() if k in known})
    except (TypeError, ValueError):
        return None


def append_change(project_root: str, session_id: str, record: ChangeRecord) -> None:
    """Append a ChangeRecord as one JSON line to changes.jsonl."""
    session_dir = get_session_dir(project_root, session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    changes_path = session_dir / "changes.jsonl"
    line = json.dumps(asdict(record), default=str) + "\n"
    with open(changes_path, "a") as f:
        f.write(line)


def read_changes(project_root: str, session_id: str) -> list[ChangeRecord]:
    """Read all changes for a session. Skips corrupted lines."""
    session_dir = get_session_dir(project_root, session_id)
    changes_path = session_dir / "changes.jsonl"
    if not changes_path.exists():
        return []
    records = []
    for line in changes_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            record = _safe_record(data)
            if record:
                records.append(record)
        except json.JSONDecodeError:
            continue  # skip corrupted lines
    return records


def read_all_changes(project_root: str) -> list[ChangeRecord]:
    """Read changes across all sessions, sorted by timestamp."""
    sessions_dir = Path(project_root) / ".agentdiff" / "sessions"
    if not sessions_dir.exists():
        return []
    all_records = []
    for session_dir in sessions_dir.iterdir():
        if session_dir.is_dir():
            changes_path = session_dir / "changes.jsonl"
            if changes_path.exists():
                for line in changes_path.read_text().splitlines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        record = _safe_record(data)
                        if record:
                            all_records.append(record)
                    except json.JSONDecodeError:
                        continue
    all_records.sort(key=lambda r: r.timestamp)
    return all_records


def update_changes(project_root: str, updates: dict[str, dict]) -> int:
    """Update fields on existing change records (by change_id).

    updates: {change_id: {field: new_value, ...}}
    Returns number of records updated.
    """
    sessions_dir = Path(project_root) / ".agentdiff" / "sessions"
    if not sessions_dir.exists():
        return 0
    count = 0
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        changes_path = session_dir / "changes.jsonl"
        if not changes_path.exists():
            continue
        lines = changes_path.read_text().splitlines()
        modified = False
        new_lines = []
        for line in lines:
            if not line.strip():
                new_lines.append(line)
                continue
            try:
                data = json.loads(line)
                cid = data.get("change_id", "")
                if cid in updates:
                    data.update(updates[cid])
                    new_lines.append(json.dumps(data, default=str))
                    modified = True
                    count += 1
                else:
                    new_lines.append(line)
            except json.JSONDecodeError:
                new_lines.append(line)
        if modified:
            changes_path.write_text("\n".join(new_lines) + "\n")
    return count
