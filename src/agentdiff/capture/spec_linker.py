"""Match agent reasoning/prompts to spec headings.

Uses keyword overlap between the agent's text (prompt, reasoning) and
the ## headings in the spec file. Since Claude already read the spec,
its reasoning naturally references the relevant concepts.
"""

import re
from pathlib import Path

from agentdiff.models.config import ProjectConfig

# Module-level caches
_config_cache: dict[str, ProjectConfig] = {}
_headings_cache: dict[str, tuple[float, list[str]]] = {}


def load_spec_headings(spec_path: str) -> list[str]:
    """Extract ## headings from a markdown file."""
    path = Path(spec_path)
    if not path.exists():
        return []

    headings = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            headings.append(stripped)
    return headings


def link_to_spec(project_root: str, text: str) -> str:
    """Match text against spec headings using keyword overlap.

    Claude's reasoning already references spec concepts naturally,
    so we just check which heading's keywords appear most in the text.
    """
    if not text:
        return ""

    config = _load_config_cached(project_root)
    if not config.spec_file:
        return ""

    spec_path = str(Path(project_root) / config.spec_file)
    headings = _load_headings_cached(spec_path)
    if not headings:
        return ""

    text_lower = text.lower()
    text_words = set(_tokenize(text_lower))

    best_score = 0
    best_heading = ""

    for heading in headings:
        heading_text = heading.lstrip("#").strip()
        heading_lower = heading_text.lower()

        # Score 1: direct substring match (strongest signal)
        if heading_lower in text_lower:
            return heading

        # Score 2: keyword overlap
        heading_words = set(_tokenize(heading_lower))
        if not heading_words:
            continue

        # Count how many heading words appear in the text
        overlap = heading_words & text_words
        score = len(overlap) / len(heading_words)

        if score > best_score:
            best_score = score
            best_heading = heading

    # Require at least 50% of heading words to match
    if best_score >= 0.5:
        return best_heading
    return ""


def relink_all(project_root: str) -> dict[str, str]:
    """Re-match all existing changes against spec headings.

    Persists updated spec_section values back to the JSONL files.
    Returns mapping of change_id -> new_spec_section.
    """
    from agentdiff.store.change_log import read_all_changes, update_changes

    changes = read_all_changes(project_root)
    updated = {}

    for change in changes:
        # Use all available text: reasoning, prompt, task description
        texts = [change.reasoning, change.prompt, change.task_description]
        combined = " ".join(t for t in texts if t)
        if combined.strip():
            new_link = link_to_spec(project_root, combined)
            if new_link and new_link != change.spec_section:
                updated[change.change_id] = new_link

    if updated:
        update_changes(project_root, {cid: {"spec_section": section} for cid, section in updated.items()})

    return updated


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase words, dropping short/common ones."""
    stopwords = {"the", "a", "an", "and", "or", "for", "to", "in", "of", "on", "is", "it", "by", "with", "from", "as", "at", "be"}
    words = re.findall(r'[a-z][a-z0-9]+', text.lower())
    return [w for w in words if w not in stopwords and len(w) > 1]


def _load_config(project_root: str) -> ProjectConfig:
    """Load project config from .agentdiff/config.yaml."""
    import yaml
    config_path = Path(project_root) / ".agentdiff" / "config.yaml"
    if not config_path.exists():
        return ProjectConfig()
    data = yaml.safe_load(config_path.read_text()) or {}
    return ProjectConfig(**{k: v for k, v in data.items() if k in ProjectConfig.__dataclass_fields__})


def _load_config_cached(project_root: str) -> ProjectConfig:
    """Cached version of _load_config."""
    if project_root not in _config_cache:
        _config_cache[project_root] = _load_config(project_root)
    return _config_cache[project_root]


def _load_headings_cached(spec_path: str) -> list[str]:
    """Load spec headings with mtime-based cache invalidation."""
    path = Path(spec_path)
    if not path.exists():
        return []
    mtime = path.stat().st_mtime
    if spec_path in _headings_cache:
        cached_mtime, cached_headings = _headings_cache[spec_path]
        if cached_mtime == mtime:
            return cached_headings
    headings = load_spec_headings(spec_path)
    _headings_cache[spec_path] = (mtime, headings)
    return headings
