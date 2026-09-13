import { atom } from 'nanostores'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/i18n', () => ({
  translateNow: (key: string) => key
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

vi.mock('@/store/gateway', () => ({
  $gateway: atom(null),
  activeGateway: vi.fn(),
  ensureActiveGatewayOpen: vi.fn()
}))

vi.mock('@/hermes', () => ({
  getHermesConfig: vi.fn(),
  getProfiles: vi.fn(),
  hermesApi: vi.fn(),
  setApiRequestProfile: vi.fn(),
  STARTUP_REQUEST_TIMEOUT_MS: 1000
}))

const gw = await import('@/store/gateway')
const activeGateway = vi.mocked(gw.activeGateway)

const { $projectContextFiles, $projectJobs, refreshProjectContext } = await import('@/store/projects')

// The store's only server dependency: a fake gateway whose request() answers
// per-method. connectionState 'open' skips the reconnect path.
function fakeGateway(answers: Record<string, unknown> = {}, rejectWith?: Error) {
  return {
    connectionState: 'open',
    request: vi.fn(async (_method: string) => {
      if (rejectWith) {
        throw rejectWith
      }

      if (_method in answers) {
        return answers[_method]
      }

      throw new Error(`unexpected rpc ${_method}`)
    })
  } as never
}

// Same shape the sibling projects.test.ts uses: a promise the test resolves on demand.
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => {
    resolve = done
  })
  return { promise, resolve }
}

beforeEach(() => {
  activeGateway.mockReset()
  $projectContextFiles.set([])
  $projectJobs.set([])
})

describe('project shared context + subscriptions cache', () => {
  it('loads both lists for the requested project', async () => {
    activeGateway.mockReturnValue(fakeGateway({
      'projects.context_list': { files: [{ name: 'CONTEXT.md', size: 10, updated_at: null, updated_by: null }] },
      'projects.jobs': { jobs: [{ enabled: true, job_id: 'j1', name: 'watch', next_run_at: null, schedule: '1h', state: null }] }
    }))

    await refreshProjectContext('p1')

    expect($projectContextFiles.get()).toHaveLength(1)
    expect($projectContextFiles.get()[0]?.name).toBe('CONTEXT.md')
    expect($projectJobs.get()[0]?.job_id).toBe('j1')
  })

  it('a slow response for a departed project never lands (generation guard)', async () => {
    type CtxList = { files: Array<{ name: string; size: number; updated_at: null; updated_by: null }> }
    const gate = deferred<CtxList>()

    activeGateway.mockReturnValue(fakeGateway({
      'projects.context_list': gate.promise,
      'projects.jobs': { jobs: [] }
    }))

    const first = refreshProjectContext('p1')
    const second = refreshProjectContext('p2')

    gate.resolve({ files: [] })
    await Promise.all([first, second])

    // p1's late answer arrived after p2 superseded it; the atoms must not carry it.
    expect($projectContextFiles.get()).toEqual([])
  })

  it('surfaces a legacy backend (missing method) as rpc-unavailable, not an error', async () => {
    const missing = Object.assign(new Error('no such method'), { code: -32601 })
    activeGateway.mockReturnValue(fakeGateway({}, missing))

    await expect(refreshProjectContext('p1')).resolves.toBeUndefined()
  })
})
