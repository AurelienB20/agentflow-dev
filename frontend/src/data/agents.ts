import { Brain, CodeXml, FlaskConical, ScanSearch, ShieldCheck, type LucideIcon } from 'lucide-react'
import type { AgentId, AgentMeta } from '../types'

// Static copy of GET /api/agents so the Guided Demo works with no backend.
export const AGENT_META: Record<AgentId, AgentMeta> = {
  orchestrator: {
    id: 'orchestrator',
    name: 'Orchestrator',
    role: 'Planning, routing & supervision',
    objective:
      'Classify the mission, select and sequence agents, react to their results and decide when the work is done.',
    responsibilities: [
      'Classify the request',
      'Select agents and decompose tasks',
      'Run independent agents in parallel',
      'Route on results (retry, rework, complete)',
      'Enforce iteration, time and budget limits',
    ],
  },
  analyzer: {
    id: 'analyzer',
    name: 'Analyzer Agent',
    role: 'Code & requirement analysis',
    objective: 'Understand the request and the code, then hand a structured diagnosis to the team.',
    responsibilities: [
      'Identify problems and potential bugs',
      'Understand context and requirements',
      'Rank issues by severity',
      'Recommend concrete next steps',
    ],
  },
  developer: {
    id: 'developer',
    name: 'Developer Agent',
    role: 'Code generation & correction',
    objective: 'Turn the diagnosis and the feedback of other agents into working code.',
    responsibilities: ['Fix bugs', 'Generate and improve functions', 'Apply recommendations', 'Incorporate Tester and Reviewer feedback'],
  },
  tester: {
    id: 'tester',
    name: 'Tester Agent',
    role: 'Test generation & validation',
    objective: 'Write tests, hunt edge cases and decide whether the code is ready to move on.',
    responsibilities: [
      'Generate pytest tests',
      'Identify edge cases',
      'Statically validate results',
      'Request a correction when validation fails',
      'Never claim unexecuted tests ran',
    ],
  },
  reviewer: {
    id: 'reviewer',
    name: 'Reviewer Agent',
    role: 'Quality control & final decision',
    objective: "Check the team's work against the request and accept or reject it.",
    responsibilities: ['Examine results', 'Check compliance with the request', 'Detect inconsistencies', 'Assess risks', 'Approve or send back for rework'],
  },
}

export const AGENT_ICON: Record<AgentId, LucideIcon> = {
  orchestrator: Brain,
  analyzer: ScanSearch,
  developer: CodeXml,
  tester: FlaskConical,
  reviewer: ShieldCheck,
}

export const AGENT_COLOR: Record<AgentId | 'result' | 'tools', string> = {
  tools: '#fbbf24',
  orchestrator: '#818cf8',
  analyzer: '#38bdf8',
  developer: '#a78bfa',
  tester: '#22d3ee',
  reviewer: '#34d399',
  result: '#e6e9f5',
}

// One plain sentence per agent, shown on the graph so the roles read at a glance.
export const AGENT_TAGLINE: Record<AgentId, string> = {
  orchestrator: 'Plans the work, hands it out',
  analyzer: 'Finds the problem',
  developer: 'Writes the fix',
  tester: 'Checks it with tests',
  reviewer: 'Approves or sends back',
}

export const WORKERS = ['analyzer', 'developer', 'tester', 'reviewer'] as const

export function agentLabel(id: string): string {
  if (id === 'result') return 'Result'
  if (id === 'tools') return 'Static checks'
  return AGENT_META[id as AgentId]?.name.replace(' Agent', '') ?? id
}
