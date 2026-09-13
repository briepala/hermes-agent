"""desktop_project tool context actions (Cursor-Projects parity): the coordinator's write path
to the shared store, verified through the same dispatch the model calls."""

from __future__ import annotations

import json

import pytest

from hermes_cli import projects_db as pdb


@pytest.fixture
def project(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    c = pdb.connect(db_path=tmp_path / "projects.db")
    pid = pdb.create_project(c, name="Tool", folders=[str(repo)])
    c.close()
    monkeypatch.setattr("hermes_cli.projects_db.projects_db_path", lambda: tmp_path / "projects.db")
    yield pid, tmp_path


def _run(action: str, **args) -> dict:
    from tools.project_tools import _handle_project
    return json.loads(_handle_project({**args, "action": action}))


def test_context_write_read_delete_flow(project):
    pid, _ = project
    wrote = _run("context_write", project=pid, name="CONTEXT.md", content="# hello")
    assert wrote["success"]
    assert "system prompt" in wrote["note"]

    got = _run("context_read", project=pid, name="CONTEXT.md")
    assert got["success"] and got["content"] == "# hello"

    listed = _run("context_list", project=pid)
    assert [f["name"] for f in listed["files"]] == ["CONTEXT.md"]

    deleted = _run("context_delete", project=pid, name="CONTEXT.md")
    assert deleted["success"] is True
    assert _run("context_list", project=pid)["files"] == []


def test_context_read_missing_file_fails_cleanly(project):
    pid, _ = project
    got = _run("context_read", project=pid, name="NOPE.md")
    assert got["success"] is False
    assert "NOPE.md" in got.get("error", "")


def test_context_write_validates_name(project):
    pid, _ = project
    got = _run("context_write", project=pid, name="../escape", content="x")
    assert got["success"] is False


def test_context_defaults_to_active_project(project):
    pid, tmp_path = project
    c = pdb.connect(db_path=tmp_path / "projects.db")
    pdb.set_active(c, pid)
    c.close()
    # No `project` arg at all — the active project must be used.
    got = _run("context_write", name="ACTIVE.md", content="x")
    assert got["success"], got
    listed = _run("context_list")
    assert [f["name"] for f in listed["files"]] == ["ACTIVE.md"]
