import {
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { AGENT_COLOR, AGENT_ICON } from '../data/agents'
import topology from '../data/langgraph.json'
import type { NodeVisit, RunState } from '../hooks/workflowReducer'
import type { AgentId } from '../types'

// The real compiled LangGraph (exported by backend/scripts/record_demos.py, checked by a backend
// test): a star. Every agent returns to the orchestrator, whose conditional edge picks what runs next.

const START = '__start__'
const END = '__end__'
const W = 150

// Hub-and-spoke ring: the orchestrator in the middle, agents around it, START above, END below.
const POS: Record<string, { x: number; y: number }> = {
  [START]: { x: 165, y: 0 },
  analyzer: { x: 0, y: 75 },
  developer: { x: 270, y: 75 },
  orchestrator: { x: 135, y: 180 },
  tester: { x: 0, y: 285 },
  reviewer: { x: 270, y: 285 },
  [END]: { x: 165, y: 395 },
}

// [orchestrator side, agent side] for the dispatch edge (orchestrator -> agent) and the return edge.
const SIDES: Record<string, { out: [string, string]; back: [string, string] }> = {
  analyzer: { out: ['l', 'b'], back: ['t', 'r'] },
  developer: { out: ['r', 'b'], back: ['t', 'l'] },
  tester: { out: ['l', 't'], back: ['b', 'r'] },
  reviewer: { out: ['r', 't'], back: ['b', 'l'] },
}

type LGData = {
  id: string
  running: boolean
  flash: boolean
  visits: number
  step: number | null
  done: boolean
}
type LGNode = Node<LGData, 'lg'>

const SIDE_POS = {
  t: Position.Top,
  b: Position.Bottom,
  l: Position.Left,
  r: Position.Right,
} as const

function Handles() {
  return (
    <>
      {(Object.keys(SIDE_POS) as (keyof typeof SIDE_POS)[]).map((k) => (
        <span key={k}>
          <Handle type="source" position={SIDE_POS[k]} id={`${k}-s`} />
          <Handle type="target" position={SIDE_POS[k]} id={`${k}-t`} />
        </span>
      ))}
    </>
  )
}

function LGNodeImpl({ data }: NodeProps<LGNode>) {
  const terminal = data.id === START || data.id === END
  const lit = data.running || data.flash
  if (terminal) {
    const color = data.id === END && data.done ? '#4ade80' : data.id === START && data.visits ? '#818cf8' : '#8b93b0'
    return (
      <div
        className="grid h-8 w-[90px] place-items-center rounded-full border bg-surface font-mono text-[11px] font-semibold"
        style={{
          borderColor: color,
          color,
          boxShadow: data.done ? `0 0 18px ${color}55` : undefined,
        }}
      >
        <Handles />
        {data.id === START ? 'START' : 'END'}
      </div>
    )
  }
  const id = data.id as AgentId
  const color = AGENT_COLOR[id]
  const Icon = AGENT_ICON[id]
  return (
    <div
      className={`rounded-xl border bg-surface px-3 py-2 transition-all duration-200 ${data.running ? 'node-running' : ''}`}
      style={{
        width: W,
        borderColor: lit ? color : data.visits ? `${color}66` : '#2a3456',
        boxShadow: lit ? `0 0 26px ${color}66` : undefined,
        background: lit ? `color-mix(in srgb, ${color} 14%, var(--surface))` : undefined,
      }}
    >
      <Handles />
      <div className="flex items-center gap-2">
        <Icon size={15} style={{ color }} aria-hidden />
        <span className="font-mono text-[12px] font-semibold text-ink">{id}</span>
        {data.visits > 0 && <span className="ml-auto font-mono text-[10px] text-muted">×{data.visits}</span>}
      </div>
      <div className="mt-1 h-4 text-[10.5px]" style={{ color: lit ? color : '#8b93b0' }}>
        {data.running ? `● running · step ${data.step}` : data.flash ? `● routing · step ${data.step}` : data.visits ? 'done' : 'idle'}
      </div>
    </div>
  )
}

const nodeTypes = { lg: memo(LGNodeImpl) }

/** Edges to light up now: the hop that led into each running node (or the orchestrator's last routing). */
function activeEdges(trace: NodeVisit[], phase: RunState['phase']): Set<string> {
  const active = new Set<string>()
  if (!trace.length) return active
  if (phase === 'completed') {
    active.add(`orchestrator->${END}`)
    return active
  }
  const running = trace.filter((v) => v.running)
  for (const v of running) {
    if (v.node !== 'orchestrator') active.add(`orchestrator->${v.node}`)
    else if (v.step === 1) active.add(`${START}->orchestrator`)
    else for (const p of trace.filter((x) => x.step === v.step - 1)) active.add(`${p.node}->orchestrator`)
  }
  if (!running.length) {
    const last = trace.at(-1)!
    if (last.node === 'orchestrator') for (const r of last.routesTo) active.add(`orchestrator->${r}`)
    else active.add(`${last.node}->orchestrator`)
  }
  return active
}

function useOrchestratorFlash(trace: NodeVisit[]): { node: string; step: number } | null {
  // The orchestrator decides in a few milliseconds: keep it lit briefly so the eye can follow the hop.
  const [flash, setFlash] = useState<{ node: string; step: number } | null>(null)
  const seen = useRef(0)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    if (trace.length < seen.current) seen.current = 0 // a new run started
    const fresh = trace.slice(seen.current).filter((v) => v.node === 'orchestrator')
    seen.current = trace.length
    if (!fresh.length) return
    const v = fresh.at(-1)!
    setFlash({ node: v.node, step: v.step })
    // Not cleared on the next trace update (the node's own exit event would cancel it at once).
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setFlash(null), 900)
  }, [trace])
  useEffect(() => () => clearTimeout(timer.current), [])
  return flash
}

