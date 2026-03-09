"""agentdiff teardown -- remove tracking from current project."""

import json
import shutil
from pathlib import Path

import click

from agentdiff.daemon.lifecycle import stop_daemon
from agentdiff.shared.paths import get_agentdiff_root


@click.command()
@click.option("--project-root", default=".", help="Project root directory")
@click.option("--keep-data", is_flag=True, help="Keep .agentdiff/ data, only remove hooks")
def teardown(project_root: str, keep_data: bool):
    """Remove AgentDiff from the current project."""
    project_root = str(Path(project_root).resolve())
    agentdiff_dir = get_agentdiff_root(project_root)

    # 1. Stop daemon
    click.echo("Stopping daemon...")
    stop_daemon(project_root)

    # 2. Remove hooks from .claude/settings.json
    settings_path = Path(project_root) / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            if "hooks" in settings:
                hook_script = str(agentdiff_dir / "hook.sh")
                for event_name in list(settings["hooks"].keys()):
                    settings["hooks"][event_name] = [
                        group for group in settings["hooks"][event_name]
                        if not any(h.get("command") == hook_script for h in group.get("hooks", []))
                    ]
                    if not settings["hooks"][event_name]:
                        del settings["hooks"][event_name]
                if not settings["hooks"]:
                    del settings["hooks"]
            settings_path.write_text(json.dumps(settings, indent=2) + "\n")
            click.echo(f"  Removed hooks from {settings_path}")
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. Clean .gitignore entries
    gitignore_path = Path(project_root) / ".gitignore"
    if gitignore_path.exists():
        agentdiff_entries = {
            ".agentdiff/sessions/",
            ".agentdiff/daemon.sock",
            ".agentdiff/daemon.pid",
            ".agentdiff/daemon.log",
            ".agentdiff/errors.log",
            "# AgentDiff",
        }
        lines = gitignore_path.read_text().splitlines()
        filtered = [line for line in lines if line.strip() not in agentdiff_entries]
        # Remove trailing blank lines left behind
        while filtered and not filtered[-1].strip():
            filtered.pop()
        gitignore_path.write_text("\n".join(filtered) + "\n" if filtered else "")
        click.echo(f"  Cleaned {gitignore_path}")

    # 4. Remove .agentdiff/ directory
    if not keep_data and agentdiff_dir.exists():
        shutil.rmtree(agentdiff_dir)
        click.echo(f"  Removed {agentdiff_dir}/")
    elif keep_data:
        click.echo(f"  Kept {agentdiff_dir}/ (--keep-data)")

    click.echo("\nAgentDiff removed.")
