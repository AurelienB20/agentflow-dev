import { X } from 'lucide-react'
import { useEffect } from 'react'
import { AGENT_COLOR, AGENT_ICON, AGENT_META } from '../data/agents'
import type { RunState } from '../hooks/workflowReducer'
import type { AgentId } from '../types'
import { StatusBadge } from './StatusBadge'

function Json({ value }: { value: unknown }) {
  return (
    <pre className="code max-h-72 rounded-lg border border-line bg-[#0e1428] p-2.5 text-[11px] text-ink/85">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function AgentDetails({ id, run, onClose }: { id: AgentId; run: RunState; onClose: () => void }) {
  const meta = AGENT_META[id]
  const rt = run.agents[id]
  const Icon = AGENT_ICON[id]
  const color = AGENT_COLOR[id]

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const orchestratorData =
    id === 'orchestrator'
      ? {
          task_type: run.taskType,
          classification: run.classification,
          plan: run.plan,
          decisions: run.log.filter((l) => l.isDecision).length,
          usage: run.usage,
        }
      : null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose} role="dialog" aria-modal="true" aria-label={meta.name}>
      <aside
        className="fade-up flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-line bg-surface p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl" style={{ background: `${color}22`, color }}>
            <Icon size={22} aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-base font-semibold">{meta.name}</h3>
            <p className="text-[12px] text-muted">{meta.role}</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-[11.5px] text-muted">
          <StatusBadge status={rt.status} />
          {rt.runs > 0 && <span>Runs: {rt.runs}</span>}
          {rt.totalMs > 0 && <span>Total time: {(rt.totalMs / 1000).toFixed(1)}s</span>}
          {rt.lastMs != null && rt.runs > 1 && <span>Last run: {(rt.lastMs / 1000).toFixed(1)}s</span>}
        </div>

        <h4 className="mt-5 text-[11px] font-semibold tracking-wide text-muted uppercase">Objective</h4>
        <p className="mt-1 text-[12.5px] leading-relaxed">{meta.objective}</p>
        <ul className="mt-2 list-disc pl-5 text-[12px] text-ink/80">
          {meta.responsibilities.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        {run.plan?.subtasks[id] && (
          <>
            <h4 className="mt-5 text-[11px] font-semibold tracking-wide text-muted uppercase">Task assigned by the orchestrator</h4>
            <p className="mt-1 text-[12.5px] text-ink/90">{run.plan.subtasks[id]}</p>
          </>
        )}

        {orchestratorData ? (
          <>
            <h4 className="mt-5 text-[11px] font-semibold tracking-wide text-muted uppercase">Plan & state</h4>
            <div className="mt-1.5">
              <Json value={orchestratorData} />
            </div>
          </>
        ) : (
          <>
            <h4 className="mt-5 text-[11px] font-semibold tracking-wide text-muted uppercase">Input (latest run)</h4>
            <div className="mt-1.5">{rt.inputs ? <Json value={rt.inputs} /> : <p className="text-[12px] text-muted">Not started yet.</p>}</div>
            {rt.history.length > 0 && (
              <>
                <h4 className="mt-5 text-[11px] font-semibold tracking-wide text-muted uppercase">Run history</h4>
                <ol className="mt-1.5 flex flex-col gap-1.5">
                  {rt.history.map((h, i) => (
                    <li key={i} className="rounded-lg border border-line bg-surface-2/30 px-2.5 py-1.5 text-[11.5px]">
                      <span className="font-mono text-muted">
                        #{i + 1} · {h.outcome} · {(h.ms / 1000).toFixed(1)}s
                      </span>
                      <p className="mt-0.5 text-ink/85">{h.summary}</p>
                    </li>
                  ))}
                </ol>
              </>
            )}
            <h4 className="mt-5 text-[11px] font-semibold tracking-wide text-muted uppercase">Output (latest run)</h4>
            <div className="mt-1.5">
              {rt.error && <p className="mb-2 text-[12px] text-danger">{rt.error}</p>}
              {rt.output ? <Json value={rt.output} /> : <p className="text-[12px] text-muted">{rt.status === 'skipped' ? 'Not needed for this mission.' : 'No output yet.'}</p>}
            </div>
          </>
        )}
      </aside>
    </div>
  )
}
