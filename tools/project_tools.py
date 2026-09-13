#!/usr/bin/env python3
"""Project tools — the agent's INTENTIONAL handle on first-class Projects (per-profile
``projects.db``, the desktop sidebar's named workspaces). Creating/switching is an explicit
tool call, never a side effect of ``cd``. GUI-only: the `project` toolset stays off
``_HERMES_CORE_TOOLS``; the desktop/TUI gateway folds it in and wires
``set_project_workspace_callback`` so the live session's cwd and sidebar follow."""

import json
import os
from typing import Callable, Optional

from tools.registry import registry

# Set by the GUI gateway: ``(task_id, primary_path, project_name)`` re-anchors that session's
# workspace. ``None`` in CLI/messaging — the DB write still happens, nothing to move.
_workspace_callback: Optional[Callable[[str, str, str], None]] = None


def set_project_workspace_callback(fn: Optional[Callable[[str, str, str], None]]) -> None:
    global _workspace_callback
    _workspace_callback = fn


def _primary_path(proj) -> Optional[str]:
    if getattr(proj, "primary_path", None):
        return proj.primary_path
    for folder in proj.folders:
        if folder.is_primary:
            return folder.path
    return proj.folders[0].path if proj.folders else None


def _apply_workspace(task_id: Optional[str], path: Optional[str], name: str) -> None:
    cb = _workspace_callback
    if cb and task_id and path:
        try:
            cb(task_id, path, name)
        except Exception:
            pass


def _resolve(conn, token: str):
    from hermes_cli import projects_db as pdb
    token = (token or "").strip()
    if not token:
        return None
    projects = pdb.list_projects(conn, include_archived=True)
    # Exact id / slug / name first, then case-insensitive slug / name.
    for proj in projects:
        if token in (proj.id, proj.slug) or proj.name == token:
            return proj
    low = token.lower()
    for proj in projects:
        if proj.slug.lower() == low or proj.name.lower() == low:
            return proj
    return None


def _activated(proj, task_id: Optional[str]) -> str:
    primary = _primary_path(proj)
    _apply_workspace(task_id, primary, proj.name)
    return json.dumps({
        "success": True, "id": proj.id, "slug": proj.slug, "name": proj.name,
        "primary_path": primary})


def project_list(task_id: Optional[str] = None) -> str:
    from hermes_cli import projects_db as pdb
    with pdb.connect_closing() as conn:
        active = pdb.get_active_id(conn)
        projects = pdb.list_projects(conn)
    return json.dumps({
        "active_id": active,
        "projects": [
            {
                "id": p.id, "slug": p.slug, "name": p.name,
                "primary_path": _primary_path(p), "active": p.id == active}
            for p in projects]})


def project_create(name: str, path: Optional[str] = None, task_id: Optional[str] = None) -> str:
    name = (name or "").strip()
    if not name:
        return json.dumps({"success": False, "error": "name is required"})
    from hermes_cli import projects_db as pdb
    folder = (path or "").strip()
    if folder:
        folder = os.path.abspath(os.path.expanduser(folder))
    try:
        with pdb.connect_closing() as conn:
            existing = pdb.find_by_primary_path(conn, folder) if folder else None
            if existing is not None:
                # Idempotent create: duplicates would render N identical sidebar subtrees.
                # Idempotent create: the folder already belongs to a project. Re-activating it beats minting
                # a duplicate — duplicated projects render N identical sidebar subtrees (#75820).
                pdb.set_active(conn, existing.id)
                proj = existing
            else:
                pid = pdb.create_project(conn, name=name, folders=[folder] if folder else [], primary_path=folder or None)
                pdb.set_active(conn, pid)
                proj = pdb.get_project(conn, pid)
    except ValueError as exc:
        return json.dumps({"success": False, "error": str(exc)})
    if proj is None:
        return json.dumps({"success": False, "error": "project vanished after create"})
    return _activated(proj, task_id)


def project_switch(project: str, task_id: Optional[str] = None) -> str:
    from hermes_cli import projects_db as pdb
    with pdb.connect_closing() as conn:
        proj = _resolve(conn, project)
        if proj is None:
            return json.dumps({"success": False, "error": f"no project matching '{project}'"})
        pdb.set_active(conn, proj.id)
    return _activated(proj, task_id)


def _resolve_or_active(conn, token: str):
    """`_resolve` with the schema-promised fallback to the ACTIVE project (project_meta KV)."""
    from hermes_cli import projects_db as pdb
    resolved = _resolve(conn, token)
    if resolved is not None:
        return resolved
    active_id = pdb.get_active_id(conn)
    return pdb.get_project(conn, active_id) if active_id else None


