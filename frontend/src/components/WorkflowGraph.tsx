import {
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Clock, Gauge, MessageSquareText, Network, Repeat, Zap } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { RunState } from '../hooks/workflowReducer'
import type { AgentId } from '../types'
import { AGENT_TAGLINE, agentLabel } from '../data/agents'
import { AgentNode, ResultNode } from './AgentNode'
import { STATUS_STYLE } from './StatusBadge'

const nodeTypes = { agent: AgentNode, result: ResultNode }

const ROW: AgentId[] = ['analyzer', 'developer', 'tester', 'reviewer']
type Layout = 'horizontal' | 'vertical'

// Horizontal: orchestrator above a row of agents. Vertical (narrow screens): a column.
const POS: Record<Layout, Record<string, { x: number; y: number }>> = {
  horizontal: {
    orchestrator: { x: 281, y: 0 },
    analyzer: { x: 0, y: 175 },
    developer: { x: 200, y: 175 },
    tester: { x: 400, y: 175 },
    reviewer: { x: 600, y: 175 },
    result: { x: 316, y: 385 },
  },
  vertical: {
    orchestrator: { x: -19, y: 0 },
    analyzer: { x: 0, y: 150 },
    developer: { x: 0, y: 268 },
    tester: { x: 0, y: 386 },
    reviewer: { x: 0, y: 504 },
    result: { x: 11, y: 630 },
  },
}

const KIND_COLOR: Record<string, string> = {
  dispatch: '#818cf8',
  handoff: '#818cf8',
  parallel: '#22d3ee',
  join: '#22d3ee',
  retry: '#f87171',
  error_retry: '#fb923c',
  complete: '#4ade80',
  stop: '#fbbf24',
}

// Plain-language narration of the latest step, so a first-time visitor follows the run without
// opening the logs.
function narration(run: RunState): { title: string; detail?: string; now?: string; tone: string } {
  if (run.phase === 'idle')
    return {
      title: 'Press Launch Agents to start.',
      detail: 'The Orchestrator reads the mission, hands each step to the right agent, and sends the work back whenever a check fails.',
      tone: '#e6e9f5',
    }
  if (run.phase === 'failed') return { title: 'The workflow failed.', detail: run.error ?? undefined, tone: '#f87171' }
  if (run.phase === 'cancelled') return { title: 'Replay stopped.', tone: '#8b93b0' }
  if (run.phase === 'completed') {
    const r = run.final?.review
    return {
      title: run.final?.status === 'completed' ? 'Done: the work is delivered.' : 'Stopped at the correction limit.',
      detail: r
        ? `Reviewer ${r.approved ? 'approved' : 'did not approve'} with quality ${r.score}/10 after ${run.iteration} correction(s). See Results for the code.`
        : 'See Results for the details.',
      tone: run.final?.status === 'completed' ? '#4ade80' : '#fbbf24',
    }
  }
  // "X started" lines carry no information: narrate the latest meaningful step instead.
  const last = run.log.findLast((e) => !/\b(re)?started$/.test(e.title))
  const working = (Object.keys(run.agents) as AgentId[])
    .filter((id) => id !== 'orchestrator' && run.agents[id].status === 'running')
    .map((id) => `${agentLabel(id)} (${AGENT_TAGLINE[id].toLowerCase()})`)
  const now = working.length ? `Now working: ${working.join(' and ')}.` : undefined
  if (!last) return { title: 'The Orchestrator is reading the mission…', now, tone: '#818cf8' }
  const tone = last.kind === 'retry' || last.kind === 'rework' ? '#f87171' : last.isDecision ? '#818cf8' : '#e6e9f5'
  return { title: last.isDecision ? `Orchestrator: ${last.title}` : last.title, detail: last.detail, now, tone }
}

function NowBar({ run }: { run: RunState }) {
  const n = narration(run)
  return (
    <div className="flex items-start gap-2.5 border-b border-line bg-surface-2/40 px-4 py-2.5" aria-live="polite">
      <MessageSquareText size={16} className="mt-0.5 shrink-0" style={{ color: n.tone }} aria-hidden />
      <div className="min-w-0">
        <div key={n.title} className="fade-up text-[13.5px] font-semibold" style={{ color: n.tone }}>
          {n.title}
        </div>
        {n.detail && <div className="line-clamp-2 text-[12px] text-ink/75">{n.detail}</div>}
        {n.now && <div className="mt-0.5 text-[11.5px] text-secondary">{n.now}</div>}
      </div>
    </div>
  )
}

