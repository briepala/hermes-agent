# Projects — Cursor-parity feature design

Maps the Cursor "Projects" changelog (Sep 2026) onto Hermes' existing architecture.
Branch reference artifact; the code is the authority once merged.

## Cursor pillars → Hermes mechanisms

| Cursor pillar | Hermes mechanism | Delta needed |
|---|---|---|
| Coordinator agent (plans, delegates, verifies; doesn't implement) | `delegate_task` orchestrator role + desktop session seeding | Tool guidance + desktop "Coordinate" entry; no new mode |
| Cloud agents (survives laptop close) | Gateway cron + remote terminal backends (ssh/modal/daytona) | None (documented posture) |
| Shared context (files that sync, grow with project) | **NEW**: `project_context` table + prompt injection seam | DB CRUD + `build_context_files_prompt` hook + tool actions |
| Subscriptions (watch/schedule/follow, act unprompted) | Cron jobs | `project_id` binding + workdir/context defaults + UI listing |

## Data shapes

`projects.db` gains (additive, `add_column_if_missing`-style safe open):

```sql
CREATE TABLE IF NOT EXISTS project_context (
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,            -- filename-like: CONTEXT.md, TESTING.md
    content     TEXT NOT NULL DEFAULT '',
    updated_at  INTEGER NOT NULL,
    updated_by  TEXT,                     -- 'user' | 'agent' | session id
    PRIMARY KEY (project_id, name)
);
```

Cron job dict gains one nullable field `project_id: Optional[str]` (jobs.json is
schemaless-additive). Invalid/unknown ids resolve to None, never crash the ticker.

## Injection seam (cache-safe)

`agent/prompt_builder.py::build_context_files_prompt` — after the existing
first-match-wins context-file chain, when the cwd belongs to a project
(`projects_db.project_for_path`), append a `# Project Shared Context` section
listing up to 4 files, each through the existing `_scan_context_content` +
`_truncate_content` path. Read once at prompt build; byte-stable for the
conversation (same contract as AGENTS.md; edits apply next session). Skipped
entirely when `skip_context_files` (curator, cron-without-workdir).

Same seam covers subagents (`_build_child_system_prompt` already calls
`build_context_files_prompt(cwd=workspace_path)`) and cron jobs with workdir —
every agent touching the project folder sees the shared context. This is the
"one agent learns, every future agent uses it" loop.

## Tool surface

`desktop_project` (project toolset, GUI sessions) gains `context` actions:
`context_list`, `context_read`, `context_write` (create/update, `updated_by`
recorded), `context_delete`. Consolidated into the existing `_ACTIONS` table;
description updated to teach the coordinator posture for large bodies of work.

## Subscriptions

- `cronjob` tool + `hermes cron create/edit` gain `project`/`--project`.
- Job creation with a project: `workdir` defaults to the project's primary
  path (explicit workdir wins); the session lands inside the project so the
  injection seam applies automatically.
- `hermes project show` lists bound jobs; desktop project view renders them.

## Desktop UI (renderer owns presentation, backend owns truth)

- Entered-project view gains: Shared Context section (file list, view, edit
  via RPC), Subscriptions section (project cron jobs, pause/resume), and a
  "Coordinate" action that seeds a new session at the project root whose first
  turn asks the agent to take ownership (plan → delegate → verify).
- New RPC: `projects.context_list/get/set/delete`, `projects.jobs`.

## Out of scope (deliberate)

- A Hermes cloud compute offering — local-first tool; gateway-on-server +
  remote backends are the documented equivalents.
- A new Slack connector — the Slack platform adapter + webhook/cron monitor
  pattern covers "watch a channel"; documented, not rebuilt.

## Verification

- `tests/hermes_cli/test_projects_db.py` — context CRUD invariants.
- `tests/agent/test_prompt_builder.py` — injection: belongs-to-project,
  cap/threat-scan, skip flags, byte-stability contract.
- `tests/tools/` — tool action matrix incl. failure modes.
- `tests/cron/` + `tests/tools/test_cronjob*` — project binding, workdir
  default, unknown-project tolerance.
- `tests/tui_gateway/test_projects_rpc.py` — new RPC surface.
- Desktop: vitest suites for new components/stores.
- Full: `scripts/run_tests.sh` on touched dirs; `npm run check` in apps/desktop.
