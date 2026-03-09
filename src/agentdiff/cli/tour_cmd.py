"""agentdiff tour -- generate a CodeTour walkthrough from agent changes."""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path

import click

from agentdiff.blame.engine import blame_file, _paths_match
from agentdiff.store.change_log import read_all_changes
from agentdiff.shared.paths import find_project_root


@click.command()
@click.option("--session", default=None, help="Filter by session ID")
@click.option("--task", default=None, help="Filter by task ID")
@click.option("--file", "file_pattern", default=None, help="Filter by file path glob")
@click.option("--output", "-o", default=None, help="Output path (default: .tours/agentdiff-<session>.tour)")
def tour(session: str, task: str, file_pattern: str, output: str):
    """Generate a VS Code CodeTour from agent changes.

    Creates a .tour file that walks through each change chronologically,
    showing the prompt, reasoning, and diff at each step.

    Requires the CodeTour VS Code extension to view.
    """
    try:
        project_root = find_project_root(Path.cwd())
    except FileNotFoundError:
        click.echo("Not initialized. Run 'agentdiff init' first.", err=True)
        raise SystemExit(1)

    changes = read_all_changes(project_root)

    if session:
        changes = [c for c in changes if c.session_id == session]
    if task:
        changes = [c for c in changes if c.task_id == task]
    if file_pattern:
        changes = [c for c in changes if
                   fnmatch.fnmatch(os.path.basename(c.file_path), file_pattern) or
                   fnmatch.fnmatch(c.file_path, file_pattern)]

    if not changes:
        click.echo("No changes to tour.")
        return

    # Build tour steps from changes (chronological order)
    steps = []
    for c in changes:
        step = _build_step(c, project_root)
        if step:
            steps.append(step)

    if not steps:
        click.echo("No tour steps could be generated.")
        return

    # Build tour title from context
    title = _build_title(changes, session, task)

    tour_data = {
        "$schema": "https://aka.ms/codetour-schema",
        "title": title,
        "steps": steps,
    }

    # Write to .tours/ directory
    if output:
        tour_path = Path(output)
    else:
        tours_dir = Path(project_root) / ".tours"
        tours_dir.mkdir(exist_ok=True)
        slug = session[:8] if session else changes[0].session_id[:8]
        tour_path = tours_dir / f"agentdiff-{slug}.tour"

    tour_path.parent.mkdir(parents=True, exist_ok=True)
    tour_path.write_text(json.dumps(tour_data, indent=2) + "\n")
    click.echo(f"Tour written: {tour_path} ({len(steps)} steps)")
    click.echo("Open in VS Code with the CodeTour extension to walk through changes.")


def _build_step(change, project_root: str) -> dict | None:
    """Build a CodeTour step from a ChangeRecord."""
    # CodeTour needs relative file paths within the project
    file_path = change.file_path
    if Path(file_path).is_absolute():
        try:
            file_path = str(Path(file_path).relative_to(project_root))
        except ValueError:
            # File is outside the project (e.g. ~/.claude/plans/) — skip it
            return None

    # Skip files that don't exist (deleted or moved)
    abs_path = Path(project_root) / file_path
    if not abs_path.exists():
        return None

    # Find which line this change maps to in the current file
    line = _find_change_line(change, abs_path)

    # Build description in markdown
    parts = []

    # Header: tool action
    action = "Created file" if change.tool_name == "Write" else "Edited"
    parts.append(f"**{action}** `{file_path}`")
    parts.append("")

    if change.prompt:
        parts.append(f"**user-prompt:** \"{change.prompt}\"")
        parts.append("")

    if change.reasoning:
        parts.append(f"**reasoning:** {change.reasoning}")
        parts.append("")

    # Show the diff for edits (truncate large diffs to keep popup readable)
    if change.tool_name == "Edit" and change.old_string and change.new_string:
        old_lines = change.old_string.splitlines()
        new_lines = change.new_string.splitlines()
        max_diff_lines = 20
        parts.append("```diff")
        for old_line in old_lines[:max_diff_lines]:
            parts.append(f"- {old_line}")
        for new_line in new_lines[:max_diff_lines]:
            parts.append(f"+ {new_line}")
        total = len(old_lines) + len(new_lines)
        if total > max_diff_lines * 2:
            parts.append(f"  ... ({total - max_diff_lines * 2} more lines)")
        parts.append("```")
        parts.append("")

    if change.task_subject:
        parts.append(f"*task: {change.task_subject}*")
    if change.spec_section:
        parts.append(f"*spec: {change.spec_section}*")
    if change.in_scope is False:
        parts.append("**!! OUT OF SCOPE**")

    step = {
        "file": file_path,
        "description": "\n".join(parts),
    }

    # Add title for step list readability
    if change.tool_name == "Edit" and change.old_string:
        preview = change.new_string.splitlines()[0][:60] if change.new_string else ""
        step["title"] = f"Edit: {preview}"
    elif change.tool_name == "Write":
        step["title"] = f"Write: {os.path.basename(file_path)}"

    if line:
        step["line"] = line

    return step


def _find_change_line(change, abs_path: Path) -> int | None:
    """Find the line number where this change appears in the current file."""
    if not abs_path.exists():
        return None

    current_lines = abs_path.read_text().splitlines()

    if change.tool_name == "Edit" and change.new_string:
        # Find where the new_string appears in the current file
        content = "\n".join(current_lines)
        idx = content.find(change.new_string)
        if idx != -1:
            return content[:idx].count("\n") + 1

    if change.tool_name == "Write":
        return 1

    return 1


def _build_title(changes, session: str | None, task: str | None) -> str:
    """Generate a descriptive tour title."""
    if task:
        # Find task subject
        for c in changes:
            if c.task_subject:
                return f"AgentDiff: {c.task_subject}"
        return f"AgentDiff: task {task[:8]}"

    # Use the first prompt as the title
    for c in changes:
        if c.prompt:
            prompt = c.prompt[:60]
            if len(c.prompt) > 60:
                prompt += "..."
            return f"AgentDiff: {prompt}"

    sid = session or changes[0].session_id
    return f"AgentDiff: session {sid[:8]}"
