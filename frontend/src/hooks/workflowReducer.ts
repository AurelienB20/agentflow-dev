import type { AgentId, FinalResult, Mode, NodeStatus, Phase, TaskType, Usage, WorkflowEvent } from '../types'

export interface AgentRuntime {
  status: NodeStatus
  runs: number
  totalMs: number
  lastMs: number | null
  startedAt: number | null
  inputs: Record<string, unknown> | null
  output: Record<string, unknown> | null
  summary: string | null
  outcome: string | null
  error: string | null
  history: { iteration: number; outcome: string; ms: number; summary: string }[]
}

export interface EdgeRuntime {
  id: string
  source: string
  target: string
  kind: string
  label: string
  count: number
  active: boolean
}

export interface ChatMessage {
  seq: number
  t: number
  timestamp: string
  sender: string
  receiver: string
  type: string
  content: string
}

export interface LogEntry {
  seq: number
  t: number
  kind: string // decision kinds + 'event'
  title: string
  detail?: string
  agent?: string | null
  isDecision: boolean
}

export interface RunState {
  phase: Phase
  mode: Mode | null
  workflowId: string | null
  provider: string | null
  model: string | null
  simulated: boolean
  cached: { at: number; model: string } | null
  taskType: TaskType | null
  classification: { confidence: number; reason: string } | null
  plan: { stages: string[][]; selected: string[]; skipped: string[]; subtasks: Record<string, string>; rationale: string } | null
  agents: Record<AgentId, AgentRuntime>
  resultStatus: NodeStatus
  edges: Record<string, EdgeRuntime>
  parallel: string[]
  messages: ChatMessage[]
  log: LogEntry[]
  iteration: number
  maxIterations: number
  qualityScores: number[]
  qualityThreshold: number
  usage: Usage | null
  final: FinalResult | null
  error: string | null
  elapsed: number
  eventCount: number
}

const AGENT_IDS: AgentId[] = ['orchestrator', 'analyzer', 'developer', 'tester', 'reviewer']

const blankAgent = (): AgentRuntime => ({
  status: 'waiting',
  runs: 0,
  totalMs: 0,
  lastMs: null,
  startedAt: null,
  inputs: null,
  output: null,
  summary: null,
  outcome: null,
  error: null,
  history: [],
})

export const initialRunState = (): RunState => ({
  phase: 'idle',
  mode: null,
  workflowId: null,
  provider: null,
  model: null,
  simulated: false,
  cached: null,
  taskType: null,
  classification: null,
  plan: null,
  agents: Object.fromEntries(AGENT_IDS.map((id) => [id, blankAgent()])) as Record<AgentId, AgentRuntime>,
  resultStatus: 'waiting',
  edges: {},
  parallel: [],
  messages: [],
  log: [],
  iteration: 0,
  maxIterations: 3,
  qualityScores: [],
  qualityThreshold: 8,
  usage: null,
  final: null,
  error: null,
  elapsed: 0,
  eventCount: 0,
})

const name = (id: string) => (id === 'result' ? 'Result' : id.charAt(0).toUpperCase() + id.slice(1))

function outcomeStatus(outcome: string): NodeStatus {
  switch (outcome) {
    case 'validation_failed':
      return 'failed'
    case 'below_threshold':
      return 'needs_review'
    case 'error':
      return 'failed'
    default:
      return 'completed'
  }
}

function patchAgent(state: RunState, id: AgentId, patch: Partial<AgentRuntime>): RunState['agents'] {
  return { ...state.agents, [id]: { ...state.agents[id], ...patch } }
}

export type Action = { type: 'event'; event: WorkflowEvent } | { type: 'reset' } | { type: 'start'; mode: Mode } | { type: 'error'; message: string }

export function reducer(state: RunState, action: Action): RunState {
  if (action.type === 'reset') return initialRunState()
  if (action.type === 'start') return { ...initialRunState(), phase: 'running', mode: action.mode }
  if (action.type === 'error') return { ...state, phase: 'failed', error: action.message }
  return applyEvent(state, action.event)
}

