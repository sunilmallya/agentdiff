"""Test spec linking."""

import pytest
from pathlib import Path

from agentdiff.capture import spec_linker
from agentdiff.capture.spec_linker import load_spec_headings, link_to_spec


@pytest.fixture(autouse=True)
def clear_spec_cache():
    """Clear module-level caches between tests."""
    spec_linker._config_cache.clear()
    spec_linker._headings_cache.clear()


def test_load_spec_headings(tmp_path):
    spec = tmp_path / "SPEC.md"
    spec.write_text("# Product\n\n## Authentication\nDetails.\n\n## Token Validation\nMore details.\n\n## API Endpoints\n")
    headings = load_spec_headings(str(spec))
    assert headings == ["## Authentication", "## Token Validation", "## API Endpoints"]


def test_link_to_spec(project_dir):
    spec = project_dir / "SPEC.md"
    spec.write_text("# Spec\n\n## Authentication\n\n## Token Validation\n\n## API Endpoints\n")
    config = project_dir / ".agentdiff" / "config.yaml"
    config.write_text("spec_file: SPEC.md\n")

    # Direct keyword overlap: "token" + "validation" match the heading
    result = link_to_spec(str(project_dir), "migrate session token validation from JWT to opaque tokens")
    assert "Token Validation" in result


def test_link_to_spec_substring_match(project_dir):
    """When the heading text appears verbatim in reasoning, it's a direct match."""
    spec = project_dir / "SPEC.md"
    spec.write_text("# Spec\n\n## Multi-Model Support\n\n## Streaming API\n")
    config = project_dir / ".agentdiff" / "config.yaml"
    config.write_text("spec_file: SPEC.md\n")

    # Claude's reasoning naturally references the spec heading
    result = link_to_spec(str(project_dir), "I'll implement multi-model support by adding a MODELS dict")
    assert "Multi-Model Support" in result


def test_link_no_spec_file(project_dir):
    result = link_to_spec(str(project_dir), "some task")
    assert result == ""


def test_link_no_match(project_dir):
    spec = project_dir / "SPEC.md"
    spec.write_text("# Spec\n\n## Authentication\n")
    config = project_dir / ".agentdiff" / "config.yaml"
    config.write_text("spec_file: SPEC.md\n")

    result = link_to_spec(str(project_dir), "completely unrelated quantum physics task xyz123")
    assert result == ""
