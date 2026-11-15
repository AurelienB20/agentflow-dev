import { CircleCheck, CircleDashed, CircleX, LoaderCircle, TriangleAlert, CirclePause } from 'lucide-react'
import type { NodeStatus } from '../types'

export const STATUS_STYLE: Record<NodeStatus, { label: string; color: string; bg: string }> = {
  waiting: { label: 'Waiting', color: '#8b93b0', bg: 'rgba(139,147,176,0.12)' },
  running: { label: 'Running', color: '#a5b4fc', bg: 'rgba(99,102,241,0.18)' },
  completed: { label: 'Completed', color: '#4ade80', bg: 'rgba(34,197,94,0.14)' },
  failed: { label: 'Failed', color: '#f87171', bg: 'rgba(239,68,68,0.14)' },
  needs_review: { label: 'Needs Review', color: '#fbbf24', bg: 'rgba(245,158,11,0.14)' },
  skipped: { label: 'Skipped', color: '#5b6382', bg: 'rgba(91,99,130,0.12)' },
}

const ICON = {
  waiting: CirclePause,
  running: LoaderCircle,
  completed: CircleCheck,
  failed: CircleX,
  needs_review: TriangleAlert,
  skipped: CircleDashed,
}

export function StatusBadge({ status, label }: { status: NodeStatus; label?: string }) {
  const s = STATUS_STYLE[status]
  const Icon = ICON[status]
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap"
      style={{ color: s.color, background: s.bg }}
    >
      <Icon size={12} className={status === 'running' ? 'animate-spin' : ''} aria-hidden />
      {label ?? s.label}
    </span>
  )
}
