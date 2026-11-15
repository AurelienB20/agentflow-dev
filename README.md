# AgentFlow Dev

**Intelligent Multi-Agent Orchestration Platform for Software Development**

AgentFlow Dev shows, live, how an orchestrator and four specialised AI agents collaborate on real
development tasks. It focuses on what makes a system *multi-agent* rather than a chain of prompts:

| Capability | Where to see it |
|---|---|
| **Dynamic routing**: the orchestrator picks agents per mission | *Generate Tests* skips the Developer |
| **Parallel execution** with fan-out / fan-in | *Code Review* runs Analyzer ‖ Tester, then the Reviewer aggregates |
| **Conditional transitions and self-correction** | *Fix a Bug*: Tester rejects the first patch → back to the Developer |
| **Inter-agent communication** (structured messages) | *Agent Messages* tab |
| **Explained decisions** | *Orchestrator Decisions* tab: every routing choice with its reason |
| **Supervision and limits** | iteration cap (3), error retry, timeout, per-workflow LLM budget |

Open the page, pick a mission, press **Launch Agents**. No sign-up, no API key, works on a phone.

---

## Two modes, clearly labelled

| | Guided Demo | Live AI |
|---|---|---|
| Needs a backend / key | No (runs fully in the browser) | Yes, the key stays on the server |
| What runs | Replay of a workflow **recorded from the real LangGraph engine** with scripted agent outputs | LangGraph executes on the server; agents call the configured LLM |
| Events | Pre-recorded, labelled *Guided Demo — Pre-recorded Workflow* | Streamed live over SSE as the backend emits them |
| Code | The scenario's code (read-only) | Your own code (≤ 6,000 chars) |

If Live AI is not configured or the backend is down, the UI says so and the Guided Demo keeps working.

## Architecture in one picture

```
             ┌──────────── React + React Flow (Vercel) ────────────┐
             │ Mission Control │  Workflow graph  │ Messages/Decisions/Results │
             └───────┬─────────────────▲───────────────────────────┘
        POST /api/workflows      SSE /api/workflows/{id}/events
                     │                 │
             ┌───────▼─────────────────┴──── FastAPI (Render) ─────┐
             │  WorkflowRun (event log) ◄── every node emits events │
             │                                                      │
             │   LangGraph StateGraph (supervisor / hub-and-spoke)  │
             │                                                      │
             │   START → Orchestrator ──next_agents──► Analyzer      │
             │              ▲   (conditional edge)   ► Developer    │
             │              │                        ► Tester       │
             │              └────── every agent ◄─── ► Reviewer     │
             │                                                      │
             │   LLM provider: Anthropic | OpenAI | scripted (tests) │
             └──────────────────────────────────────────────────────┘
```

* The orchestrator classifies the request (LLM, with a keyword fallback), builds a staged plan, then after
  **every** stage decides the next step from the agents' structured results (`router.decide`).
* Returning two node names from the conditional edge runs both agents **in the same LangGraph
  super-step** (true asyncio concurrency); the orchestrator runs again only when both have finished: that
  is the join. Shared-state keys written concurrently use reducers (`Annotated[dict, merge]`, `operator.add`).
* **Deterministic tools do what a model should not guess.** Before any LLM call, a parser-based analyser
  (`ast` + pyflakes, never executes the code) finds syntax errors, SQL injection, bare `except`, resource
  leaks, unguarded division by `len()`, mutable defaults… and hands them to the Analyzer as verified facts.
  Developer code that does not parse or drops a public function, and test modules that do not parse or
  leave a case untraced, are rejected automatically and the agent retries with the error message.
* **Small steps for small models.** The Tester works in two calls (write the tests, then trace the code
  case by case in a fixed format with a worked example). Its pass/fail verdict is **computed from the
  traces by code**, so it cannot contradict its own reasoning. This is what makes a small, cheap model
  such as Claude Haiku viable.
* Tests are **generated, never executed**: no user code runs on the server, and the UI says so.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Deployment: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## Repository layout

