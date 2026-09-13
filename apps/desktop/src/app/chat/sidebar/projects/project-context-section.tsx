import { useStore } from '@nanostores/react'
import type * as React from 'react'
import { useEffect, useState } from 'react'

import { Codicon } from '@/components/ui/codicon'
import { useI18n } from '@/i18n'
import { notifyError } from '@/store/notifications'
import {
  $projectContextFiles,
  $projectJobs,
  deleteProjectContextFile,
  readProjectContextFile,
  refreshProjectContext,
  requestStartWorkSession,
  writeProjectContextFile
} from '@/store/projects'

import { SidebarRowStack } from '../chrome'

// Shared context + subscriptions panels for the entered project
// (Cursor-Projects parity). Auto projects and the synthetic Home bucket have
// no projects.db row behind them, so the panels render nothing there.
export function ProjectContextSection({
  projectId,
  projectRootPath
}: {
  projectId: string
  projectRootPath: null | string
}) {
  const { t } = useI18n()
  const s = t.sidebar.projects
  const files = useStore($projectContextFiles)
  const jobs = useStore($projectJobs)
  const [viewing, setViewing] = useState<null | { content: string; name: string }>(null)
  const [editing, setEditing] = useState<null | { content: string; name: string }>(null)

  useEffect(() => {
    void refreshProjectContext(projectId).catch(err => notifyError(err, s.contextLoadFailed))

    return () => {
      $projectContextFiles.set([])
      $projectJobs.set([])
    }
  }, [projectId, s.contextLoadFailed])

  const openFile = async (name: string) => {
    try {
      const content = await readProjectContextFile(projectId, name)
      setViewing(content === null ? null : { content, name })
    } catch (err) {
      notifyError(err, s.contextLoadFailed)
    }
  }

  const save = async () => {
    if (!editing) {
      return
    }

    try {
      await writeProjectContextFile(projectId, editing.name, editing.content)
      setViewing({ content: editing.content, name: editing.name })
      setEditing(null)
    } catch (err) {
      notifyError(err, s.contextSaveFailed)
    }
  }

  const remove = async (name: string) => {
    try {
      await deleteProjectContextFile(projectId, name)

      if (viewing?.name === name) {
        setViewing(null)
      }
    } catch (err) {
      notifyError(err, s.contextSaveFailed)
    }
  }

  return (
    <SidebarRowStack className="gap-1 pb-2">
      <ContextPanel
        editing={editing}
        files={files}
        jobs={jobs}
        onAdd={() => setEditing({ content: '', name: '' })}
        onCoordinate={() => {
          // Seed a session at the project root whose first turn hands the
          // coordinator role to the agent (plan → delegate → verify).
          if (projectRootPath) {
            requestStartWorkSession(projectRootPath, s.coordinateDraft, { openTab: true })
          }
        }}
        onDelete={name => void remove(name)}
        onEdit={() => viewing && setEditing({ content: viewing.content, name: viewing.name })}
        onOpen={name => void openFile(name)}
        onSave={() => void save()}
        onViewingClose={() => setViewing(null)}
        s={s}
        setEditing={setEditing}
        viewing={viewing}
      />
    </SidebarRowStack>
  )
}

