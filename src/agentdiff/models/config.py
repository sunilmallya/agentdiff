"""Project configuration from .agentdiff/config.yaml."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProjectConfig:
    spec_file: Optional[str] = None
    daemon_socket: str = "daemon.sock"
