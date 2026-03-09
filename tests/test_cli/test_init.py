"""Test agentdiff init command."""

import json
from pathlib import Path

from click.testing import CliRunner

from agentdiff.cli.app import cli


def test_init_creates_structure(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--project-root", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / ".agentdiff").exists()
    assert (tmp_path / ".agentdiff" / "sessions").exists()
    assert (tmp_path / ".agentdiff" / "config.yaml").exists()
    assert (tmp_path / ".agentdiff" / "hook.sh").exists()


def test_init_registers_hooks(tmp_path):
    runner = CliRunner()
    runner.invoke(cli, ["init", "--project-root", str(tmp_path)])

    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()

    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "PostToolUse" in settings["hooks"]
    assert "SessionStart" in settings["hooks"]


def test_init_updates_gitignore(tmp_path):
    runner = CliRunner()
    runner.invoke(cli, ["init", "--project-root", str(tmp_path)])

    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".agentdiff/sessions/" in gitignore
    assert ".agentdiff/daemon.sock" in gitignore


def test_init_idempotent(tmp_path):
    runner = CliRunner()
    runner.invoke(cli, ["init", "--project-root", str(tmp_path)])
    result = runner.invoke(cli, ["init", "--project-root", str(tmp_path)])
    assert result.exit_code == 0
