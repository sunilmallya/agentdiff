"""agentdiff log -- show recent changes."""

import fnmatch
import json
import os
from dataclasses import asdict
from pathlib import Path

import click

from agentdiff.store.change_log import read_all_changes
from agentdiff.shared.paths import find_project_root
from agentdiff.shared.formatting import format_change_log_entry


@click.command()
@click.option("--task", default=None, help="Filter by task ID")
@click.option("--session", default=None, help="Filter by session ID")
@click.option("--file", "file_pattern", default=None, help="Filter by file path glob (matches basename)")
@click.option("--limit", default=20, help="Number of entries to show")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def log(task: str, session: str, file_pattern: str, limit: int, as_json: bool):
    """Show recent agent changes from the change log."""
    try:
        project_root = find_project_root(Path.cwd())
    except FileNotFoundError:
        click.echo("Not initialized. Run 'agentdiff init' first.", err=True)
        raise SystemExit(1)

    changes = read_all_changes(project_root)

    if task:
        changes = [c for c in changes if c.task_id == task]
    if session:
        changes = [c for c in changes if c.session_id == session]
    if file_pattern:
        changes = [c for c in changes if
                   fnmatch.fnmatch(os.path.basename(c.file_path), file_pattern) or
                   fnmatch.fnmatch(c.file_path, file_pattern)]

    # Most recent first, limited
    changes = list(reversed(changes))[:limit]

    if as_json:
        print(json.dumps([asdict(c) for c in changes], indent=2, default=str))
    elif not changes:
        click.echo("No changes recorded.")
    else:
        for i, change in enumerate(changes):
            format_change_log_entry(change, index=i + 1)