function Graph({ run }: { run: RunState }) {
  const { fitView } = useReactFlow()
  const flash = useOrchestratorFlash(run.trace)
  const built = useMemo(() => {
    const visits: Record<string, number> = {}
    for (const v of run.trace) visits[v.node] = (visits[v.node] ?? 0) + 1
    const traversed: Record<string, number> = {}
    run.trace.forEach((v, i) => {
      if (v.node === 'orchestrator') {
        if (v.step === 1) traversed[`${START}->orchestrator`] = 1
        for (const r of v.routesTo) traversed[`orchestrator->${r}`] = (traversed[`orchestrator->${r}`] ?? 0) + 1
      } else if (!v.running && run.trace.slice(i).some((x) => x.node === 'orchestrator' && x.step > v.step)) {
        traversed[`${v.node}->orchestrator`] = (traversed[`${v.node}->orchestrator`] ?? 0) + 1
      }
    })
    const active = activeEdges(run.trace, run.phase)
    const runningAt = Object.fromEntries(run.trace.filter((v) => v.running).map((v) => [v.node, v.step]))

    const nodes: LGNode[] = topology.nodes.map((id) => ({
      id,
      type: 'lg',
      position: POS[id],
      draggable: false,
      data: {
        id,
        running: id in runningAt,
        flash: flash?.node === id && !(id in runningAt) && run.phase === 'running',
        visits: id === START ? (run.trace.length ? 1 : 0) : (visits[id] ?? 0),
        step: runningAt[id] ?? (flash?.node === id ? flash.step : null),
        done: id === END && run.phase === 'completed',
      },
    }))

    const edges: Edge[] = topology.edges.map((e) => {
      const key = `${e.source}->${e.target}`
      let sh = 'b-s'
      let th = 't-t'
      if (e.source === 'orchestrator' && SIDES[e.target]) [sh, th] = [`${SIDES[e.target].out[0]}-s`, `${SIDES[e.target].out[1]}-t`]
      else if (e.target === 'orchestrator' && SIDES[e.source]) [sh, th] = [`${SIDES[e.source].back[1]}-s`, `${SIDES[e.source].back[0]}-t`]
      const on = active.has(key)
      const used = traversed[key] ?? 0
      const color = on ? '#e6e9f5' : e.conditional ? '#818cf8' : '#64748b'
      return {
        id: key,
        source: e.source,
        target: e.target,
        sourceHandle: sh,
        targetHandle: th,
        type: 'straight',
        animated: on,
        label: used > 1 ? `×${used}` : undefined,
        labelStyle: { fill: '#cbd5e1', fontSize: 10 },
        labelBgStyle: { fill: '#111827' },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
          width: 14,
          height: 14,
        },
        style: {
          stroke: color,
          strokeWidth: on ? 2.6 : used ? 1.6 : 1.1,
          strokeDasharray: e.conditional && !on ? '5 4' : undefined,
          opacity: on ? 1 : used ? 0.8 : 0.3,
        },
        zIndex: on ? 10 : 1,
      } as Edge
    })
    return { nodes, edges }
  }, [run.trace, run.phase, flash])

  // Keep React Flow's measured sizes: passing fresh node objects on every event would hide the
  // nodes until they are measured again, which never happens when their size does not change.
  const [nodes, setNodes, onNodesChange] = useNodesState<LGNode>(built.nodes)
  useEffect(() => {
    setNodes((prev) =>
      built.nodes.map((n) => {
        const old = prev.find((p) => p.id === n.id)
        return old ? { ...old, data: n.data } : n
      }),
    )
  }, [built, setNodes])

  useEffect(() => {
    const ro = new ResizeObserver(() => requestAnimationFrame(() => fitView({ padding: 0.08 })))
    const el = document.getElementById('lg-flow')
    if (el) ro.observe(el)
    return () => ro.disconnect()
  }, [fitView])

  return (
    <div id="lg-flow" className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={built.edges}
        onNodesChange={onNodesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        minZoom={0.3}
        maxZoom={1.5}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
      />
    </div>
  )
}

