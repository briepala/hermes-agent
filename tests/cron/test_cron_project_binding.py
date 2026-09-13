"""Project-bound cron jobs (Cursor-Projects subscriptions): binding survives the store round-trip
and resolves to the project's primary folder when no explicit workdir is set."""

from __future__ import annotations

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from cron import jobs as cron_jobs
    monkeypatch.setattr(cron_jobs, "CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr(cron_jobs, "JOBS_FILE", tmp_path / "cron" / "jobs.json")
    (tmp_path / "cron").mkdir(parents=True, exist_ok=True)
    return cron_jobs


def test_project_id_survives_roundtrip(store):
    job = store.create_job(name="watch", schedule="0 9 * * *", prompt="look", project_id="p_abc")
    loaded = store.load_jobs()
    assert [j["project_id"] for j in loaded] == ["p_abc"]
    assert loaded[0]["id"] == job["id"]


def test_scheduler_resolves_project_workdir(store, tmp_path):
    from cron.scheduler import _resolve_job_workdir

    repo = tmp_path / "repo"
    repo.mkdir()
    job = {"id": "j1", "project_id": "p_x", "workdir": ""}
    # No project row -> no workdir (binding dangles harmlessly).
    assert _resolve_job_workdir(job, "j1") is None


def test_scheduler_resolves_project_workdir_real(store, tmp_path, monkeypatch):
    from cron import scheduler
    from hermes_cli import projects_db as pdb

    repo = tmp_path / "repo"
    repo.mkdir()
    c = pdb.connect(db_path=tmp_path / "projects.db")
    pid = pdb.create_project(c, name="W", folders=[str(repo)])
    c.close()
    monkeypatch.setattr("hermes_cli.projects_db.projects_db_path", lambda: tmp_path / "projects.db")

    resolved = scheduler._resolve_job_workdir({"id": "j1", "project_id": pid, "workdir": ""}, "j1")
    assert resolved == str(repo)
    # Explicit workdir wins over the project folder.
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    job2 = {"id": "j2", "project_id": pid, "workdir": str(explicit)}
    assert scheduler._resolve_job_workdir(job2, "j2") == str(explicit)


def test_cronjob_tool_binds_project(store, tmp_path, monkeypatch):
    from hermes_cli import projects_db as pdb
    from tools import cronjob_tools

    repo = tmp_path / "repo"
    repo.mkdir()
    c = pdb.connect(db_path=tmp_path / "projects.db")
    pid = pdb.create_project(c, name="Subs", folders=[str(repo)])
    c.close()
    monkeypatch.setattr("hermes_cli.projects_db.projects_db_path", lambda: tmp_path / "projects.db")

    out = cronjob_tools.cronjob(
        action="create", name="daily", schedule="0 9 * * *", prompt="x", project="Subs")
    import json
    payload = json.loads(out)
    assert payload.get("success"), payload
    job = store.load_jobs()[0]
    assert job["project_id"] == pid
