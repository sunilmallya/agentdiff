"""Infer scope (mentioned files/directories) from a task prompt."""

import re
from pathlib import PurePosixPath

_FILE_EXTENSIONS = (
    r"\.(?:py|js|ts|tsx|jsx|go|rs|java|rb|c|cpp|h|hpp|css|html|yaml|yml|json|md|toml|sql|sh|bash)"
)
_FILE_PATTERN = re.compile(r"[\w./\-]+" + _FILE_EXTENSIONS, re.IGNORECASE)
_DIR_PATTERN = re.compile(r"(?:in|under|from|the)\s+([\w./\-]+/)", re.IGNORECASE)


def infer_scope_files(prompt: str) -> list[str]:
    """Extract file paths and directory patterns from a task prompt.

    Returns empty list if no files can be inferred (vague prompt).
    """
    if not prompt:
        return []

    files = set()

    for match in _FILE_PATTERN.finditer(prompt):
        files.add(match.group(0))

    for match in _DIR_PATTERN.finditer(prompt):
        files.add(match.group(1))

    return sorted(files)


def is_in_scope(file_path: str, scope_files: list[str]) -> bool:
    """Check if file_path matches any scope pattern."""
    if not scope_files:
        return True

    fp = PurePosixPath(file_path)
    for pattern in scope_files:
        if pattern.endswith("/"):
            if str(fp).startswith(pattern) or f"/{pattern}" in str(fp):
                return True
        else:
            # Match by suffix path (e.g., "src/auth/session.js" matches
            # "/full/path/src/auth/session.js"). Single-component patterns
            # like "session.js" still match by name, but generic names like
            # "__init__.py" won't false-match unrelated files.
            if str(fp).endswith(pattern):
                return True
            # Only match by basename if the pattern has directory components
            # (e.g., "auth/session.js") or the pattern is specific enough.
            pattern_path = PurePosixPath(pattern)
            if len(pattern_path.parts) > 1:
                # Multi-component: match suffix
                fp_parts = fp.parts
                pat_parts = pattern_path.parts
                if len(fp_parts) >= len(pat_parts):
                    if fp_parts[-len(pat_parts):] == pat_parts:
                        return True
            else:
                # Single component: exact name match
                if fp.name == pattern_path.name:
                    return True
    return False
