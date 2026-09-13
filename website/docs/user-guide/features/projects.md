# Projects

Hermes Projects are named workspaces that group folders, sessions, and — since the
Cursor-parity update — three durable capabilities: **shared context**, **subscriptions**,
and a **coordinator posture** for the agent working inside a project.

- A Project owns a set of folders (the first is the *primary*).
- Sessions created inside a project live in its workspace; the chat's terminal and file
  tools follow the primary folder.
- The kanban board binding (`--board`) gives worker agents a durable task queue.

## Shared context

Every agent working inside a project — your main session, spawned subagents, and cron
runs — automatically loads the project's shared-context files into the system prompt.
Anything one agent learns (how to build, how to test, which quirks the repo has, how you
prefer reviews) is written once and known by every future agent.

Files live in the per-profile `projects.db`, named like `CONTEXT.md`, `TESTING.md`,
`RELEASE.md`. They ride along every session, subagent, and cron run whose working
directory is inside one of the project's folders.

Ways to manage them:

- Ask the agent: "write what you learned about testing into the project context" — it
  uses the `desktop_project` tool (`context_write`, `context_list`, `context_read`,
  `context_delete`).
- Desktop app: open a project, the sidebar shows the Context section (view, edit, delete).
- CLI: `hermes project show <name>` lists the context files with sizes.

```bash
hermes project create myapp ~/code/myapp
hermes project show myapp      # folders + context + subscriptions at a glance
```

Injection is failure-isolated: a locked or missing database never breaks prompt build,
and content passes the same prompt-injection scanner as repo context files
(`AGENTS.md` et al.).

## Subscriptions

Cron jobs can bind to a project. A bound job runs from the project's primary folder
(unless an explicit `--workdir` overrides it) and loads the project's shared context
on every run — a scheduled agent that already knows how the repo works.

```bash
hermes cron create "0 9 * * *" --name triage --project myapp --prompt "check the board"
hermes cron edit <id> --project myapp        # bind an existing job
hermes cron edit <id> --project ""           # unbind
```

The agent creates these with the `cronjob` tool's `project` parameter (name, slug, or
id). `hermes project show` lists every bound job.

## The coordinator posture

The system prompt for sessions inside a project teaches the Cursor-style posture: the
agent doesn't have to write every line itself — it plans, delegates implementation to
subagents (`delegate_task`), verifies their diffs, and writes what it learns into the
shared context. Projects pair naturally with the kanban board for durable multi-agent
work.

## Where the data lives

- `projects.db` in the active profile's home: projects, folders, context files,
  discovery cache. Per-profile isolation applies to everything here.
- Cron bindings are a `project_id` field on the job record; deleting a project leaves
  the job running from its explicit workdir (dangling bindings degrade, never crash).
