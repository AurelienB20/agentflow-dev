"""Executes a LangGraph workflow in the background and records its lifecycle."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from app.config import Settings
from app.orchestration.events import WorkflowRun
from app.orchestration.graph import WorkflowContext, compiled_graph
from app.services.llm import BudgetExceeded, LLMProvider

RECURSION_LIMIT = 60  # hard stop on graph steps, independent of MAX_ITERATIONS


def initial_state(run: WorkflowRun, *, code: str, request: str, task_hint: str = "auto",
                  quality_threshold: float = 8.0, min_rubric_score: float = 8.0) -> dict[str, Any]:
    return {
        "quality_threshold": quality_threshold,
        "min_rubric_score": min_rubric_score,
        "workflow_id": run.id,
        "task_hint": task_hint,
        "user_request": request,
        "original_code": code,
        "agent_outputs": {},
        "completed_steps": [],
        "error_retries": {},
        "errors": [],
        "iteration_count": 0,
        "generated_code": "",
        "test_code": "",
        "status": "pending",
    }


async def execute(run: WorkflowRun, provider: LLMProvider, settings: Settings, *, code: str, request: str,
                  task_hint: str = "auto", scenario_id: str | None = None,
                  on_success: Callable[[WorkflowRun], None] | None = None) -> dict[str, Any] | None:
    budget = provider.new_budget(settings)
    ctx = WorkflowContext(run=run, provider=provider, budget=budget, settings=settings)
    run.status = "running"
    run.emit("workflow_started", agent="orchestrator", mode=run.mode, provider=provider.name, model=provider.model,
             simulated=provider.simulated, scenario_id=scenario_id, request=request, task_hint=task_hint,
             limits={"max_iterations": settings.max_iterations, "timeout_s": settings.workflow_timeout_s,
                     "quality_threshold": settings.quality_threshold,
                     "min_rubric_score": settings.min_rubric_score,
                     "max_llm_calls": settings.max_llm_calls_per_workflow,
                     "max_cost_usd": settings.max_cost_per_workflow_usd})
    try:
        final_state = await asyncio.wait_for(
            compiled_graph.ainvoke(
                initial_state(run, code=code, request=request, task_hint=task_hint,
                              quality_threshold=settings.quality_threshold,
                              min_rubric_score=settings.min_rubric_score),
                config={"configurable": {"ctx": ctx}, "recursion_limit": RECURSION_LIMIT},
            ),
            timeout=settings.workflow_timeout_s,
        )
    except asyncio.CancelledError:
        run.emit("workflow_cancelled", agent="orchestrator", reason="Cancelled by the user")
        raise
    except TimeoutError:
        run.error = f"Workflow exceeded the {settings.workflow_timeout_s:.0f}s time limit"
        run.emit("workflow_failed", agent="orchestrator", error=run.error, usage=budget.snapshot())
        return None
    except BudgetExceeded as exc:
        run.error = str(exc)
        run.decision("Abort workflow", f"Budget guard triggered: {exc}", kind="abort")
        run.emit("workflow_failed", agent="orchestrator", error=run.error, usage=budget.snapshot())
        return None
    except Exception as exc:  # noqa: BLE001 - any engine failure must end the stream cleanly
        run.error = f"Internal error: {exc.__class__.__name__}"
        run.emit("workflow_failed", agent="orchestrator", error=run.error, usage=budget.snapshot())
        return None

    result = final_state.get("final_result") or {}
    run.final_result = result
    if final_state.get("status") == "failed":
        run.error = result.get("reason", "Workflow failed")
        run.emit("workflow_failed", agent="orchestrator", error=run.error, final_result=result,
                 usage=budget.snapshot())
    else:
        run.emit("workflow_completed", agent="orchestrator", final_result=result)
        if on_success is not None:
            try:
                on_success(run)
            except Exception:  # noqa: BLE001 - caching must never break a finished run
                pass
    return result


MAX_REPLAY_GAP_S = 2.5


async def replay(run: WorkflowRun, cached: dict[str, Any], speed: float = 1.0) -> None:
    """Re-emit a cached real run with its original pacing. No LLM call is made."""
    run.status = "running"
    previous_t = 0.0
    for event in cached["events"]:
        gap = min(MAX_REPLAY_GAP_S, max(0.0, event["t"] - previous_t))
        previous_t = event["t"]
        if gap and speed:
            await asyncio.sleep(gap / speed)
        data = dict(event["data"])
        if event["type"] == "workflow_started":
            data.update(cached=True, cached_from=event["workflow_id"], cached_model=cached["model"],
                        cached_at=cached["created"])
        if event["type"] == "workflow_completed":
            run.final_result = data.get("final_result")
        run.emit(event["type"], agent=event["agent"], **data)


def start_background(run: WorkflowRun, provider: LLMProvider, settings: Settings, **kwargs: Any) -> None:
    async def _runner() -> None:
        try:
            await execute(run, provider, settings, **kwargs)
        except asyncio.CancelledError:
            pass

    run.task = asyncio.create_task(_runner())


def start_replay(run: WorkflowRun, cached: dict[str, Any], speed: float = 1.0) -> None:
    async def _runner() -> None:
        try:
            await replay(run, cached, speed)
        except asyncio.CancelledError:
            run.emit("workflow_cancelled", agent="orchestrator", reason="Cancelled by the user")

    run.task = asyncio.create_task(_runner())
