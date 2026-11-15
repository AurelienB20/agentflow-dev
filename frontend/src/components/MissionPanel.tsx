import { Bug, FlaskConical, Lock, Play, RotateCcw, ShieldCheck, Sparkles, Square, Wifi, WifiOff } from 'lucide-react'
import type { BackendStatus } from '../hooks/useWorkflow'
import type { Mode, Phase, Scenario } from '../types'
import { CodeEditor } from './CodeEditor'

const SCENARIO_ICON = { 'fix-bug': Bug, 'generate-tests': FlaskConical, 'code-review': ShieldCheck } as const

interface Props {
  scenarios: Scenario[]
  selected: Scenario
  onSelect: (s: Scenario) => void
  code: string
  setCode: (v: string) => void
  request: string
  setRequest: (v: string) => void
  mode: Mode
  setMode: (m: Mode) => void
  backend: BackendStatus
  phase: Phase
  onLaunch: () => void
  onReset: () => void
  onCancel: () => void
  speed: number
  setSpeed: (v: number) => void
}

export function liveAvailability(backend: BackendStatus): { ok: boolean; label: string; detail: string } {
  if (backend.state === 'checking') return { ok: false, label: 'Checking backend…', detail: 'Contacting the API.' }
  if (backend.state === 'offline')
    return { ok: false, label: 'Backend offline', detail: 'The live API is unreachable. The Guided Demo works fully offline.' }
  const lm = backend.health.live_mode
  if (!lm.available)
    return { ok: false, label: 'Live AI not configured', detail: 'No LLM provider is configured on this server. Use the Guided Demo.' }
  if (lm.simulated)
    return { ok: true, label: 'Live engine · simulated model', detail: 'Real LangGraph run on the server with a scripted model (no LLM key).' }
  return { ok: true, label: `Live AI · ${lm.model}`, detail: `Real agents calling ${lm.provider} (${lm.model}) on the server.` }
}

