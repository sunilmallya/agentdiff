"""agentdiff init -- set up tracking in current project."""

import json
import stat
from pathlib import Path

import click

from agentdiff.daemon.lifecycle import start_daemon
from agentdiff.hooks.scripts import HOOK_SCRIPT_CONTENT, get_hooks_config
from agentdiff.shared.paths import get_agentdiff_root


@click.command()
@click.option("--project-root", default=".", help="Project root directory")
def init(project_root: str):
    """Initialize AgentDiff in the current project."""
    project_root = str(Path(project_root).resolve())
    agentdiff_dir = get_agentdiff_root(project_root)

    # 1. Create .agentdiff/ directory structure
    click.echo(f"Creating {agentdiff_dir}/")
    agentdiff_dir.mkdir(parents=True, exist_ok=True)
    (agentdiff_dir / "sessions").mkdir(exist_ok=True)

    # 2. Write default config.yaml
    config_path = agentdiff_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text("# AgentDiff configuration\n# spec_file: SPEC.md\n")
        click.echo(f"  Created {config_path}")

    # 3. Write hook script
    hook_script_path = agentdiff_dir / "hook.sh"
    hook_script_path.write_text(HOOK_SCRIPT_CONTENT)
    hook_script_path.chmod(hook_script_path.stat().st_mode | stat.S_IEXEC)
    click.echo(f"  Created {hook_script_path}")

    # 4. Register hooks in .claude/settings.json
    claude_dir = Path(project_root) / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.json"

    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            existing = {}

    hooks_config = get_hooks_config(str(hook_script_path))
    if "hooks" not in existing:
        existing["hooks"] = {}
    for event_name, event_hooks in hooks_config["hooks"].items():
        if event_name not in existing["hooks"]:
            existing["hooks"][event_name] = []
        existing_cmds = {
            h.get("command", "")
            for group in existing["hooks"][event_name]
            for h in group.get("hooks", [])
        }
        for hook_group in event_hooks:
            new_cmds = [h for h in hook_group.get("hooks", []) if h.get("command") not in existing_cmds]
            if new_cmds:
                existing["hooks"][event_name].append(hook_group)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")
    click.echo(f"  Registered hooks in {settings_path}")

    # 5. Start daemon
    click.echo("Starting daemon...")
    pid = start_daemon(project_root)
    click.echo(f"  Daemon running (PID {pid})")

    # 6. Add .gitignore entries
    gitignore_path = Path(project_root) / ".gitignore"
    entries_to_add = [
        ".agentdiff/sessions/",
        ".agentdiff/daemon.sock",
        ".agentdiff/daemon.pid",
        ".agentdiff/daemon.log",
        ".agentdiff/errors.log",
    ]
    existing_lines = set()
    if gitignore_path.exists():
        existing_lines = {line.strip() for line in gitignore_path.read_text().splitlines()}
    new_entries = [e for e in entries_to_add if e not in existing_lines]
    if new_entries:
        with open(gitignore_path, "a") as f:
            f.write("\n# AgentDiff\n")
            for entry in new_entries:
                f.write(entry + "\n")
        click.echo(f"  Updated {gitignore_path}")

    click.echo("\nAgentDiff initialized. Start a Claude Code session to begin tracking.")