function StepList({ run }: { run: RunState }) {
  const steps = useMemo(() => {
    const by = new Map<number, NodeVisit[]>()
    for (const v of run.trace) by.set(v.step, [...(by.get(v.step) ?? []), v])
    return [...by.entries()]
  }, [run.trace])
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // Scroll the step list only (scrollIntoView would also scroll the page on phones).
    const box = end.current?.closest('[data-steps]')
    if (box) box.scrollTop = box.scrollHeight
  }, [steps.length])

  if (!steps.length)
    return (
      <p className="px-4 py-3 text-[12px] text-muted">
        {run.phase === 'idle'
          ? 'Launch the agents: each LangGraph step will be listed here as it runs.'
          : 'This run carries no node trace (recorded before tracing was added).'}
      </p>
    )
  return (
    <ol className="space-y-1 px-4 py-2 font-mono text-[11.5px]">
      {steps.map(([step, visits]) => {
        const live = visits.some((v) => v.running)
        const orch = visits.find((v) => v.node === 'orchestrator')
        return (
          <li key={step} className={`flex gap-2 ${live ? 'text-ink' : 'text-muted'}`}>
            <span className="w-14 shrink-0" style={{ color: live ? '#e6e9f5' : undefined }}>
              step {step}
            </span>
            <span className="min-w-0">
              {visits.map((v, i) => (
                <span key={v.node}>
                  {i > 0 && <span className="text-secondary"> ‖ </span>}
                  <span style={{ color: AGENT_COLOR[v.node as AgentId] }}>{v.node}</span>
                </span>
              ))}
              {visits.length > 1 && <span className="text-secondary"> (parallel)</span>}
              {orch && !orch.running && <span> → {orch.routesTo.map((r) => (r === END ? 'END' : r)).join(' ‖ ')}</span>}
              {live && <span className="text-warning"> · running…</span>}
              {!live && !orch && (
                <span className="block text-[10.5px] text-muted/80">
                  wrote {[...new Set(visits.flatMap((v) => v.updatedKeys))].filter((k) => k !== 'completed_steps').join(', ') || '—'}
                </span>
              )}
            </span>
          </li>
        )
      })}
      <div ref={end} />
    </ol>
  )
}

export function LangGraphView({ run }: { run: RunState }) {
  return (
    <div className="flex h-full flex-col">
      <p className="px-4 pt-2 text-[11.5px] text-muted">
        The real compiled LangGraph: every agent returns to the <span className="font-mono text-ink">orchestrator</span>, whose conditional
        edge (dashed) picks the next node. The lit node is where the run is now.
      </p>
      <div className="min-h-[300px] flex-1">
        <ReactFlowProvider>
          <Graph run={run} />
        </ReactFlowProvider>
      </div>
      <div data-steps className="max-h-[38%] min-h-[96px] overflow-y-auto border-t border-line">
        <StepList run={run} />
      </div>
    </div>
  )
}