// One flat panel body — the two lists share the section shell; table-driven rows
// keep the branching minimal. Props bag beats threading eight callbacks twice.
function ContextPanel(props: {
  editing: null | { content: string; name: string }
  onCoordinate: () => void
  files: { name: string; size: number }[]
  jobs: { enabled: boolean; job_id: string; name: string; next_run_at: null | string; schedule: string; state: null | string }[]
  onAdd: () => void
  onDelete: (name: string) => void
  onEdit: () => void
  onOpen: (name: string) => void
  onSave: () => void
  onViewingClose: () => void
  setEditing: (next: null | { content: string; name: string }) => void
  s: ReturnType<typeof useI18n>['t']['sidebar']['projects']
  viewing: null | { content: string; name: string }
}) {
  const { s } = props

  return (
    <>
      <SectionShell
        action={
          <>
            <button
              className="cursor-pointer text-(--ui-text-tertiary) hover:text-(--ui-text-primary)"
              onClick={props.onCoordinate}
              title={s.coordinateTitle}
              type="button"
            >
              <Codicon name="rocket" size="0.75rem" />
            </button>
            <Codicon
              className="cursor-pointer text-(--ui-text-tertiary) hover:text-(--ui-text-primary)"
              name="add"
              onClick={props.onAdd}
            />
          </>
        }
        icon="notebook"
        label={s.contextTitle}
      >
        {props.files.length === 0 ? (
          <p className="px-2 py-1 text-xs text-(--ui-text-tertiary)">{s.contextEmpty}</p>
        ) : (
          props.files.map(file => (
            <div className="group flex items-center gap-1 px-2 py-0.5" key={file.name}>
              <button
                className="min-w-0 flex-1 truncate text-left text-xs hover:underline"
                onClick={() => props.onOpen(file.name)}
                type="button"
              >
                {file.name}
                <span className="ml-1.5 text-(--ui-text-tertiary)">{Math.max(1, Math.round(file.size / 1024))}k</span>
              </button>
              <Codicon
                className="hidden cursor-pointer text-(--ui-text-tertiary) hover:text-(--ui-text-primary) group-hover:block"
                name="trash"
                onClick={() => {
                  if (window.confirm(s.contextDeleteConfirm(file.name))) {
                    props.onDelete(file.name)
                  }
                }}
              />
            </div>
          ))
        )}
      </SectionShell>

      {props.viewing && !props.editing && (
        <SectionShell action={
          <>
            <Codicon className="cursor-pointer text-(--ui-text-tertiary) hover:text-(--ui-text-primary)" name="edit" onClick={props.onEdit} />
            <Codicon className="cursor-pointer text-(--ui-text-tertiary) hover:text-(--ui-text-primary)" name="close" onClick={props.onViewingClose} />
          </>
        } icon="file" label={props.viewing.name}>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap px-2 py-1 text-xs">{props.viewing.content}</pre>
        </SectionShell>
      )}

      {props.editing && (
        <SectionShell icon="edit" label={props.editing.name || s.contextNewFile}>
          <input
            className="mx-2 mb-1 rounded border border-(--ui-border) bg-transparent px-1.5 py-1 text-xs"
            onChange={event => props.setEditing({ content: props.editing?.content ?? '', name: event.target.value })}
            placeholder="CONTEXT.md"
            value={props.editing.name}
          />
          <textarea
            className="mx-2 mb-1 h-32 resize-none rounded border border-(--ui-border) bg-transparent px-1.5 py-1 font-mono text-xs"
            onChange={event => props.setEditing({ content: event.target.value, name: props.editing?.name ?? '' })}
            value={props.editing.content}
          />
          <div className="flex gap-2 px-2 pb-1">
            <button className="text-xs text-(--ui-accent) hover:underline" onClick={props.onSave} type="button">
              {s.contextSave}
            </button>
            <button className="text-xs text-(--ui-text-tertiary) hover:underline" onClick={() => props.setEditing(null)} type="button">
              {s.contextCancel}
            </button>
          </div>
        </SectionShell>
      )}

      <SectionShell icon="clock" label={s.subscriptionsTitle}>
        {props.jobs.length === 0 ? (
          <p className="px-2 py-1 text-xs text-(--ui-text-tertiary)">{s.subsEmpty}</p>
        ) : (
          props.jobs.map(job => (
            <div className="flex items-center gap-1.5 px-2 py-0.5 text-xs" key={job.job_id}>
              <span
                className={job.enabled ? 'text-(--ui-accent)' : 'text-(--ui-text-tertiary)'}
                title={job.state ?? (job.enabled ? 'enabled' : 'paused')}
              >
                ●
              </span>
              <span className="min-w-0 flex-1 truncate">{job.name}</span>
              <span className="shrink-0 text-(--ui-text-tertiary)">{job.schedule}</span>
            </div>
          ))
        )}
      </SectionShell>
    </>
  )
}

function SectionShell({
  action,
  children,
  icon,
  label
}: React.PropsWithChildren<{
  action?: React.ReactNode
  icon: string
  label: string
}>) {
  const [open, setOpen] = useState(true)

  return (
    <div>
      <div className="flex items-center gap-1 px-1 py-0.5">
        <Codicon
          className="cursor-pointer text-(--ui-text-tertiary)"
          name={open ? 'chevron-down' : 'chevron-right'}
          onClick={() => setOpen(!open)}
          size="0.7rem"
        />
        <Codicon className="shrink-0 text-(--ui-text-tertiary)" name={icon} size="0.7rem" />
        <span className="flex-1 text-[0.68rem] font-medium tracking-wide text-(--ui-text-secondary) uppercase">{label}</span>
        {action}
      </div>
      {open && <div className="pb-1">{children}</div>}
    </div>
  )
}
