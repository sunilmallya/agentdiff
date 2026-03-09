"""Top-level CLI entry point."""

from importlib.metadata import version as pkg_version

import click


@click.group()
@click.version_option(version=pkg_version("agentdiff"), prog_name="agentdiff")
def cli():
    """AgentDiff -- track every change an AI coding agent makes."""
    pass


from agentdiff.cli.init_cmd import init
from agentdiff.cli.teardown_cmd import teardown
from agentdiff.cli.blame_cmd import blame
from agentdiff.cli.log_cmd import log
from agentdiff.cli.doctor_cmd import doctor
from agentdiff.cli.relink_cmd import relink
from agentdiff.cli.tour_cmd import tour

cli.add_command(init)
cli.add_command(teardown)
cli.add_command(blame)
cli.add_command(log)
cli.add_command(doctor)
cli.add_command(relink)
cli.add_command(tour)