# Shared context (Cursor-Projects parity): project-scoped files every future agent
# (session, subagent, cron) reads automatically when working inside the project.
def project_context_list(project: str) -> str:
    from hermes_cli import projects_db as pdb
    with pdb.connect_closing() as conn:
        proj = _resolve_or_active(conn, project)
        if proj is None:
            return json.dumps({"success": False, "error": f"no project matching '{project}'"})
        return json.dumps({"success": True, "id": proj.id, "files": pdb.list_context_files(conn, proj.id)})


def project_context_read(project: str, name: str) -> str:
    from hermes_cli import projects_db as pdb
    with pdb.connect_closing() as conn:
        proj = _resolve_or_active(conn, project)
        if proj is None:
            return json.dumps({"success": False, "error": f"no project matching '{project}'"})
        try:
            row = pdb.get_context_file(conn, proj.id, name)
        except ValueError as exc:
            return json.dumps({"success": False, "error": str(exc)})
    if row is None:
        return json.dumps({"success": False, "error": f"no context file named '{name}'"})
    return json.dumps({"success": True, **row})


def project_context_write(project: str, name: str, content: str, task_id: Optional[str] = None) -> str:
    from hermes_cli import projects_db as pdb
    with pdb.connect_closing() as conn:
        proj = _resolve_or_active(conn, project)
        if proj is None:
            return json.dumps({"success": False, "error": f"no project matching '{project}'"})
        try:
            row = pdb.set_context_file(
                conn, proj.id, name, content, updated_by=f"agent:{task_id}" if task_id else "agent")
        except ValueError as exc:
            return json.dumps({"success": False, "error": str(exc)})
    return json.dumps({
        "success": True, "name": row["name"], "updated_at": row["updated_at"], "updated_by": row["updated_by"],
        "note": "loaded into the system prompt of every future session/subagent/cron working inside this project"})


_ACTIONS = {
    "list": lambda args, tid: project_list(task_id=tid),
    "create": lambda args, tid: project_create(
        name=args.get("name", ""), path=args.get("path"), task_id=tid),
    "switch": lambda args, tid: project_switch(project=args.get("name", ""), task_id=tid),
    "context_list": lambda args, tid: project_context_list(project=args.get("project", "")),
    "context_read": lambda args, tid: project_context_read(project=args.get("project", ""), name=args.get("name", "")),
    "context_write": lambda args, tid: project_context_write(
        project=args.get("project", ""), name=args.get("name", ""), content=args.get("content", ""), task_id=tid),
    "context_delete": lambda args, tid: _project_context_delete(project=args.get("project", ""), name=args.get("name", "")),
}


def _project_context_delete(project: str, name: str) -> str:
    from hermes_cli import projects_db as pdb
    with pdb.connect_closing() as conn:
        proj = _resolve_or_active(conn, project)
        if proj is None:
            return json.dumps({"success": False, "error": f"no project matching '{project}'"})
        try:
            removed = pdb.delete_context_file(conn, proj.id, name)
        except ValueError as exc:
            return json.dumps({"success": False, "error": str(exc)})
    return json.dumps({"success": removed, "name": name})


def _handle_project(args, **kw):
    action = _ACTIONS.get((args.get("action") or "").strip())
    if action is None:
        return json.dumps({"success": False, "error": "action must be one of: create, switch, list."})
    return action(args, kw.get("task_id"))


# One action enum instead of three tools: each re-taught "desktop Projects" (244 -> ~145 tok).
# Consolidated (#95681, maintainer-directed): project_list/create/switch each re-taught "desktop Projects
# (named workspaces)"; one action enum says it once (244 -> ~145 tok).
registry.register(
    name="desktop_project",
    toolset="project",
    schema={
        "name": "desktop_project",
        "description": (
            "Create or switch desktop Projects (named workspaces). create: one and switch "
            "this chat into it — pass path to anchor it to a repo/folder (the "
            "chat's workspace moves there, the sidebar follows). switch: move "
            "this chat into an existing project by name/slug/id — the "
            "intentional way to move the session, not `cd`. list: all projects + which is active. "
            "context_*: the project's shared-context files, loaded into the system prompt of "
            "every future session/subagent/cron working inside the project — when you learn "
            "something durable (how to build/test/review this repo, user's preferred process), "
            "write it with context_write so every future agent starts knowing it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "switch", "list",
                                                      "context_list", "context_read", "context_write", "context_delete"]},
                "name": {"type": "string", "description": "create: human name. switch: name/slug/id. context_read/write/delete: file name (e.g. TESTING.md)."},
                "path": {"type": "string", "description": "create: repo/folder to anchor to."},
                "project": {"type": "string", "description": "context_*: project name/slug/id (defaults to the active project)."},
                "content": {"type": "string", "description": "context_write: full file content (markdown)."},
            },
            "required": ["action"],
        },
    },
    handler=_handle_project,
)