```
backend/            FastAPI + LangGraph
  app/agents/       analyzer.py developer.py tester.py reviewer.py (prompts, I/O, outcome)
  app/orchestration graph.py (LangGraph) router.py (policy) state.py (typed state) events.py (event log)
  app/services/     llm.py (providers + budget) runner.py (timeout/cancel) limits.py (rate limits)
                    static_checks.py (parser-based facts) cache.py (result cache)
  app/api/routes.py REST + SSE
  app/scenarios.py  the 3 scenarios (+ scripted outputs for tests and demo recording)
  scripts/record_demos.py   re-records the Guided Demo from the engine
  tests/            57 pytest tests (no API key needed)
frontend/           React 19 + TypeScript + Vite + Tailwind 4 + React Flow + Monaco
  src/hooks/workflowReducer.ts  one reducer folds events into UI state (demo and live share it)
  src/components/   WorkflowGraph, AgentNode, MissionPanel, ActivityPanel, ResultsPanel, AgentDetails
demo/scenarios/     recorded workflows (JSON event streams)
docs/               architecture and deployment notes
```

## Run locally

Requirements: Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node.js 22.12+ (24 recommended).

```bash
# backend (simulated model: no key needed)
cd backend
uv sync
LLM_PROVIDER=mock uv run uvicorn app.main:app --port 8000

# frontend (proxies /api to :8000)
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Use a real model: set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` (see `.env.example`).
The default model is `claude-sonnet-5-5` (best quality/cost in our comparison: ~$0.05 per workflow); any model id can be set with `LLM_MODEL`.

Or the whole stack with Docker: `cp .env.example .env && docker compose up --build` → http://localhost:8080

## Tests

```bash
cd backend && uv run pytest        # 57 tests: routing, parallelism, loops, limits, errors, checks, cache, API, SSE
cd frontend && npm test            # 5 tests: recorded workflows replayed through the UI reducer
```

All tests use a scripted model, so they need no API key and no network.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/health` | status, live mode availability, limits |
| GET | `/api/scenarios` | the three scenarios |
| GET | `/api/agents` | orchestrator + agents, roles and objectives |
| POST | `/api/workflows` | start a live workflow → `{workflow_id, events_url}` |
| GET | `/api/workflows/{id}` | snapshot (status, final result) |
| GET | `/api/workflows/{id}/events` | Server-Sent Events, resumable with `Last-Event-ID` |
| POST | `/api/workflows/{id}/cancel` | cancel a running workflow |

Interactive docs at `/docs` (FastAPI).

## Safety and cost controls (public demo)

**Cost reduction**
* **Result cache**: an identical request (same model, code and request) replays the first real run from a
  SQLite cache: no LLM call, no cost, no quota used. The UI labels it *Cached live result*.
* **No classification call** when the mission type is known (unchanged scenario request).
* **Concise outputs**: agents are instructed to keep summaries short, at most 5 findings and 8 test cases.
* **Model choice** via `LLM_MODEL`: `claude-haiku-5-5` costs about 40× less than `claude-opus-5-5`.

**Guard rails**: per-IP rate limit (5/h), per-session quota (2), global daily cap on paid runs (50),
max concurrent workflows, 64 KB body limit, input length limits, workflow timeout, max 3 correction loops,
max LLM calls and **max USD cost per workflow** (computed from token usage), one automatic retry per failed
agent, graph recursion limit. User code is never executed. Prompts tell agents to treat the code and request
as untrusted data. Set a monthly spend limit in the Anthropic Console as a second safety net.

## Known limitations

* In-memory run store and rate limiter: fine for one instance, not shared across replicas.
* The Tester does not execute tests (no sandbox in the MVP); its verdict is a static model judgement.
* The Guided Demo recordings use scripted agent outputs. Run `scripts/record_demos.py --live` with a key
  to record real model outputs instead (the UI still labels them as pre-recorded).
* With `LLM_PROVIDER=mock`, Live mode only knows the three built-in scenarios.
