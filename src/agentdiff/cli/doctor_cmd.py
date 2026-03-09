"""agentdiff doctor -- diagnose issues."""

import json
import os
from pathlib import Path

import click

from agentdiff.daemon.lifecycle import is_daemon_running
from agentdiff.shared.paths import find_project_root, get_agentdiff_root, get_socket_path


@click.command()
def doctor():
    """Diagnose AgentDiff setup issues."""
    try:
        project_root = find_project_root(Path.cwd())
    except FileNotFoundError:
        click.echo("!! Not initialized. Run 'agentdiff init' first.")
        return

    agentdiff_dir = get_agentdiff_root(project_root)
    all_ok = True

    # Check .agentdiff/ exists
    if agentdiff_dir.exists():
        click.echo(f"OK .agentdiff/ exists at {agentdiff_dir}")
    else:
        click.echo(f"!! .agentdiff/ missing")
        all_ok = False

    # Check config.yaml
    config_path = agentdiff_dir / "config.yaml"
    if config_path.exists():
        click.echo(f"OK config.yaml exists")
    else:
        click.echo(f"!! config.yaml missing")
        all_ok = False

    # Check hook script
    hook_path = agentdiff_dir / "hook.sh"
    if hook_path.exists():
        if os.access(hook_path, os.X_OK):
            click.echo(f"OK hook.sh exists and is executable")
        else:
            click.echo(f"!! hook.sh exists but is NOT executable (run: chmod +x {hook_path})")
            all_ok = False
    else:
        click.echo(f"!! hook.sh missing")
        all_ok = False

    # Check daemon
    if is_daemon_running(project_root):
        click.echo(f"OK daemon running")
    else:
        click.echo(f"!! daemon not running")
        all_ok = False

    # Check socket
    sock_path = get_socket_path(project_root)
    if sock_path.exists():
        click.echo(f"OK daemon.sock exists")
    else:
        click.echo(f"!! daemon.sock missing")
        all_ok = False

    # Check .claude/settings.json hooks
    settings_path = Path(project_root) / ".claude" / "settings.json"
    hook_script = str(agentdiff_dir / "hook.sh")
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            hooks = settings.get("hooks", {})
            event_types = len(hooks)
            # Verify at least one hook points to our hook.sh
            our_hooks = 0
            for event_name, groups in hooks.items():
                for group in groups:
                    for h in group.get("hooks", []):
                        if h.get("command") == hook_script:
                            our_hooks += 1
            if our_hooks > 0:
                click.echo(f"OK hooks registered ({event_types} event types, {our_hooks} agentdiff hooks)")
            elif event_types > 0:
                click.echo(f"!! hooks exist ({event_types} event types) but none point to agentdiff hook.sh")
                all_ok = False
            else:
                click.echo(f"!! no hooks registered in settings.json")
                all_ok = False
        except json.JSONDecodeError:
            click.echo(f"!! settings.json is invalid JSON")
            all_ok = False
    else:
        click.echo(f"!! .claude/settings.json missing")
        all_ok = False

    # Check sessions
    sessions_dir = agentdiff_dir / "sessions"
    if sessions_dir.exists():
        session_count = sum(1 for d in sessions_dir.iterdir() if d.is_dir())
        click.echo(f"OK {session_count} session(s) recorded")
    else:
        click.echo(f"OK no sessions yet")

    # Check errors log
    errors_log = agentdiff_dir / "errors.log"
    if errors_log.exists():
        error_count = sum(1 for _ in errors_log.read_text().splitlines() if _.strip())
        if error_count > 0:
            click.echo(f"!! {error_count} error(s) in errors.log")
            all_ok = False
    else:
        click.echo(f"OK no errors logged")

    if all_ok:
        click.echo("\nAll checks passed.")
    else:
        click.echo("\nSome checks failed. Run 'agentdiff init' to fix.")
