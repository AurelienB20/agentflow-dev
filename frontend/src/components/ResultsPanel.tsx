import { CircleCheck, CircleX, Coins, FlaskConical, Info, Repeat, TriangleAlert, Users } from 'lucide-react'
import { agentLabel } from '../data/agents'
import type { RunState } from '../hooks/workflowReducer'
import type { CaseTrace, FinalResult, Issue } from '../types'
import { CodeDiff, CodeView } from './CodeEditor'

const SEVERITY: Record<Issue['severity'], string> = {
  critical: '#f87171',
  high: '#fb923c',
  medium: '#fbbf24',
  low: '#8b93b0',
}

function Stat({ icon: Icon, label, value }: { icon: typeof Users; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2/40 px-3 py-2">
      <div className="flex items-center gap-1 text-[10.5px] text-muted uppercase">
        <Icon size={11} aria-hidden /> {label}
      </div>
      <div className="mt-0.5 text-[13px] font-semibold text-ink">{value}</div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-[11px] font-semibold tracking-wide text-muted uppercase">{title}</h4>
      {children}
    </div>
  )
}

function Issues({ issues }: { issues: Issue[] }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {issues.map((i) => (
        <li key={i.title} className="rounded-lg border border-line bg-surface-2/30 px-2.5 py-2 text-[12px]">
          <div className="flex items-center gap-2">
            <span className="rounded px-1.5 py-0.5 font-mono text-[10px] uppercase" style={{ color: SEVERITY[i.severity], background: `${SEVERITY[i.severity]}1a` }}>
              {i.severity}
            </span>
            <span className="font-medium">{i.title}</span>
            {i.line ? <span className="ml-auto font-mono text-[10px] text-muted">L{i.line}</span> : null}
          </div>
          <p className="mt-1 text-muted">{i.detail}</p>
        </li>
      ))}
    </ul>
  )
}

const RUBRIC_LABEL = { correctness: 'Correctness', edge_cases: 'Edge cases', robustness: 'Robustness', readability: 'Readability' }

