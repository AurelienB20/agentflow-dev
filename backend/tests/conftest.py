import copy
from dataclasses import replace

import pytest

from app import config as config_module
from app.orchestration.events import WorkflowRun
from app.scenarios import SCENARIOS
from app.services import runner
from app.services.limits import limiter
from app.services.llm import ScriptedProvider


@pytest.fixture
def settings():
    """Fast, deterministic settings for engine tests."""
    return replace(config_module.settings, llm_provider="mock", mock_delay_scale=0.0, max_iterations=3,
                   workflow_timeout_s=20, max_llm_calls_per_workflow=20, max_cost_per_workflow_usd=1.0)


@pytest.fixture
def script():
    def _get(scenario_id: str):
        return copy.deepcopy(SCENARIOS[scenario_id]["script"])
    return _get


@pytest.fixture
def run_scenario(settings):
    async def _run(scenario_id: str, *, provider=None, settings_override=None, task_hint=None):
        sc = SCENARIOS[scenario_id]
        provider = provider or ScriptedProvider(copy.deepcopy(sc["script"]))
        wf = WorkflowRun(mode="test", provider=provider.name, model=provider.model, simulated=True)
        result = await runner.execute(wf, provider, settings_override or settings, code=sc["code"],
                                      request=sc["request"], task_hint=task_hint or sc["task_type"],
                                      scenario_id=scenario_id)
        return wf, result
    return _run


@pytest.fixture(autouse=True)
def _reset_limits():
    limiter.reset()
    yield
    limiter.reset()


def events_of(run, type_):
    return [e for e in run.events if e["type"] == type_]
