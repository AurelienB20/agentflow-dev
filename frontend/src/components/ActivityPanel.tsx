import { ArrowRight, Brain, GitBranch, MessageSquare, Trophy } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { AGENT_COLOR, agentLabel } from '../data/agents'
import type { RunState } from '../hooks/workflowReducer'
import { ResultsPanel } from './ResultsPanel'

type Tab = 'messages' | 'decisions' | 'results'

const fmt = (t: number) => {
  const s = Math.floor(t)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

const TYPE_STYLE: Record<string, string> = {
  instruction: '#a5b4fc',
  analysis: '#38bdf8',
  code_proposal: '#c4b5fd',
  test_report: '#22d3ee',
  review: '#34d399',
  error: '#f87171',
  static_facts: '#fbbf24',
  check_failed: '#fb923c',
}

const DECISION_COLOR: Record<string, string> = {
  classify: '#a5b4fc',
  plan: '#a5b4fc',
  dispatch: '#818cf8',
  parallel: '#22d3ee',
  join: '#22d3ee',
  retry: '#f87171',
  rework: '#f87171',
  retry_error: '#fb923c',
  fallback: '#fb923c',
  complete: '#4ade80',
  limit: '#fbbf24',
  abort: '#f87171',
  error: '#f87171',
  event: '#5b6382',
  tool: '#fbbf24',
}

function AgentChip({ id }: { id: string }) {
  const color = AGENT_COLOR[id as keyof typeof AGENT_COLOR] ?? '#8b93b0'
  return (
    <span className="rounded-md px-1.5 py-0.5 text-[11px] font-semibold" style={{ color, background: `${color}1f` }}>
      {agentLabel(id)}
    </span>
  )
}

function useAutoScroll(dep: unknown) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 140
    if (nearBottom) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [dep])
  return ref
}

function Messages({ run }: { run: RunState }) {
  const ref = useAutoScroll(run.messages.length)
  if (!run.messages.length) return <Empty text="Messages exchanged between agents appear here." />
  return (
    <div ref={ref} className="flex h-full flex-col gap-2 overflow-y-auto p-3">
      {run.messages.map((m) => (
        <article key={m.seq} className="fade-up rounded-xl border border-line bg-surface-2/40 p-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <AgentChip id={m.sender} />
            <ArrowRight size={12} className="text-muted" aria-label="to" />
            <AgentChip id={m.receiver} />
            <span
              className="ml-auto rounded-full px-1.5 py-0.5 font-mono text-[10px]"
              style={{ color: TYPE_STYLE[m.type] ?? '#8b93b0', background: '#ffffff08' }}
            >
              {m.type}
            </span>
            <span className="font-mono text-[10px] text-muted">{fmt(m.t)}</span>
          </div>
          <p className="mt-1.5 text-[12px] leading-relaxed text-ink/90">{m.content}</p>
        </article>
      ))}
    </div>
  )
}

function Decisions({ run }: { run: RunState }) {
  const ref = useAutoScroll(run.log.length)
  if (!run.log.length) return <Empty text="The orchestrator's decision log appears here, with the reason for every routing choice." />
  return (
    <div ref={ref} className="h-full overflow-y-auto p-3">
      <ol className="relative ml-1.5 border-l border-line">
        {run.log.map((l) => {
          const color = DECISION_COLOR[l.kind] ?? '#818cf8'
          return (
            <li key={`${l.seq}-${l.title}`} className="fade-up relative mb-2.5 ml-3.5">
              <span
                className="absolute top-[5px] -left-[19.5px] h-2.5 w-2.5 rounded-full border-2 border-bg"
                style={{ background: l.isDecision ? color : '#2c3657' }}
              />
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-[10.5px] text-muted">[{fmt(l.t)}]</span>
                <span className={`text-[12.5px] ${l.isDecision ? 'font-semibold' : 'text-ink/80'}`} style={l.isDecision ? { color } : undefined}>
                  {l.isDecision && <span className="mr-1 text-[10px] tracking-wider text-muted uppercase">Decision ·</span>}
                  {l.title}
                </span>
              </div>
              {l.detail && (
                <p className={`mt-0.5 text-[11.5px] leading-relaxed ${l.isDecision ? 'text-ink/85' : 'text-muted'}`}>{l.detail}</p>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="grid h-full place-items-center p-6 text-center text-[12.5px] text-muted">{text}</div>
}

export function ActivityPanel({ run }: { run: RunState }) {
  const [tab, setTab] = useState<Tab>('decisions')
  useEffect(() => {
    if (run.phase === 'completed') setTab('results')
    if (run.phase === 'running' && run.eventCount <= 1) setTab('decisions')
  }, [run.phase, run.eventCount])

  const decisions = run.log.filter((l) => l.isDecision).length
  const tabs: { id: Tab; label: string; icon: typeof Brain; count?: number }[] = [
    { id: 'messages', label: 'Agent Messages', icon: MessageSquare, count: run.messages.length },
    { id: 'decisions', label: 'Orchestrator Decisions', icon: GitBranch, count: decisions },
    { id: 'results', label: 'Results', icon: Trophy },
  ]

  return (
    <section className="panel flex h-full min-h-[460px] flex-col overflow-hidden" aria-label="Agent activity">
      <div role="tablist" className="flex border-b border-line">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-2 py-3 text-[11.5px] font-medium transition ${
              tab === t.id ? 'border-primary text-ink' : 'border-transparent text-muted hover:text-ink'
            }`}
          >
            <t.icon size={13} aria-hidden />
            <span className="truncate">{t.label}</span>
            {t.count ? <span className="rounded-full bg-surface-2 px-1.5 font-mono text-[10px]">{t.count}</span> : null}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        {tab === 'messages' && <Messages run={run} />}
        {tab === 'decisions' && <Decisions run={run} />}
        {tab === 'results' && <ResultsPanel run={run} />}
      </div>
    </section>
  )
}
