"""Git pre-commit and post-commit hooks for summary projection."""

import json
import subprocess
import sys
from pathlib import Path

from agentdiff.store.change_log import read_all_changes
from agentdiff.shared.paths import get_agentdiff_root


PRE_COMMIT_SCRIPT = '''#!/bin/sh
# AgentDiff pre-commit hook
# Rolls up change log into summary, writes to pending-metadata.json
python3 -m agentdiff.hooks.git_hooks pre_commit "$PWD" || true
'''

POST_COMMIT_SCRIPT = '''#!/bin/sh
# AgentDiff post-commit hook
# Attaches summary as git note
python3 -m agentdiff.hooks.git_hooks post_commit "$PWD" || true
'''


def pre_commit(project_root: str) -> None:
    """Pre-commit: build summary from changes since last commit, write to pending-metadata.json."""
    agentdiff_dir = get_agentdiff_root(project_root)

    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, cwd=project_root,
    )
    staged_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    if not staged_files:
        return

    # Get timestamp of last commit to scope changes
    last_commit_ts = 0.0
    ts_result = subprocess.run(
        ["git", "log", "-1", "--format=%ct"],
        capture_output=True, text=True, cwd=project_root,
    )
    if ts_result.returncode == 0 and ts_result.stdout.strip():
        try:
            last_commit_ts = float(ts_result.stdout.strip())
        except ValueError:
            pass

    changes = read_all_changes(project_root)
    # Only include changes since last commit that match staged files
    matched = [
        c for c in changes
        if c.timestamp > last_commit_ts and any(c.file_path.endswith(f) for f in staged_files)
    ]

    if not matched:
        return

    # Collect unique prompts (preserving order)
    prompts = list(dict.fromkeys(c.prompt for c in matched if c.prompt))

    # Build per-file summaries
    files: dict[str, dict] = {}
    for c in matched:
        fp = c.file_path
        if fp not in files:
            files[fp] = {"edits": 0, "reasoning": []}
        files[fp]["edits"] += 1
        if c.reasoning and c.reasoning not in files[fp]["reasoning"]:
            files[fp]["reasoning"].append(c.reasoning)

    # Collect scope violations
    scope_violations = list(dict.fromkeys(
        c.file_path for c in matched if c.in_scope is False
    ))

    # Collect tasks (if any)
    tasks = []
    seen_tasks: set[str] = set()
    for c in matched:
        if c.task_subject and c.task_id not in seen_tasks:
            seen_tasks.add(c.task_id)
            tasks.append({"task_id": c.task_id, "subject": c.task_subject})

    summary: dict = {
        "agentdiff_version": "0.1.0",
        "total_changes": len(matched),
        "provenance": "agent",
        "prompts": prompts,
        "files": {fp: info for fp, info in files.items()},
    }
    if tasks:
        summary["tasks"] = tasks
    if scope_violations:
        summary["scope_violations"] = scope_violations

    pending_path = agentdiff_dir / "pending-metadata.json"
    pending_path.write_text(json.dumps(summary, indent=2))


def post_commit(project_root: str) -> None:
    """Post-commit: attach pending metadata as git note."""
    agentdiff_dir = get_agentdiff_root(project_root)
    pending_path = agentdiff_dir / "pending-metadata.json"

    if not pending_path.exists():
        return

    metadata = pending_path.read_text()

    subprocess.run(
        ["git", "notes", "--ref=agentdiff", "add", "--force", "-m", metadata, "HEAD"],
        capture_output=True, cwd=project_root,
    )

    pending_path.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        command = sys.argv[1]
        root = sys.argv[2]
        if command == "pre_commit":
            pre_commit(root)
        elif command == "post_commit":
            post_commit(root)
