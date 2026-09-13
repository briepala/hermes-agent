"""Shared project context (Cursor-Projects parity): store CRUD + prompt injection.

Behavior contracts, not snapshots: what relates to what.
"""

from __future__ import annotations

import os

import pytest

from hermes_cli import projects_db as pdb


@pytest.fixture
def conn(tmp_path):
    c = pdb.connect(db_path=tmp_path / "projects.db")
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def project(conn, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return pdb.create_project(conn, name="Ctx", folders=[str(repo)]), repo


def test_context_file_roundtrip_and_normalize(conn, project):
    pid, _ = project
    pdb.set_context_file(conn, pid, "CONTEXT.md", "# one")
    # Trailing/leading whitespace is stripped (same row upserts, not duplicates).
    pdb.set_context_file(conn, pid, " CONTEXT.md ", "# two")
    files = pdb.list_context_files(conn, pid)
    assert len(files) == 1
    assert files[0]["name"] == "CONTEXT.md"
    assert pdb.get_context_file(conn, pid, "CONTEXT.md")["content"] == "# two"


def test_context_name_validation(conn, project):
    pid, _ = project
    with pytest.raises(ValueError):
        pdb.set_context_file(conn, pid, "../escape", "x")


def test_context_files_are_per_project(conn, project):
    pid, _ = project
    other = pdb.create_project(conn, name="Other", folders=["/www/other"])
    pdb.set_context_file(conn, pid, "CONTEXT.md", "mine")
    pdb.set_context_file(conn, other, "CONTEXT.md", "theirs")
    assert [f["name"] for f in pdb.list_context_files(conn, pid)] == ["CONTEXT.md"]
    assert pdb.get_context_file(conn, pid, "CONTEXT.md")["content"] == "mine"


def test_delete_context_file(conn, project):
    pid, _ = project
    pdb.set_context_file(conn, pid, "TESTING.md", "how to test")
    assert pdb.delete_context_file(conn, pid, "TESTING.md") is True
    assert pdb.get_context_file(conn, pid, "TESTING.md") is None
    assert pdb.delete_context_file(conn, pid, "TESTING.md") is False


def test_set_context_requires_existing_project(conn):
    with pytest.raises(ValueError):
        pdb.set_context_file(conn, "p_nonexistent", "CONTEXT.md", "x")


def test_prompt_injection_scopes_to_owning_project(conn, tmp_path, project, monkeypatch):
    """build_context_files_prompt gains the project block only for cwds the project owns."""
    from agent.prompt_builder import build_context_files_prompt

    # The loader opens the default per-profile DB; point it at the test DB.
    monkeypatch.setattr("hermes_cli.projects_db.projects_db_path", lambda: tmp_path / "projects.db")

    pid, repo = project
    pdb.set_context_file(conn, pid, "CONTEXT.md", "Run tests with `scripts/run_tests.sh`.")
    prompt = build_context_files_prompt(cwd=str(repo))
    assert "scripts/run_tests.sh" in prompt
    assert "CONTEXT.md" in prompt

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert "scripts/run_tests.sh" not in build_context_files_prompt(cwd=str(elsewhere))
