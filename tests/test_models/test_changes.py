"""Test ChangeRecord serialization and construction."""

import json
from dataclasses import asdict

from agentdiff.models.changes import ChangeRecord


def test_change_record_defaults():
    r = ChangeRecord()
    assert r.change_id  # auto-generated
    assert r.timestamp > 0
    assert r.provenance == "agent"
    assert r.in_scope is None


def test_change_record_roundtrip():
    r = ChangeRecord(
        session_id="sess-1",
        file_path="src/auth.py",
        tool_name="Edit",
        old_string="foo",
        new_string="bar",
        prompt="fix the bug",
        reasoning="Changed foo to bar for consistency",
        task_id="task-1",
        task_subject="bugfix",
        spec_section="## Authentication",
    )
    serialized = json.dumps(asdict(r), default=str)
    data = json.loads(serialized)
    r2 = ChangeRecord(**data)
    assert r2.session_id == "sess-1"
    assert r2.old_string == "foo"
    assert r2.new_string == "bar"
    assert r2.spec_section == "## Authentication"


def test_change_id_uniqueness():
    r1 = ChangeRecord()
    r2 = ChangeRecord()
    assert r1.change_id != r2.change_id
