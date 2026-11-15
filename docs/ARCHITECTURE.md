# Architecture

## 1. Design goals

1. Show **real** orchestration: routing that depends on results, true parallelism, loops, error handling.
2. Make every decision **observable**: nothing on screen is invented by the frontend; the graph, logs and
   messages are a projection of the backend's event log.
3. Keep the public demo **free and safe**: works with no key, with no backend, and never runs user code.

## 2. The LangGraph workflow (`backend/app/orchestration/graph.py`)

A *supervisor* (hub-and-spoke) topology:

```
START ─► orchestrator ─(conditional: state["next_agents"])─► analyzer | developer | tester | reviewer | END
              ▲                                                   │
              └──────────────── each agent ───────────────────────┘
```

* **One conditional edge** (`route_after_orchestrator`) returns the list written by the orchestrator. A
  list with two names fans out; LangGraph runs both nodes in the same super-step with asyncio.
* **Fan-in**: both agents have an edge back to `orchestrator`; LangGraph triggers it once, after the
  super-step barrier, with both results merged into the state.
* **The orchestrator node** runs on every hop:
  * first visit: `classify` (LLM structured output, keyword fallback) → `build_plan` → dispatch stage 0;
  * later visits: `router.decide(state)` → dispatch, retry, rework, complete, stop at limit, or abort.

### Plans (`router.PIPELINES`)

| Mission | Stages | Notes |
|---|---|---|
| `BUG_FIX` | Analyzer → Developer → Tester → Reviewer | Tester fail → Developer · Reviewer reject → Developer |
| `TEST_GEN` | Analyzer → Tester → Reviewer | Developer skipped · Reviewer reject → Tester |
| `CODE_REVIEW` | (Analyzer ‖ Tester) → Reviewer | parallel stage; the verdict is the deliverable |

### Decision rules (`router.decide`), in priority order

1. An agent errored → retry that agent once (only the failed branch of a parallel stage); then abort.
2. Tester validation failed (not in CODE_REVIEW) → back to Developer (BUG_FIX) or Tester (TEST_GEN),
   unless `iteration_count >= MAX_ITERATIONS` → stop with `max_iterations_reached`.
3. Reviewer approved **and** quality average ≥ `QUALITY_THRESHOLD` **and** every rubric criterion ≥
   `MIN_RUBRIC_SCORE` → complete. Otherwise rework (same limit); at the limit an approved-but-below-bar
   version is delivered as the best version. For CODE_REVIEW the verdict is the deliverable.
   The Reviewer's best approved version is snapshotted (`best_version`); if the limit is reached on a
   worse or failing round, that snapshot is delivered instead of the last attempt.
4. Otherwise → next stage of the plan, or complete.

These rules are pure functions with unit tests (`tests/test_router.py`).

## 3. Shared state (`state.py`)

`AgentState` is a `TypedDict`. Keys that may be written by two parallel nodes use reducers:

| Key | Reducer | Why |
|---|---|---|
| `agent_outputs` | dict merge | Analyzer and Tester each write their own key in the same step |
| `completed_steps` | list concat | both branches record their step |
| `errors` | list concat | |
| `error_retries` | dict merge | |

Single-writer keys (`generated_code`, `test_results`, `review_feedback`, `stage_index`, …) are plain values.
`dispatch_id` tags each dispatch so the orchestrator knows exactly which results belong to the stage that
just finished.

## 4. Agents (`app/agents/*.py`)

Each agent is an `AgentSpec`: system prompt, `build_prompt(state)` (which also returns the inputs shown in the
UI), an output schema (Pydantic, `schemas/agents.py`), `apply(output, state)` (state update + outcome) and
`summarize(output)` (used in messages). The outcome (`success`, `validation_failed`, `approved`,
`rejected`, `error`) is what the router branches on.

Agents never talk to each other directly. The orchestrator forwards work products at dispatch time and
publishes each hand-off as a structured message (`sender`, `receiver`, `message_type`, `content`,
`workflow_id`, `timestamp`). The messages shown are exactly the inputs the receiving agent's prompt
contains, so the communication log matches what each agent actually received.

### Helping small models (`services/static_checks.py`, `agents/tester.py`)

* **Facts before opinions**: at planning time the orchestrator runs a parser-based analysis (`ast` +
  pyflakes; the code is parsed, never executed). Findings are emitted as a `tool_result` event, sent to
  the Analyzer as a `static_facts` message and included in its prompt; the Reviewer also gets the same
  analysis of the corrected code.
* **Automatic output checks** (`AgentSpec.validate`): the Developer's code must parse and keep every public
  name of the original; the Tester's module must parse, define every listed case, and every case must have
  a trace. A rejected output is recorded as an agent error with the reason (`check_failed` message), stored
  in `agent_feedback`, and the agent is retried once with that message in its prompt.
* **Two-step Tester** (`AgentSpec.run`): `write` (TestSuite) then `verify` (one `CaseTrace` per case:
  trace, expected, predicted, passes), with a worked example in the prompt. `validation.passed` and
  `failing_cases` are computed from the traces, not stated by the model.

## 5. Events and streaming (`events.py`, `routes.py`)

`WorkflowRun` holds an append-only event log (`seq`, `type`, `agent`, `t`, `timestamp`, `data`). Types:
`workflow_started`, `task_classified`, `plan_created`, `decision`, `transition`, `agent_started`,
`agent_completed`, `agent_error`, `message`, `parallel_started`, `parallel_joined`, `iteration`, `usage`,
`workflow_completed | workflow_failed | workflow_cancelled`.

`GET /api/workflows/{id}/events` streams it as SSE (`id:` = `seq`). Subscribers first receive the history,
so `Last-Event-ID` reconnects lose nothing.

The frontend folds events with a single reducer (`frontend/src/hooks/workflowReducer.ts`). The Guided Demo
replays a recorded log through the **same reducer**, with the recorded timing.

## 6. LLM providers and budget (`services/llm.py`)

`AnthropicProvider` uses `client.messages.parse(output_format=<Pydantic model>)` (structured outputs) with
`output_config.effort` (default `low`). `OpenAIProvider` uses JSON mode plus schema validation.
`ScriptedProvider` replays scenario scripts (tests and demo recording) and is always reported as
`simulated`.

`BudgetTracker` enforces max calls and max USD per workflow from real token usage; exceeding it raises
`BudgetExceeded`, which aborts the workflow with an explicit decision event. The runner also enforces a
wall-clock timeout and cancellation.

## 7. Frontend

* **Mission Control**: scenario cards, mode switch, Monaco editor (bundled locally, Python only).
* **Workflow graph**: React Flow; nodes show status (Waiting, Running, Completed, Failed, Needs Review,
  Skipped), run count and time. Static dashed lines show orchestrator dispatch; coloured edges are the
  transitions the backend emitted (hand-off, parallel, join, correction loop). Horizontal layout on wide
  screens, vertical column on phones. Clicking a node opens its role, assigned task, inputs, run history and
  output.
* **Activity**: Agent Messages, Orchestrator Decisions (timestamped log with reasons), Results (diff of the
  corrected code, generated tests labelled *not executed*, review verdict, agents used, iterations, cost).

## 8. Why these choices

* **Supervisor over a fixed DAG**: the routing logic lives in one testable function, and every hop produces
  an explainable decision event.
* **Event log over polling state**: a recording of the log is enough to replay a demo, and it is the
  natural contract between engine and UI.
* **No code execution**: running untrusted code needs a real sandbox (gVisor/Firecracker). Out of MVP scope,
  and stated rather than faked.