const TASK_LABEL: Record<string, string> = { BUG_FIX: 'Bug fix', TEST_GEN: 'Test generation', CODE_REVIEW: 'Code review' }

function resultLabel(run: RunState): string {
  if (run.phase === 'completed') return run.final?.status === 'completed' ? 'Workflow complete' : 'Stopped at limit'
  if (run.phase === 'failed') return 'Workflow failed'
  if (run.phase === 'cancelled') return 'Cancelled'
  return 'Result'
}

function buildGraph(run: RunState, selected: string | null, layout: Layout): { nodes: Node[]; edges: Edge[] } {
  const pos = POS[layout]
  const vertical = layout === 'vertical'
  const nodes: Node[] = (['orchestrator', ...ROW] as AgentId[]).map((id) => ({
    id,
    type: 'agent',
    position: pos[id],
    data: { agentId: id, runtime: run.agents[id], parallel: run.parallel.includes(id), selected: selected === id },
    draggable: false,
  }))
  nodes.push({
    id: 'result',
    type: 'result',
    position: pos.result,
    data: { status: run.resultStatus, label: resultLabel(run) },
    draggable: false,
  })

  const edges: Edge[] = []
  // Static dispatch lines from the orchestrator to every agent.
  for (const id of ROW) {
    const live = run.edges[`orchestrator->${id}`]
    const selectedAgent = run.plan?.selected.includes(id)
    const skipped = run.agents[id].status === 'skipped'
    const color = live ? KIND_COLOR[live.kind] ?? '#818cf8' : '#3b4a7a'
    edges.push({
      id: `dispatch-${id}`,
      source: 'orchestrator',
      sourceHandle: vertical ? 'out-r' : 'out-b',
      target: id,
      targetHandle: vertical ? 'in-r' : 'in',
      type: vertical ? 'smoothstep' : 'default',
      pathOptions: vertical ? { offset: 62, borderRadius: 14 } : undefined,
      animated: Boolean(live?.active),
      style: {
        stroke: color,
        strokeWidth: live?.active ? 2.2 : 1.2,
        strokeDasharray: live?.active ? undefined : '5 5',
        opacity: skipped ? 0.12 : live?.active ? 1 : selectedAgent ? 0.7 : 0.35,
      },
    } as Edge)
  }
  // Dynamic transitions recorded by the backend.
  for (const e of Object.values(run.edges)) {
    if (e.source === 'orchestrator') continue
    const color = KIND_COLOR[e.kind] ?? '#818cf8'
    const si = ROW.indexOf(e.source as AgentId)
    const ti = e.target === 'result' ? ROW.length : ROW.indexOf(e.target as AgentId)
    const adjacent = ti === si + 1
    const backward = ti < si
    let sourceHandle: string, targetHandle: string, offset: number
    if (vertical) {
      if (adjacent) [sourceHandle, targetHandle, offset] = ['out-b', 'in', 0]
      else if (backward) [sourceHandle, targetHandle, offset] = ['out-r', 'in-r', 30]
      else [sourceHandle, targetHandle, offset] = ['out-l', 'in-l', 26]
    } else if (e.target === 'result') [sourceHandle, targetHandle, offset] = ['out-b', 'in', 20]
    else if (adjacent) [sourceHandle, targetHandle, offset] = ['out-r', 'in-l', 0]
    else [sourceHandle, targetHandle, offset] = ['out-b', 'in-b', backward ? 52 : e.kind === 'join' ? 30 : 18]
    const straight = offset === 0
    const label = [e.label, e.count > 1 ? `×${e.count}` : ''].filter(Boolean).join(' ')
    edges.push({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle,
      targetHandle,
      type: straight ? 'straight' : 'smoothstep',
      pathOptions: straight ? undefined : { offset, borderRadius: 14 },
      animated: e.active,
      label: label || undefined,
      labelStyle: { fill: color, fontSize: 10.5, fontWeight: 600 },
      labelBgPadding: [6, 3],
      labelBgBorderRadius: 6,
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      style: { stroke: color, strokeWidth: e.active ? 2.4 : 1.6, opacity: e.active ? 1 : 0.5 },
      zIndex: e.active ? 10 : 1,
    } as Edge)
  }
  return { nodes, edges }
}