export function MissionPanel(p: Props) {
  const running = p.phase === 'running'
  const live = liveAvailability(p.backend)
  const demo = p.mode === 'demo'
  const limits = p.backend.state === 'online' ? p.backend.health.limits : null

  return (
    <section className="panel flex flex-col gap-4 overflow-y-auto p-4" aria-label="Mission control">
      <div className="flex items-center gap-2">
        <Sparkles size={16} className="text-primary" aria-hidden />
        <h2 className="text-sm font-semibold">Mission Control</h2>
      </div>

      <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Scenario">
        {p.scenarios.map((s) => {
          const Icon = SCENARIO_ICON[s.id as keyof typeof SCENARIO_ICON] ?? Bug
          const active = s.id === p.selected.id
          return (
            <button
              key={s.id}
              role="radio"
              aria-checked={active}
              disabled={running}
              onClick={() => p.onSelect(s)}
              className={`flex flex-col items-start gap-1.5 rounded-xl border p-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
                active ? 'border-primary bg-primary/12 shadow-[0_0_0_1px_var(--primary)]' : 'border-line bg-surface-2/50 hover:border-primary/50'
              }`}
            >
              <Icon size={16} className={active ? 'text-primary' : 'text-muted'} aria-hidden />
              <span className="text-[12px] leading-tight font-semibold">{s.short_title}</span>
            </button>
          )
        })}
      </div>

      <div>
        <h3 className="text-[15px] font-semibold">{p.selected.title}</h3>
        <p className="mt-1 text-[12.5px] leading-relaxed text-muted">{p.selected.description}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {p.selected.highlights.map((h) => (
            <span key={h} className="rounded-full bg-surface-2 px-2 py-0.5 text-[10.5px] text-secondary">
              {h}
            </span>
          ))}
        </div>
      </div>

      <div role="radiogroup" aria-label="Execution mode" className="grid grid-cols-2 gap-1 rounded-xl border border-line bg-bg/60 p-1">
        {(['demo', 'live'] as const).map((m) => {
          const disabled = running || (m === 'live' && !live.ok)
          const active = p.mode === m
          return (
            <button
              key={m}
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => p.setMode(m)}
              title={m === 'live' ? live.detail : 'Replays a workflow recorded from the real engine'}
              className={`rounded-lg px-2 py-1.5 text-[12px] font-medium transition disabled:cursor-not-allowed ${
                active ? 'bg-primary text-white' : 'text-muted hover:text-ink disabled:opacity-50'
              }`}
            >
              {m === 'demo' ? 'Guided Demo' : 'Live AI'}
            </button>
          )
        })}
      </div>
      <p className="-mt-2 flex items-start gap-1.5 text-[11px] leading-snug text-muted">
        {demo ? (
          <>
            <Lock size={12} className="mt-0.5 shrink-0" aria-hidden />
            <span>
              <span className="text-ink">Guided Demo — Pre-recorded Workflow.</span> Replays events recorded from the real LangGraph engine
              (scripted agent outputs). Switch to Live AI to run your own code.
            </span>
          </>
        ) : (
          <>
            <Wifi size={12} className="mt-0.5 shrink-0 text-success" aria-hidden />
            <span>
              <span className="text-ink">{live.label}.</span> {live.detail}
              {limits && ` Max ${limits.max_code_chars} chars, ${limits.max_iterations} corrections, ${limits.quota_per_session} runs per visitor.`}
              {' '}Requests already answered are replayed from cache for free.
            </span>
          </>
        )}
      </p>
      {demo && !live.ok && p.backend.state !== 'checking' && (
        <p className="-mt-2 flex items-center gap-1.5 text-[11px] text-muted/80">
          <WifiOff size={12} aria-hidden /> {live.label}
        </p>
      )}

      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] font-medium tracking-wide text-muted uppercase" htmlFor="request">
          Request
        </label>
        <textarea
          id="request"
          value={demo ? p.selected.request : p.request}
          onChange={(e) => p.setRequest(e.target.value)}
          readOnly={demo || running}
          rows={3}
          maxLength={1000}
          className="resize-none rounded-xl border border-line bg-[#0e1428] px-3 py-2 text-[12.5px] leading-relaxed text-ink outline-none focus:border-primary"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium tracking-wide text-muted uppercase">Code</span>
        <CodeEditor value={demo ? p.selected.code : p.code} onChange={p.setCode} readOnly={demo || running} height={250} />
      </div>

      <div className="flex items-center gap-2">
        {running ? (
          <button
            onClick={p.onCancel}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-danger/60 bg-danger/10 px-4 py-2.5 text-sm font-semibold text-danger transition hover:bg-danger/20"
          >
            <Square size={15} aria-hidden /> {demo ? 'Stop replay' : 'Cancel workflow'}
          </button>
        ) : (
          <button
            onClick={p.onLaunch}
            disabled={!demo && !live.ok}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-[0_8px_30px_-8px_var(--primary)] transition hover:brightness-110 disabled:opacity-50"
          >
            <Play size={15} aria-hidden /> Launch Agents
          </button>
        )}
        <button
          onClick={p.onReset}
          disabled={running}
          className="flex items-center gap-1.5 rounded-xl border border-line px-3 py-2.5 text-sm text-muted transition hover:text-ink disabled:opacity-40"
          aria-label="Reset"
        >
          <RotateCcw size={15} aria-hidden /> Reset
        </button>
      </div>
      {demo && (
        <div className="-mt-1 flex items-center justify-end gap-1 text-[11px] text-muted">
          Replay speed
          {[1, 2, 4].map((v) => (
            <button
              key={v}
              onClick={() => p.setSpeed(v)}
              className={`rounded-md px-1.5 py-0.5 font-mono ${p.speed === v ? 'bg-surface-2 text-ink' : 'hover:text-ink'}`}
            >
              {v}×
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
