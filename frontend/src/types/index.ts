// Shared types — mirror backend/app/orchestration/events.py and schemas/.

export type AgentId = 'orchestrator' | 'analyzer' | 'developer' | 'tester' | 'reviewer'
export type WorkerId = Exclude<AgentId, 'orchestrator'>
export type TaskType = 'BUG_FIX' | 'TEST_GEN' | 'CODE_REVIEW'
export type NodeStatus = 'waiting' | 'running' | 'completed' | 'failed' | 'needs_review' | 'skipped'
export type Mode = 'demo' | 'live'
export type Phase = 'idle' | 'running' | 'completed' | 'failed' | 'cancelled'

export type EventType =
  | 'workflow_started'
  | 'task_classified'
  | 'plan_created'
  | 'decision'
  | 'transition'
  | 'agent_started'
  | 'agent_completed'
  | 'agent_error'
  | 'message'
  | 'parallel_started'
  | 'parallel_joined'
  | 'iteration'
  | 'usage'
  | 'tool_result'
  | 'workflow_completed'
  | 'workflow_failed'
  | 'workflow_cancelled'

export interface WorkflowEvent {
  seq: number
  workflow_id: string
  type: EventType
  agent: AgentId | null
  t: number
  timestamp: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>
}

export interface Scenario {
  id: string
  title: string
  short_title: string
  description: string
  task_type: TaskType
  highlights: string[]
  code: string
  request: string
}

export interface Recording {
  scenario: Scenario
  recording: {
    recorded_at: string
    engine: string
    provider: string
    model: string
    simulated: boolean
    status: string
    duration_s: number
  }
  events: WorkflowEvent[]
}

export interface AgentMeta {
  id: AgentId
  name: string
  role: string
  objective: string
  responsibilities: string[]
}

export interface Issue {
  title: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  line?: number | null
  detail: string
}

export interface TestResults {
  executed: boolean
  method: string
  passed: boolean
  failing_cases: string[]
  issues: string[]
  total_cases: number
}

export interface CaseTrace {
  case: string
  trace: string
  expected: string
  predicted: string
  passes: boolean
}

export interface Usage {
  calls: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
  max_cost_usd: number
}

export interface FinalResult {
  status: 'completed' | 'failed' | 'max_iterations_reached'
  reason: string
  task_type: TaskType
  agents_used: WorkerId[]
  skipped_agents: WorkerId[]
  steps: number
  iterations: number
  original_code: string
  final_code: string | null
  test_code: string | null
  test_results: TestResults | null
  analysis: { summary: string; issues: Issue[]; recommendations: string[] } | null
  review: {
    summary: string
    approved: boolean
    score: number
    rubric?: { correctness: number; edge_cases: number; robustness: number; readability: number }
    findings: string[]
    required_changes: string[]
    risks: string[]
  } | null
  usage: Usage
}

export interface HealthInfo {
  status: string
  live_mode: { available: boolean; provider: string; model: string | null; simulated: boolean }
  limits: Record<string, number>
}
