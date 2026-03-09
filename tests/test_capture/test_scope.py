"""Test scope inference from prompts."""

from agentdiff.capture.scope import infer_scope_files, is_in_scope


def test_infer_file_paths():
    prompt = "update the src/auth.py and src/session.py files"
    files = infer_scope_files(prompt)
    assert "src/auth.py" in files
    assert "src/session.py" in files


def test_infer_directory():
    prompt = "refactor everything in src/auth/"
    files = infer_scope_files(prompt)
    assert "src/auth/" in files


def test_infer_empty_prompt():
    assert infer_scope_files("") == []
    assert infer_scope_files("fix the bug") == []


def test_is_in_scope_file():
    assert is_in_scope("src/auth.py", ["src/auth.py"])
    assert not is_in_scope("src/other.py", ["src/auth.py"])


def test_is_in_scope_directory():
    assert is_in_scope("src/auth/token.py", ["src/auth/"])
    assert not is_in_scope("src/api/routes.py", ["src/auth/"])


def test_is_in_scope_empty():
    assert is_in_scope("anything.py", [])
