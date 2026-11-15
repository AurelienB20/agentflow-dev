import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { Flag } from 'lucide-react'
import { memo } from 'react'
import { AGENT_COLOR, AGENT_ICON, AGENT_META, AGENT_TAGLINE, agentLabel } from '../data/agents'
import type { AgentRuntime } from '../hooks/workflowReducer'
import type { AgentId, NodeStatus } from '../types'
import { STATUS_STYLE, StatusBadge } from './StatusBadge'

export type AgentNodeData = { agentId: AgentId; runtime: AgentRuntime; parallel: boolean; selected: boolean }
export type AgentFlowNode = Node<AgentNodeData, 'agent'>

const OUTCOME_LABEL: Record<string, string> = {
  validation_failed: 'Validation failed',
  approved: 'Approved',
  rejected: 'Changes requested',
  below_threshold: 'Below quality bar',
}

function AgentNodeImpl({ data }: NodeProps<AgentFlowNode>) {
  const { agentId, runtime, parallel, selected } = data
  const meta = AGENT_META[agentId]
  const Icon = AGENT_ICON[agentId]
  const color = AGENT_COLOR[agentId]
  const status = runtime.status
  const border = status === 'waiting' ? '#2a3456' : STATUS_STYLE[status].color
  const isOrchestrator = agentId === 'orchestrator'
  const label = runtime.outcome && status !== 'running' ? OUTCOME_LABEL[runtime.outcome] : undefined

  return (
    <div
      className={`relative rounded-2xl border bg-surface/95 px-3.5 py-3 transition-all duration-300 ${
        status === 'running' ? 'node-running' : ''
      } ${status === 'skipped' ? 'opacity-40' : ''}`}
      style={{
        width: isOrchestrator ? 210 : 172,
        borderColor: selected ? '#e6e9f5' : border,
        boxShadow: status === 'running' ? `0 0 28px ${color}40` : selected ? '0 0 0 1px #e6e9f5' : undefined,
      }}
      role="button"
      aria-label={`${meta.name}: ${STATUS_STYLE[status].label}`}
    >
      <Handle type="target" position={Position.Top} id="in" />
      <Handle type="target" position={Position.Left} id="in-l" />
      <Handle type="target" position={Position.Right} id="in-r" />
      <Handle type="target" position={Position.Bottom} id="in-b" />
      <Handle type="source" position={Position.Bottom} id="out-b" />
      <Handle type="source" position={Position.Right} id="out-r" />
      <Handle type="source" position={Position.Left} id="out-l" />

      {parallel && (
        <span className="absolute -top-2.5 right-3 rounded-full bg-secondary px-2 py-0.5 text-[10px] font-semibold text-bg">
          PARALLEL
        </span>
      )}
      <div className="flex items-center gap-2.5">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl" style={{ background: `${color}22`, color }}>
          <Icon size={18} aria-hidden />
        </div>
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold text-ink">{agentLabel(agentId)}</div>
          <div className="text-[11px] leading-snug text-muted">{AGENT_TAGLINE[agentId]}</div>
        </div>
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2">
        <StatusBadge status={status} label={label} />
        <span className="font-mono text-[10.5px] text-muted">
          {runtime.runs > 1 && <span className="mr-1.5 text-warning">×{runtime.runs}</span>}
          {runtime.lastMs != null && status !== 'running' ? `${(runtime.totalMs / 1000).toFixed(1)}s` : ''}
        </span>
      </div>
      {status === 'running' && <div className="shimmer mt-2 h-0.5 rounded-full" />}
    </div>
  )
}

export const AgentNode = memo(AgentNodeImpl)

export type ResultNodeData = { status: NodeStatus; label: string }
export type ResultFlowNode = Node<ResultNodeData, 'result'>

function ResultNodeImpl({ data }: NodeProps<ResultFlowNode>) {
  const style = STATUS_STYLE[data.status]
  const done = data.status !== 'waiting'
  return (
    <div
      className="flex w-[150px] items-center justify-center gap-2 rounded-full border bg-surface px-3 py-2 transition-all duration-300"
      style={{ borderColor: done ? style.color : '#2a3456', boxShadow: done ? `0 0 24px ${style.color}33` : undefined }}
    >
      <Handle type="target" position={Position.Top} id="in" />
      <Handle type="target" position={Position.Left} id="in-l" />
      <Flag size={14} style={{ color: done ? style.color : '#8b93b0' }} aria-hidden />
      <span className="text-[12px] font-semibold" style={{ color: done ? style.color : '#8b93b0' }}>
        {data.label}
      </span>
    </div>
  )
}

export const ResultNode = memo(ResultNodeImpl)
