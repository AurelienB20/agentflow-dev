"""REST + SSE endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app import config as config_module
from app.agents import AGENTS, ORCHESTRATOR_INFO
from app.orchestration.events import WorkflowRun, registry
from app.scenarios import SCENARIOS, public_scenarios
from app.schemas.api import AgentInfo, ScenarioInfo, WorkflowCreate, WorkflowCreated, WorkflowSnapshot
from app.services import runner
from app.services.cache import ResultCache, cache_key
from app.services.limits import limiter
from app.services.llm import LLMError, make_provider

router = APIRouter(prefix="/api")


def settings():
    return config_module.settings


_cache: ResultCache | None = None


def result_cache() -> ResultCache | None:
    """Lazily opened so tests and deployments can point RESULT_CACHE_PATH anywhere."""
    global _cache
    s = settings()
    if not s.result_cache:
        return None
    if _cache is None or _cache.path != s.result_cache_path:
        _cache = ResultCache(s.result_cache_path, s.result_cache_ttl_days)
    return _cache


@router.get("/health")
async def health() -> dict:
    s = settings()
    return {
        "status": "ok",
        "live_mode": {
            "available": s.live_available,
            "provider": s.llm_provider,
            "model": s.llm_model if s.live_available else None,
            "simulated": s.is_simulated,
        },
        "limits": {
            "max_iterations": s.max_iterations,
            "workflow_timeout_s": s.workflow_timeout_s,
            "max_code_chars": s.max_code_chars,
            "max_request_chars": s.max_request_chars,
            "rate_limit_per_ip_per_hour": s.rate_limit_per_ip_per_hour,
            "quota_per_session": s.quota_per_session,
            "max_cost_per_workflow_usd": s.max_cost_per_workflow_usd,
            "max_live_workflows_per_day": s.max_live_workflows_per_day,
        },
        "result_cache": (result_cache().stats() if result_cache() else None),
        "active_workflows": registry.active_count(),
    }


@router.get("/scenarios", response_model=list[ScenarioInfo])
async def list_scenarios() -> list[dict]:
    return public_scenarios()


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents() -> list[dict]:
    return [ORCHESTRATOR_INFO, *(spec.public() for spec in AGENTS.values())]


@router.post("/workflows", response_model=WorkflowCreated, status_code=202)
async def create_workflow(body: WorkflowCreate, request: Request) -> WorkflowCreated:
    s = settings()
    if not s.live_available:
        raise HTTPException(503, detail="Live AI mode is not configured on this server. Use the Guided Demo.")
    if len(body.code) > s.max_code_chars:
        raise HTTPException(413, detail=f"Code is limited to {s.max_code_chars} characters.")
    if len(body.request) > s.max_request_chars:
        raise HTTPException(413, detail=f"Request is limited to {s.max_request_chars} characters.")
    if body.scenario_id and body.scenario_id not in SCENARIOS:
        raise HTTPException(404, detail="Unknown scenario")
    scenario = SCENARIOS.get(body.scenario_id or "")
    try:
        provider = make_provider(s, scenario["script"] if scenario else None)
    except LLMError as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    # 1. Identical request already answered by a real run: replay it, free of charge.
    cache = result_cache()
    use_cache = cache is not None and (not provider.simulated or s.result_cache_include_simulated)
    key = cache_key(provider=provider.name, model=provider.model, task_hint=body.task_type,
                    code=body.code, request=body.request)
    cached = cache.get(key) if use_cache else None
    if cached is not None:
        run = WorkflowRun(mode="live", provider=provider.name, model=cached["model"], simulated=provider.simulated)
        run.cached = True
        registry.add(run)
        runner.start_replay(run, cached)
        return WorkflowCreated(workflow_id=run.id, status=run.status, events_url=f"/api/workflows/{run.id}/events",
                               provider=provider.name, model=cached["model"], simulated=provider.simulated,
                               cached=True)

    # 2. New request: guarded, paid run.
    if registry.active_count() >= s.max_concurrent_workflows:
        raise HTTPException(503, detail="All live agents are busy right now. Try again in a minute or use the Guided Demo.")
    limiter.check(request, s)

    def store(finished: WorkflowRun) -> None:
        if use_cache and finished.final_result and finished.final_result.get("status") == "completed":
            cache.put(key, provider.model, finished.events)

    run = WorkflowRun(mode="live", provider=provider.name, model=provider.model, simulated=provider.simulated)
    registry.add(run)
    runner.start_background(run, provider, s, code=body.code, request=body.request,
                            task_hint=body.task_type, scenario_id=body.scenario_id, on_success=store)
    return WorkflowCreated(workflow_id=run.id, status=run.status, events_url=f"/api/workflows/{run.id}/events",
                           provider=provider.name, model=provider.model, simulated=provider.simulated, cached=False)


def _get_run(workflow_id: str) -> WorkflowRun:
    run = registry.get(workflow_id)
    if run is None:
        raise HTTPException(404, detail="Workflow not found (runs are kept for one hour)")
    return run


@router.get("/workflows/{workflow_id}", response_model=WorkflowSnapshot)
async def get_workflow(workflow_id: str) -> dict:
    return _get_run(workflow_id).snapshot()


@router.get("/workflows/{workflow_id}/events")
async def workflow_events(workflow_id: str, request: Request) -> EventSourceResponse:
    run = _get_run(workflow_id)
    try:
        after = int(request.headers.get("last-event-id", "0"))
    except ValueError:
        after = 0

    async def generator():
        async for event in run.stream(after=after):
            if await request.is_disconnected():
                break
            yield {"id": str(event["seq"]), "event": "workflow", "data": json.dumps(event)}

    return EventSourceResponse(generator(), ping=15)


@router.post("/workflows/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str) -> dict:
    run = _get_run(workflow_id)
    if run.finished:
        return {"workflow_id": run.id, "status": run.status, "cancelled": False}
    if run.task is not None:
        run.task.cancel()
    return {"workflow_id": run.id, "status": "cancelling", "cancelled": True}