function Graph({ run, selected, onSelect }: Props) {
  const { fitView } = useReactFlow()
  const ref = useRef<HTMLDivElement>(null)
  const [layout, setLayout] = useState<Layout>(() => (window.innerWidth < 640 ? 'vertical' : 'horizontal'))
  const built = useMemo(() => buildGraph(run, selected, layout), [run, selected, layout])
  // Keep node objects stable so React Flow retains their measured size.
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(built.nodes)
  useEffect(() => {
    setNodes((prev) =>
      built.nodes.map((n) => {
        const old = prev.find((p) => p.id === n.id)
        return old ? { ...old, position: n.position, data: n.data } : n
      }),
    )
  }, [built, setNodes])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      const next: Layout = el.clientWidth < 520 ? 'vertical' : 'horizontal'
      setLayout(next)
      requestAnimationFrame(() => fitView({ padding: 0.1, duration: 200 }))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [fitView])
  useEffect(() => {
    const id = setTimeout(() => fitView({ padding: 0.1, duration: 250 }), 60)
    return () => clearTimeout(id)
  }, [layout, fitView])

  return (
    <div ref={ref} className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        onNodesChange={onNodesChange}
        edges={built.edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.1 }}
        minZoom={0.3}
        maxZoom={1.6}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        onNodeClick={(_, node) => node.id !== 'result' && onSelect(node.id as AgentId)}
        proOptions={{ hideAttribution: true }}
      >
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  )
}

interface Props {
  run: RunState
  selected: AgentId | null
  onSelect: (id: AgentId) => void
}

export function WorkflowGraph(props: Props) {
  const { run } = props
  const mm = Math.floor(run.elapsed / 60)
  const ss = Math.floor(run.elapsed % 60)
  return (
    <section className="panel flex h-full min-h-[440px] flex-col overflow-hidden" aria-label="Multi-agent workflow graph">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <Network size={16} className="text-primary" aria-hidden />
        <h2 className="text-sm font-semibold">Multi-Agent Workflow</h2>
        <div className="ml-auto flex flex-wrap items-center gap-1.5 text-[11px]">
          {run.taskType && (
            <span className="rounded-full border border-line px-2 py-0.5 text-muted">{TASK_LABEL[run.taskType]}</span>
          )}
          {run.phase !== 'idle' && (
            <span className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 font-mono text-muted">
              <Clock size={11} aria-hidden /> {String(mm).padStart(2, '0')}:{String(ss).padStart(2, '0')}
            </span>
          )}
          {run.qualityScores.length > 0 && (
            <span
              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono"
              style={{
                borderColor: run.qualityScores.at(-1)! >= run.qualityThreshold ? '#22c55e55' : '#f59e0b55',
                color: run.qualityScores.at(-1)! >= run.qualityThreshold ? '#4ade80' : '#fbbf24',
              }}
              title={`Reviewer quality score per round (bar: ${run.qualityThreshold})`}
            >
              <Gauge size={11} aria-hidden /> {run.qualityScores.join(' → ')}
            </span>
          )}
          {run.phase !== 'idle' && (
            <span
              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono"
              style={{
                borderColor: run.iteration ? '#f59e0b55' : 'var(--border)',
                color: run.iteration ? '#fbbf24' : 'var(--muted)',
              }}
              title="Correction loops used / allowed"
            >
              <Repeat size={11} aria-hidden /> {run.iteration}/{run.maxIterations}
            </span>
          )}
        </div>
      </header>
      <NowBar run={run} />
      <div className="relative flex-1">
        {run.parallel.length > 1 && (
          <div className="fade-up absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded-full border border-secondary/40 bg-secondary/10 px-3 py-1 text-[11.5px] font-medium text-secondary">
            <Zap size={12} className="mr-1 inline" aria-hidden />
            Parallel execution · {run.parallel.map((a) => a[0].toUpperCase() + a.slice(1)).join(' ‖ ')}
          </div>
        )}
        {run.phase === 'idle' && (
          <div className="pointer-events-none absolute inset-x-0 top-3 z-10 text-center text-[11.5px] text-muted">
            Click any agent to see what it does
          </div>
        )}
        <ReactFlowProvider>
          <Graph {...props} />
        </ReactFlowProvider>
        <div className="pointer-events-none absolute bottom-3 left-3 hidden flex-wrap gap-x-3 gap-y-1 text-[10.5px] text-muted sm:flex">
          {(['running', 'completed', 'failed', 'needs_review', 'skipped'] as const).map((s) => (
            <span key={s} className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full" style={{ background: STATUS_STYLE[s].color }} />
              {STATUS_STYLE[s].label}
            </span>
          ))}
          <span className="inline-flex items-center gap-1">
            <span className="h-0.5 w-3 bg-danger" /> correction loop
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-0.5 w-3 bg-secondary" /> parallel / aggregation
          </span>
        </div>
      </div>
    </section>
  )
}
