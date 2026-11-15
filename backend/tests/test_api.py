"""HTTP API tests (no API key needed: the simulated provider is used)."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from app import config as config_module
from app.main import app
from app.scenarios import SCENARIOS


@pytest.fixture
def client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def live_mock(monkeypatch):
    s = replace(config_module.settings, llm_provider="mock", llm_model="scripted-demo-model", mock_delay_scale=0.0)
    monkeypatch.setattr(config_module, "settings", s)
    return s


@pytest.fixture
def live_off(monkeypatch):
    monkeypatch.setattr(config_module, "settings", replace(config_module.settings, llm_provider="none"))


def body(scenario_id="fix-bug"):
    sc = SCENARIOS[scenario_id]
    return {"scenario_id": scenario_id, "task_type": sc["task_type"], "code": sc["code"], "request": sc["request"]}


async def test_health(client, live_off):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["live_mode"]["available"] is False


async def test_scenarios_and_agents(client):
    scenarios = (await client.get("/api/scenarios")).json()
    assert [s["id"] for s in scenarios] == ["fix-bug", "generate-tests", "code-review"]
    assert all("script" not in s for s in scenarios)
    agents = (await client.get("/api/agents")).json()
    assert [a["id"] for a in agents] == ["orchestrator", "analyzer", "developer", "tester", "reviewer"]


async def test_live_mode_unavailable_returns_503(client, live_off):
    r = await client.post("/api/workflows", json=body())
    assert r.status_code == 503


async def test_workflow_lifecycle_over_sse(client, live_mock):
    r = await client.post("/api/workflows", json=body("code-review"))
    assert r.status_code == 202
    data = r.json()
    assert data["simulated"] is True
    events = []
    async with client.stream("GET", data["events_url"]) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    types = [e["type"] for e in events]
    assert types[0] == "workflow_started" and types[-1] == "workflow_completed"
    assert "parallel_joined" in types
    snap = (await client.get(f"/api/workflows/{data['workflow_id']}")).json()
    assert snap["status"] == "completed" and snap["final_result"]["task_type"] == "CODE_REVIEW"


async def test_sse_resume_with_last_event_id(client, live_mock):
    wid = (await client.post("/api/workflows", json=body("generate-tests"))).json()["workflow_id"]
    for _ in range(100):
        if (await client.get(f"/api/workflows/{wid}")).json()["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    first = []
    async with client.stream("GET", f"/api/workflows/{wid}/events", headers={"Last-Event-ID": "10"}) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                first.append(json.loads(line[5:].strip()))
    assert first[0]["seq"] == 11


async def test_cancel(client, monkeypatch):
    s = replace(config_module.settings, llm_provider="mock", mock_delay_scale=1.0)
    monkeypatch.setattr(config_module, "settings", s)
    wid = (await client.post("/api/workflows", json=body())).json()["workflow_id"]
    await asyncio.sleep(0.1)
    r = await client.post(f"/api/workflows/{wid}/cancel")
    assert r.json()["cancelled"] is True
    for _ in range(50):
        if (await client.get(f"/api/workflows/{wid}")).json()["status"] == "cancelled":
            break
        await asyncio.sleep(0.02)
    assert (await client.get(f"/api/workflows/{wid}")).json()["status"] == "cancelled"


async def test_input_size_limit(client, live_mock):
    b = body()
    b["code"] = "x = 1\n" * 2000
    r = await client.post("/api/workflows", json=b)
    assert r.status_code == 413


async def test_rate_limit(client, monkeypatch):
    s = replace(config_module.settings, llm_provider="mock", mock_delay_scale=0.0, rate_limit_per_ip_per_hour=2,
                max_concurrent_workflows=10)
    monkeypatch.setattr(config_module, "settings", s)
    codes = [(await client.post("/api/workflows", json=body())).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


async def test_session_quota(client, monkeypatch):
    s = replace(config_module.settings, llm_provider="mock", mock_delay_scale=0.0, quota_per_session=1,
                rate_limit_per_ip_per_hour=50, max_concurrent_workflows=10)
    monkeypatch.setattr(config_module, "settings", s)
    h = {"X-Session-Id": "abc"}
    assert (await client.post("/api/workflows", json=body(), headers=h)).status_code == 202
    assert (await client.post("/api/workflows", json=body(), headers=h)).status_code == 429


async def test_unknown_workflow_404(client):
    assert (await client.get("/api/workflows/wf_nope")).status_code == 404


@pytest.fixture
def cached_mock(monkeypatch, tmp_path):
    s = replace(config_module.settings, llm_provider="mock", llm_model="scripted-demo-model", mock_delay_scale=0.0,
                result_cache=True, result_cache_include_simulated=True,
                result_cache_path=str(tmp_path / "cache.sqlite"), quota_per_session=1,
                rate_limit_per_ip_per_hour=50, max_concurrent_workflows=10)
    monkeypatch.setattr(config_module, "settings", s)
    return s


async def wait_done(client, wid):
    for _ in range(200):
        status = (await client.get(f"/api/workflows/{wid}")).json()["status"]
        if status in ("completed", "failed", "cancelled"):
            return status
        await asyncio.sleep(0.02)
    raise AssertionError("workflow did not finish")


async def test_identical_request_is_served_from_cache(client, cached_mock):
    h = {"X-Session-Id": "visitor"}
    first = (await client.post("/api/workflows", json=body("code-review"), headers=h)).json()
    assert first["cached"] is False
    assert await wait_done(client, first["workflow_id"]) == "completed"
    # quota is 1 per session: a second *paid* run would be refused, a cache hit is free
    second = await client.post("/api/workflows", json=body("code-review"), headers=h)
    assert second.status_code == 202 and second.json()["cached"] is True
    wid = second.json()["workflow_id"]
    assert await wait_done(client, wid) == "completed"
    events = []
    async with client.stream("GET", f"/api/workflows/{wid}/events") as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    assert events[0]["data"]["cached"] is True
    assert events[-1]["type"] == "workflow_completed"
    assert (await client.get("/api/health")).json()["result_cache"]["hits"] == 1


async def test_different_code_is_not_cached(client, cached_mock):
    first = (await client.post("/api/workflows", json=body("code-review"))).json()
    await wait_done(client, first["workflow_id"])
    b = body("code-review")
    b["code"] += "\n# edited\n"
    second = (await client.post("/api/workflows", json=b)).json()
    assert second["cached"] is False


async def test_daily_cap(client, monkeypatch):
    s = replace(config_module.settings, llm_provider="mock", mock_delay_scale=0.0, max_live_workflows_per_day=1,
                rate_limit_per_ip_per_hour=50, quota_per_session=50, max_concurrent_workflows=10)
    monkeypatch.setattr(config_module, "settings", s)
    assert (await client.post("/api/workflows", json=body())).status_code == 202
    r = await client.post("/api/workflows", json=body())
    assert r.status_code == 429 and "daily" in r.json()["detail"]
