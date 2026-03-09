"""agentdiff relink -- re-match tasks to spec headings."""

from pathlib import Path

import click

from agentdiff.capture.spec_linker import relink_all
from agentdiff.shared.paths import find_project_root


@click.command()
def relink():
    """Re-match all tasks against updated spec headings."""
    try:
        project_root = find_project_root(Path.cwd())
    except FileNotFoundError:
        click.echo("Not initialized. Run 'agentdiff init' first.", err=True)
        raise SystemExit(1)
    updated = relink_all(project_root)

    if not updated:
        click.echo("No spec links changed.")
    else:
        click.echo(f"Updated {len(updated)} spec link(s):")
        for change_id, new_section in updated.items():
            click.echo(f"  {change_id[-12:]} -> {new_section}")