export function applyEvent(prev: RunState, e: WorkflowEvent): RunState {
  const s: RunState = { ...prev, elapsed: e.t, eventCount: prev.eventCount + 1 }
  const d = e.data
  const log = (entry: Omit<LogEntry, 'seq' | 't'>) => {
    s.log = [...s.log, { seq: e.seq, t: e.t, ...entry }]
  }

  switch (e.type) {
    case 'workflow_started':
      s.phase = 'running'
      s.workflowId = e.workflow_id
      s.provider = d.provider
      s.model = d.model
      s.simulated = Boolean(d.simulated)
      s.cached = d.cached ? { at: d.cached_at, model: d.cached_model } : null
      s.maxIterations = d.limits?.max_iterations ?? 3
      s.qualityThreshold = d.limits?.quality_threshold ?? 8
      s.agents = patchAgent(s, 'orchestrator', { status: 'running', startedAt: e.t })
      log({ kind: 'event', title: 'Workflow started', detail: d.request, isDecision: false, agent: 'orchestrator' })
      break

    case 'task_classified':
      s.taskType = d.task_type
      s.classification = { confidence: d.confidence, reason: d.reason }
      log({
        kind: 'classify',
        title: `Task classified as ${d.task_type}`,
        detail: `${d.reason} (confidence ${Math.round(d.confidence * 100)}%)`,
        isDecision: true,
        agent: 'orchestrator',
      })
      break

    case 'plan_created': {
      s.plan = { stages: d.stages, selected: d.selected_agents, skipped: d.skipped_agents, subtasks: d.subtasks, rationale: d.rationale }
      let agents = s.agents
      for (const id of d.skipped_agents as AgentId[]) agents = { ...agents, [id]: { ...agents[id], status: 'skipped' } }
      s.agents = agents
      break
    }

    case 'decision': {
      // a new routing decision: previous transitions are no longer "active"
      s.edges = Object.fromEntries(Object.entries(s.edges).map(([k, v]) => [k, { ...v, active: false }]))
      if (d.kind === 'retry' || d.kind === 'rework') {
        let agents = s.agents
        for (const id of d.next as AgentId[]) agents = { ...agents, [id]: { ...agents[id], status: 'needs_review' } }
        s.agents = agents
      }
      if (typeof d.iteration === 'number') s.iteration = d.iteration
      log({ kind: d.kind, title: d.decision, detail: d.reason, isDecision: true, agent: 'orchestrator' })
      break
    }

    case 'transition': {
      const id = `${d.source}->${d.target}`
      const existing = s.edges[id]
      s.edges = {
        ...s.edges,
        [id]: {
          id,
          source: d.source,
          target: d.target,
          kind: d.kind,
          label: d.label || existing?.label || '',
          count: (existing?.count ?? 0) + 1,
          active: true,
        },
      }
      break
    }

    case 'agent_started': {
      const id = e.agent as AgentId
      if (id === 'orchestrator') break
      const a = s.agents[id]
      s.agents = patchAgent(s, id, { status: 'running', runs: a.runs + 1, startedAt: e.t, inputs: d.inputs ?? null, error: null })
      log({
        kind: 'event',
        title: `${name(id)} ${a.runs > 0 ? 'restarted' : 'started'}`,
        isDecision: false,
        agent: id,
      })
      break
    }

    case 'agent_completed': {
      const id = e.agent as AgentId
      if (id === 'orchestrator') break
      const a = s.agents[id]
      const ms = d.duration_ms ?? 0
      s.agents = patchAgent(s, id, {
        status: outcomeStatus(d.outcome),
        lastMs: ms,
        totalMs: a.totalMs + ms,
        output: d.output ?? null,
        summary: d.summary ?? null,
        outcome: d.outcome,
        history: [...a.history, { iteration: d.iteration ?? 0, outcome: d.outcome, ms, summary: d.summary ?? '' }],
      })
      if (id === 'reviewer' && typeof d.output?.score === 'number') s.qualityScores = [...s.qualityScores, d.output.score]
      const verb: Record<string, string> = {
        validation_failed: 'Validation failed',
        approved: 'approved',
        rejected: 'requested changes',
        below_threshold: `approved, but quality ${d.output?.score ?? '?'}/10 is below the bar`,
      }
      log({
        kind: 'event',
        title: d.outcome === 'validation_failed' ? `${name(id)}: validation failed` : `${name(id)} ${verb[d.outcome] ?? 'completed'}`,
        detail: d.summary,
        isDecision: false,
        agent: id,
      })
      break
    }

    case 'agent_error': {
      const id = e.agent as AgentId
      const a = s.agents[id]
      s.agents = patchAgent(s, id, { status: 'failed', error: d.error, lastMs: d.duration_ms, totalMs: a.totalMs + (d.duration_ms ?? 0) })
      log({ kind: 'error', title: `${name(id)} error`, detail: d.error, isDecision: false, agent: id })
      break
    }

    case 'message':
      s.messages = [
        ...s.messages,
        { seq: e.seq, t: e.t, timestamp: e.timestamp, sender: d.sender, receiver: d.receiver, type: d.message_type, content: d.content },
      ]
      break

    case 'parallel_started':
      s.parallel = d.agents
      log({ kind: 'parallel', title: `Parallel execution: ${d.agents.map(name).join(' ‖ ')}`, isDecision: false, agent: 'orchestrator' })
      break

    case 'parallel_joined':
      s.parallel = []
      log({ kind: 'join', title: `Results aggregated from ${d.agents.map(name).join(' + ')}`, isDecision: false, agent: 'orchestrator' })
      break

    case 'iteration':
      s.iteration = d.iteration
      s.maxIterations = d.max_iterations
      break

    case 'usage':
      s.usage = d as Usage
      break

    case 'tool_result':
      log({
        kind: 'tool',
        title: 'Static checks (parser, code not executed)',
        detail: d.summary,
        isDecision: false,
        agent: 'tools',
      })
      break

    case 'workflow_completed': {
      const final = d.final_result as FinalResult
      s.phase = 'completed'
      s.final = final
      s.usage = final.usage ?? s.usage
      s.agents = patchAgent(s, 'orchestrator', { status: 'completed' })
      s.resultStatus = final.status === 'completed' ? 'completed' : 'needs_review'
      log({ kind: 'event', title: final.status === 'completed' ? 'Workflow completed' : 'Workflow stopped: correction limit reached', isDecision: false, agent: 'orchestrator' })
      break
    }

    case 'workflow_failed':
      s.phase = 'failed'
      s.error = d.error
      s.final = (d.final_result as FinalResult) ?? null
      s.agents = patchAgent(s, 'orchestrator', { status: 'failed' })
      s.resultStatus = 'failed'
      log({ kind: 'error', title: 'Workflow failed', detail: d.error, isDecision: false, agent: 'orchestrator' })
      break

    case 'workflow_cancelled':
      s.phase = 'cancelled'
      s.agents = patchAgent(s, 'orchestrator', { status: 'failed' })
      log({ kind: 'error', title: 'Workflow cancelled', detail: d.reason, isDecision: false, agent: 'orchestrator' })
      break
  }
  return s
}
