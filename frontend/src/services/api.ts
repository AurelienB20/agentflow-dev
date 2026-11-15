import type { HealthInfo, TaskType, WorkflowEvent } from '../types'

// Empty string = same origin (Vite dev proxy or a reverse proxy in front of both).
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function sessionId(): string {
  const key = 'agentflow.session'
  try {
    const existing = localStorage.getItem(key)
    if (existing) return existing
    const id = crypto.randomUUID()
    localStorage.setItem(key, id)
    return id
  } catch {
    return 'anonymous'
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 8000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionId(), ...(init?.headers ?? {}) },
    })
    const isJson = res.headers.get('content-type')?.includes('application/json')
    const body = isJson ? await res.json() : null
    if (!res.ok) {
      const detail = body && typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`
      throw new ApiError(res.status, detail)
    }
    if (!isJson) throw new ApiError(res.status, 'Backend not reachable')
    return body as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    throw new ApiError(0, 'Backend not reachable')
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  health: () => request<HealthInfo>('/api/health', undefined, 6000),
  startWorkflow: (body: { scenario_id?: string; task_type: TaskType | 'auto'; code: string; request: string }) =>
    request<{ workflow_id: string; events_url: string; provider: string; model: string; simulated: boolean; cached: boolean }>(
      '/api/workflows',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  cancel: (id: string) => request<{ cancelled: boolean }>(`/api/workflows/${id}/cancel`, { method: 'POST' }),
}

const TERMINAL = new Set(['workflow_completed', 'workflow_failed', 'workflow_cancelled'])

/** Subscribe to a workflow's Server-Sent Events. EventSource reconnects and
 *  resumes with Last-Event-ID automatically; the backend replays history. */
export function subscribe(
  eventsUrl: string,
  onEvent: (e: WorkflowEvent) => void,
  onConnectionError: (msg: string) => void,
): () => void {
  const source = new EventSource(`${API_BASE}${eventsUrl}`)
  let lastSeq = 0
  let failures = 0
  source.addEventListener('workflow', (msg) => {
    failures = 0
    const event = JSON.parse((msg as MessageEvent).data) as WorkflowEvent
    if (event.seq <= lastSeq) return
    lastSeq = event.seq
    onEvent(event)
    if (TERMINAL.has(event.type)) source.close()
  })
  source.onerror = () => {
    failures += 1
    if (failures >= 5) {
      source.close()
      onConnectionError('Lost connection to the live stream.')
    }
  }
  return () => source.close()
}
