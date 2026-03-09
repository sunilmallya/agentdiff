"""Helper to call Claude Code CLI for AI-powered analysis.

Shells out to `claude -p` (non-interactive print mode) for tasks like
summarizing changes, enriching reasoning, or linking to spec sections.
Uses haiku by default for speed/cost.  Fails open — returns empty string
on any error so callers never break.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Optional


def ask_claude(
    prompt: str,
    *,
    model: str = "haiku",
    max_turns: int = 1,
    timeout: int = 30,
    output_format: str = "text",
    json_schema: Optional[dict] = None,
) -> str:
    """Run a prompt through `claude -p` and return the response text.

    Args:
        prompt: The question or instruction for Claude.
        model: Model alias — "haiku" (fast/cheap), "sonnet", "opus".
        max_turns: Max agentic turns. 1 = single Q&A, no tool loops.
        timeout: Seconds before we give up.
        output_format: "text" for plain text, "json" for structured output.
        json_schema: Optional JSON schema for structured output.
                     Requires output_format="json".

    Returns:
        The response text, or "" on any failure.
    """
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return ""

    cmd = [
        claude_bin,
        "-p", prompt,
        "--model", model,
        "--max-turns", str(max_turns),
        "--output-format", output_format,
        "--no-session-persistence",
    ]

    if json_schema and output_format == "json":
        cmd.extend(["--json-schema", json.dumps(json_schema)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return ""

        text = result.stdout.strip()

        # For JSON output, extract the result field
        if output_format == "json" and text:
            try:
                data = json.loads(text)
                return data.get("result", text)
            except json.JSONDecodeError:
                return text

        return text
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return ""


def ask_claude_json(
    prompt: str,
    schema: dict,
    *,
    model: str = "haiku",
    timeout: int = 30,
) -> Optional[dict]:
    """Run a prompt and parse the response as structured JSON.

    Args:
        prompt: The question or instruction.
        schema: JSON Schema describing the expected output shape.
        model: Model alias.
        timeout: Seconds before we give up.

    Returns:
        Parsed dict matching the schema, or None on failure.
    """
    raw = ask_claude(
        prompt,
        model=model,
        timeout=timeout,
        output_format="json",
        json_schema=schema,
    )
    if not raw:
        return None
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return None