function Verdict({ final, scores, threshold }: { final: FinalResult; scores: number[]; threshold: number }) {
  const r = final.review
  if (!r) return null
  const ok = r.approved
  return (
    <div className={`rounded-xl border p-3 ${ok ? 'border-success/40 bg-success/8' : 'border-warning/40 bg-warning/8'}`}>
      <div className="flex items-center gap-2 text-[13px] font-semibold" style={{ color: ok ? '#4ade80' : '#fbbf24' }}>
        {ok ? <CircleCheck size={16} aria-hidden /> : <TriangleAlert size={16} aria-hidden />}
        Reviewer: {ok ? 'Approved' : 'Changes requested'} · quality {r.score}/10
      </div>
      {final.task_type !== 'CODE_REVIEW' && (
        <p className="mt-0.5 font-mono text-[11px] text-muted">
          Quality per round: {scores.join(' → ') || r.score} · bar {threshold}
        </p>
      )}
      <p className="mt-1 text-[12px] text-ink/85">{r.summary}</p>
      {r.rubric && (
        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
          {(Object.keys(RUBRIC_LABEL) as (keyof typeof RUBRIC_LABEL)[]).map((k) => (
            <div key={k} className="text-[11px]">
              <div className="flex justify-between text-muted">
                <span>{RUBRIC_LABEL[k]}</span>
                <span className="font-mono text-ink">{r.rubric![k]}</span>
              </div>
              <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-surface-2">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${r.rubric![k] * 10}%`, background: r.rubric![k] >= 8 ? '#22c55e' : r.rubric![k] >= 6 ? '#f59e0b' : '#ef4444' }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
      {r.required_changes.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-[12px] text-ink/85">
          {r.required_changes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
      {r.risks.length > 0 && <p className="mt-2 text-[11.5px] text-muted">Risks: {r.risks.join(' · ')}</p>}
    </div>
  )
}

function TestBadge({ final }: { final: FinalResult }) {
  const t = final.test_results
  if (!t) return null
  return (
    <div className="flex items-start gap-2 rounded-lg border border-line bg-surface-2/30 px-2.5 py-2 text-[11.5px] text-muted">
      <Info size={13} className="mt-0.5 shrink-0 text-secondary" aria-hidden />
      <span>
        <span className="text-ink">{t.total_cases} tests generated — not executed.</span> The Tester traced the code case by case; the verdict
        is computed from those traces ({t.passed ? 'all cases expected to pass' : `${t.failing_cases.length} expected to fail: ${t.failing_cases.join(', ')}`}).
        No code is run on the server.
      </span>
    </div>
  )
}

export function ResultsPanel({ run }: { run: RunState }) {
  const final = run.final
  if (!final) {
    if (run.phase === 'failed' || run.phase === 'cancelled')
      return (
        <div className="grid h-full place-items-center p-6 text-center text-[12.5px]">
          <div>
            <CircleX className="mx-auto mb-2 text-danger" aria-hidden />
            <p className="text-ink">{run.phase === 'cancelled' ? 'Workflow cancelled.' : 'Workflow failed.'}</p>
            {run.error && <p className="mt-1 text-muted">{run.error}</p>}
          </div>
        </div>
      )
    return (
      <div className="grid h-full place-items-center p-6 text-center text-[12.5px] text-muted">
        {run.phase === 'running' ? 'Agents are working… results appear when the orchestrator closes the workflow.' : 'Results appear here when the workflow completes.'}
      </div>
    )
  }

  const statusOk = final.status === 'completed'
  const testerOut = run.agents.tester.output as {
    cases?: { name: string; category: string; description: string }[]
    traces?: CaseTrace[]
  } | null
  const failingTraces = (testerOut?.traces ?? []).filter((tr) => !tr.passes)

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-3">
      <div className={`fade-up rounded-xl border p-3 ${statusOk ? 'border-success/40' : 'border-warning/40'}`}>
        <div className="flex items-center gap-2 text-[13.5px] font-semibold" style={{ color: statusOk ? '#4ade80' : '#fbbf24' }}>
          {statusOk ? <CircleCheck size={16} aria-hidden /> : <TriangleAlert size={16} aria-hidden />}
          {statusOk ? 'Workflow completed' : final.status === 'failed' ? 'Workflow failed' : 'Stopped: correction limit reached'}
        </div>
        <p className="mt-1 text-[12px] text-muted">{final.reason}</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat icon={Users} label="Agents used" value={final.agents_used.map(agentLabel).join(', ')} />
        <Stat icon={FlaskConical} label="Steps executed" value={`${final.steps} agent runs`} />
        <Stat icon={Repeat} label="Corrections" value={`${final.iterations} / ${run.maxIterations}`} />
        <Stat
          icon={Coins}
          label={run.simulated ? 'LLM cost (simulated)' : run.cached ? 'LLM cost (cached)' : 'LLM cost'}
          value={
            run.simulated
              ? `$0 · ${final.usage.calls} calls`
              : run.cached
                ? `$0 now · first run $${final.usage.cost_usd.toFixed(3)}`
                : `$${final.usage.cost_usd.toFixed(4)} · ${final.usage.calls} calls`
          }
        />
      </div>
      {final.skipped_agents.length > 0 && (
        <p className="-mt-2 text-[11.5px] text-muted">Skipped by the orchestrator: {final.skipped_agents.map(agentLabel).join(', ')}.</p>
      )}

      <Verdict final={final} scores={run.qualityScores} threshold={run.qualityThreshold} />

      {final.task_type === 'BUG_FIX' && final.final_code && (
        <Section title="Corrected code (diff)">
          <CodeDiff original={final.original_code} modified={final.final_code} height={300} />
        </Section>
      )}

      {final.task_type === 'CODE_REVIEW' && final.analysis && (
        <Section title="Quality review (Analyzer)">
          <Issues issues={final.analysis.issues} />
        </Section>
      )}
      {final.task_type === 'CODE_REVIEW' && final.test_results && (
        <Section title="Testability review (Tester)">
          <ul className="list-disc pl-5 text-[12px] text-ink/85">
            {final.test_results.issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </Section>
      )}

      {final.test_code && (
        <Section title={final.task_type === 'TEST_GEN' ? 'Generated test suite' : 'Generated tests'}>
          <TestBadge final={final} />
          {testerOut?.cases && (
            <div className="flex flex-wrap gap-1">
              {testerOut.cases.map((c) => (
                <span key={c.name} title={c.description} className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-muted">
                  <span
                    style={{
                      color: c.category === 'error' ? '#f87171' : c.category === 'edge' ? '#fbbf24' : c.category === 'adversarial' ? '#c084fc' : '#4ade80',
                    }}
                  >
                    ●
                  </span> {c.name}
                </span>
              ))}
            </div>
          )}
          {failingTraces.length > 0 && (
            <ul className="flex flex-col gap-1.5">
              {failingTraces.map((tr) => (
                <li key={tr.case} className="rounded-lg border border-danger/30 bg-danger/5 px-2.5 py-2 text-[11.5px]">
                  <div className="font-mono text-danger">{tr.case}</div>
                  <p className="mt-0.5 text-ink/80">{tr.trace}</p>
                  <p className="mt-0.5 text-muted">
                    expected {tr.expected} · predicted {tr.predicted}
                  </p>
                </li>
              ))}
            </ul>
          )}
          <CodeView code={final.test_code} height={final.task_type === 'TEST_GEN' ? 360 : 260} />
        </Section>
      )}

      {final.task_type !== 'CODE_REVIEW' && final.analysis && (
        <Section title="Analysis">
          <p className="text-[12px] text-ink/85">{final.analysis.summary}</p>
          <Issues issues={final.analysis.issues} />
        </Section>
      )}
    </div>
  )
}
