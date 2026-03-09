"""agentdiff blame -- line-level traceability."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import click

from agentdiff.blame.engine import blame_file, blame_line_history
from agentdiff.shared.paths import find_project_root
from agentdiff.shared.formatting import format_blame_lines, format_blame_history


@click.command()
@click.argument("target")
@click.option("--history", is_flag=True, help="Show version history for a specific line")
@click.option("--task", default=None, help="Filter to a specific task")
@click.option("--spec", default=None, help="Filter to a specific spec section")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.option("--color", is_flag=True, default=None, help="Color-code lines by prompt/task (auto-enabled with pager)")
@click.option("--no-pager", is_flag=True, help="Disable pager (default: pager on when TTY)")
def blame(target: str, history: bool, task: str, spec: str, as_json: bool,
          color: bool | None, no_pager: bool):
    """Show prompt, reasoning, task, and spec link for each line.

    Usage:
        agentdiff blame src/auth/session.js
        agentdiff blame src/auth/session.js:15 --history
    """
    # Parse target: file_path or file_path:line
    if ":" in target and target.rsplit(":", 1)[1].isdigit():
        file_path, line_str = target.rsplit(":", 1)
        line_number = int(line_str)
    else:
        file_path = target
        line_number = None

    file_path = str(Path(file_path).resolve())

    if not Path(file_path).exists():
        click.echo(f"File not found: {file_path}", err=True)
        raise SystemExit(1)

    try:
        project_root = find_project_root(Path(file_path).parent)
    except FileNotFoundError:
        click.echo("Not initialized. Run 'agentdiff init' first.", err=True)
        raise SystemExit(1)

    # Determine pager and color settings
    is_tty = sys.stdout.isatty()
    use_pager = is_tty and not no_pager and not as_json and not history
    if color is None:
        color = use_pager  # auto-enable color when paging

    if history:
        if not line_number:
            click.echo("--history requires a line number: agentdiff blame file.py:15 --history", err=True)
            raise SystemExit(1)
        hist = blame_line_history(project_root, file_path, line_number)
        if as_json:
            print(json.dumps(asdict(hist), indent=2, default=str))
        else:
            if not hist.versions:
                click.echo(f"No agent changes recorded for line {line_number}.")
            else:
                format_blame_history(hist)
    else:
        blame_lines = blame_file(project_root, file_path)

        if task:
            blame_lines = [bl for bl in blame_lines if bl.change and bl.change.task_id == task]
        if spec:
            blame_lines = [bl for bl in blame_lines if bl.change and spec.lower() in (bl.change.spec_section or "").lower()]

        if as_json:
            print(json.dumps([asdict(d) for d in blame_lines], indent=2, default=str))
        elif not blame_lines:
            click.echo("No lines to display.")
        elif use_pager:
            _paged_blame(blame_lines, color=color)
        else:
            format_blame_lines(blame_lines, color=color)


def _paged_blame(blame_lines: list, *, color: bool) -> None:
    """Capture blame output and pipe through less -R."""
    # Capture output to string
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        format_blame_lines(blame_lines, color=color)
    finally:
        sys.stdout = old_stdout

    output = buf.getvalue()

    # Find less binary
    less_bin = shutil.which("less")
    if not less_bin:
        # No less available, just print
        sys.stdout.write(output)
        return

    try:
        proc = subprocess.Popen(
            [less_bin, "-R"],  # -R: interpret ANSI color escapes
            stdin=subprocess.PIPE,
            encoding="utf-8",
        )
        proc.communicate(input=output)
    except (OSError, BrokenPipeError):
        # Pager failed, fall back to direct output
        sys.stdout.write(output)
