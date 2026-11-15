import { Workflow } from 'lucide-react'
import { useCallback, useState } from 'react'
import { ActivityPanel } from '../components/ActivityPanel'
import { AgentDetails } from '../components/AgentDetails'
import { liveAvailability, MissionPanel } from '../components/MissionPanel'
import { WorkflowGraph } from '../components/WorkflowGraph'
import { SCENARIOS } from '../data/scenarios'
import { useBackendStatus, useWorkflow } from '../hooks/useWorkflow'
import type { AgentId, Mode, Scenario } from '../types'

const STEPS = [
  { title: 'Pick a mission', text: 'Fix a bug, write tests or review code.' },
  { title: 'Press Launch Agents', text: 'An Orchestrator splits the work between 4 AI agents.' },
  { title: 'Watch them work', text: 'Each step is narrated. A failed test sends the code back for a fix.' },
]

export function Home() {
  const backend = useBackendStatus()
  const { run, launchDemo, launchLive, cancel, reset, speed, setSpeed } = useWorkflow()
  const [scenario, setScenario] = useState<Scenario>(SCENARIOS[0])
  const [code, setCode] = useState(SCENARIOS[0].code)
  const [request, setRequest] = useState(SCENARIOS[0].request)
  const [mode, setMode] = useState<Mode>('demo')
  const [selectedAgent, setSelectedAgent] = useState<AgentId | null>(null)
  const live = liveAvailability(backend)

  const selectScenario = (s: Scenario) => {
    setScenario(s)
    setCode(s.code)
    setRequest(s.request)
    reset()
  }

  const launch = () => {
    if (mode === 'live' && live.ok) void launchLive(scenario, code, request)
    else launchDemo(scenario)
  }

  const closeDetails = useCallback(() => setSelectedAgent(null), [])

  return (
    <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 pb-6 sm:px-6">
      <header className="flex items-center gap-3 py-4">
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-primary/15 text-primary">
          <Workflow size={19} aria-hidden />
        </div>
        <div className="leading-tight">
          <div className="text-[15px] font-bold tracking-tight">AgentFlow Dev</div>
          <div className="hidden text-[11px] text-muted sm:block">Intelligent Multi-Agent Orchestration for Software Development</div>
        </div>
        <div className="ml-auto flex items-center gap-2 text-[11px]">
          <span
            className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-muted"
            title={live.detail}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${live.ok ? 'bg-success' : backend.state === 'checking' ? 'bg-warning' : 'bg-muted'}`} />
            {live.ok ? 'Live AI available' : 'Guided Demo'}
          </span>
        </div>
      </header>

      <div className="pt-2 pb-5 sm:pt-4">
        <h1 className="text-[26px] leading-tight font-bold tracking-tight sm:text-[34px]">
          See AI Agents{' '}
          <span className="bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">Collaborate in Real Time</span>
        </h1>
        <p className="mt-2 max-w-2xl text-[14px] text-muted sm:text-[15px]">
          A team of AI agents fixes, tests and reviews code like a small dev team, and you watch every hand-off.
        </p>
        <ol className="mt-4 grid max-w-4xl gap-2 sm:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex items-start gap-2.5 rounded-xl border border-line bg-surface/60 px-3 py-2.5">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary/20 text-[12px] font-bold text-primary">
                {i + 1}
              </span>
              <span className="text-[12.5px] leading-snug">
                <span className="font-semibold text-ink">{s.title}</span>
                <span className="block text-muted">{s.text}</span>
              </span>
            </li>
          ))}
        </ol>
      </div>

      <main className="grid flex-1 grid-cols-1 xl:flex-none gap-4 lg:grid-cols-[360px_minmax(0,1fr)] xl:h-[860px] xl:grid-cols-[340px_minmax(0,1fr)_380px] xl:grid-rows-[minmax(0,1fr)]">
        <MissionPanel
          scenarios={SCENARIOS}
          selected={scenario}
          onSelect={selectScenario}
          code={code}
          setCode={setCode}
          request={request}
          setRequest={setRequest}
          mode={mode}
          setMode={setMode}
          backend={backend}
          phase={run.phase}
          onLaunch={launch}
          onReset={reset}
          onCancel={cancel}
          speed={speed}
          setSpeed={setSpeed}
        />
        <div className="flex min-h-0 min-w-0 flex-col gap-3">
          {run.mode && (
            <div
              className={`rounded-xl border px-3 py-2 text-[12px] ${
                run.mode === 'demo' ? 'border-secondary/30 bg-secondary/8 text-secondary' : 'border-success/30 bg-success/8 text-success'
              }`}
            >
              {run.mode === 'demo' ? (
                <>
                  <strong>Guided Demo — Pre-recorded Workflow.</strong>{' '}
                  <span className="text-ink/75">Replaying events recorded from the LangGraph engine with scripted agent outputs.</span>
                </>
              ) : (
                run.cached ? (
                  <>
                    <strong>Cached live result · {run.cached.model}.</strong>{' '}
                    <span className="text-ink/75">
                      Replay of a real run from {new Date(run.cached.at * 1000).toLocaleDateString()} for this exact request: no LLM
                      call, no cost. Edit the code or the request to run the agents again.
                    </span>
                  </>
                ) : (
                  <>
                    <strong>{run.simulated ? 'Live engine · simulated model' : `Live AI · ${run.model ?? ''}`}.</strong>{' '}
                    <span className="text-ink/75">Events are streamed from the backend as they happen{run.workflowId ? ` (${run.workflowId})` : ''}.</span>
                  </>
                )
              )}
            </div>
          )}
          <div className="h-[600px] sm:h-[520px] lg:h-auto lg:min-h-[520px] lg:flex-1 xl:min-h-0">
            <WorkflowGraph run={run} selected={selectedAgent} onSelect={setSelectedAgent} />
          </div>
        </div>
        <div className="h-[600px] min-h-0 lg:col-span-2 xl:col-span-1 xl:h-auto">
          <ActivityPanel run={run} />
        </div>
      </main>

      <footer className="mt-6 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
        <span>React Flow · LangGraph · FastAPI · Server-Sent Events</span>
        <span>No code is executed on the server. Generated tests are labelled as not executed.</span>
      </footer>

      {selectedAgent && <AgentDetails id={selectedAgent} run={run} onClose={closeDetails} />}
    </div>
  )
}
