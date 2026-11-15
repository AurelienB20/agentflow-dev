"""End-to-end tests of the LangGraph engine with the scripted (offline) model."""

import copy
from dataclasses import replace

from app.scenarios import SCENARIOS
from app.services.llm import ScriptedProvider
from tests.conftest import events_of


def agent_sequence(run):
    return [e["agent"] for e in events_of(run, "agent_completed") if e["agent"] != "orchestrator"]


async def test_bug_fix_runs_correction_loop(run_scenario):
    run, result = await run_scenario("fix-bug")
    assert run.status == "completed"
    assert agent_sequence(run) == ["analyzer", "developer", "tester", "developer", "tester", "reviewer"]
    assert result["iterations"] == 1
    assert "values = list(numbers)" in result["final_code"]
    assert result["test_results"]["executed"] is False  # never claims execution
    kinds = [e["data"]["kind"] for e in events_of(run, "decision")]
    assert "retry" in kinds
    retry = [e for e in events_of(run, "transition") if e["data"]["kind"] == "retry"]
    assert retry[0]["data"]["source"] == "tester" and retry[0]["data"]["target"] == "developer"


async def test_test_generation_skips_developer(run_scenario):
    run, result = await run_scenario("generate-tests")
    assert run.status == "completed"
    assert "developer" not in agent_sequence(run)
    assert result["skipped_agents"] == ["developer"]
    assert result["iterations"] == 1  # quality bar sent the tester back once
    reviews = [e["data"]["outcome"] for e in events_of(run, "agent_completed") if e["agent"] == "reviewer"]
    assert reviews == ["below_threshold", "approved"]
    assert "test_accents_are_dropped" in result["test_code"]


async def test_code_review_runs_in_parallel(run_scenario):
    provider = ScriptedProvider(copy.deepcopy(SCENARIOS["code-review"]["script"]), delay_scale=0.01)
    run, result = await run_scenario("code-review", provider=provider)
    assert run.status == "completed"
    starts = {e["agent"]: e["seq"] for e in events_of(run, "agent_started")}
    ends = {e["agent"]: e["seq"] for e in events_of(run, "agent_completed")}
    # both branches started before either finished => same super-step
    assert max(starts["analyzer"], starts["tester"]) < min(ends["analyzer"], ends["tester"])
    joined = events_of(run, "parallel_joined")
    assert joined and sorted(joined[0]["data"]["agents"]) == ["analyzer", "tester"]
    assert ends["reviewer"] > max(ends["analyzer"], ends["tester"])
    assert result["review"]["approved"] is False


async def test_parallel_branches_overlap_in_time(run_scenario, settings):
    sc = SCENARIOS["code-review"]
    provider = ScriptedProvider(copy.deepcopy(sc["script"]), delay_scale=0.05)
    run, _ = await run_scenario("code-review", provider=provider)
    durations = {e["agent"]: e["data"]["duration_ms"] for e in events_of(run, "agent_completed")
                 if e["agent"] != "orchestrator"}
    t = {e["agent"]: e["t"] for e in events_of(run, "agent_completed")}
    t_start = {e["agent"]: e["t"] for e in events_of(run, "agent_started")}
    # wall time of the parallel stage is less than the sum of both branches
    stage_wall = max(t["analyzer"], t["tester"]) - min(t_start["analyzer"], t_start["tester"])
    assert stage_wall * 1000 < durations["analyzer"] + durations["tester"]


async def test_iteration_limit(run_scenario, script):
    s = script("fix-bug")
    s["tester"] = [s["tester"][0]] * 10  # validation never passes
    s["tester_verify"] = [s["tester_verify"][0]] * 10
    run, result = await run_scenario("fix-bug", provider=ScriptedProvider(s))
    assert result["status"] == "max_iterations_reached"
    assert result["iterations"] == 3
    assert agent_sequence(run).count("developer") == 4  # first attempt + 3 corrections
    assert "reviewer" not in agent_sequence(run)


async def test_agent_error_is_retried(run_scenario, script):
    provider = ScriptedProvider(script("fix-bug"), failures={"developer": 1})
    run, result = await run_scenario("fix-bug", provider=provider)
    assert run.status == "completed"
    assert events_of(run, "agent_error")[0]["agent"] == "developer"
    assert any(e["data"]["kind"] == "retry_error" for e in events_of(run, "decision"))


async def test_repeated_error_fails_workflow(run_scenario, script):
    provider = ScriptedProvider(script("fix-bug"), failures={"analyzer": 2})
    run, result = await run_scenario("fix-bug", provider=provider)
    assert run.status == "failed"
    assert events_of(run, "workflow_failed")
    assert any(e["data"]["kind"] == "abort" for e in events_of(run, "decision"))


async def test_classifier_failure_falls_back(run_scenario, script):
    provider = ScriptedProvider(script("generate-tests"), failures={"classifier": 1})
    run, result = await run_scenario("generate-tests", provider=provider, task_hint="auto")
    assert run.status == "completed"
    assert events_of(run, "task_classified")[0]["data"]["task_type"] == "TEST_GEN"
    assert any(e["data"]["kind"] == "fallback" for e in events_of(run, "decision"))


async def test_budget_guard_stops_workflow(run_scenario, settings):
    tight = replace(settings, max_llm_calls_per_workflow=3)
    run, result = await run_scenario("fix-bug", settings_override=tight)
    assert run.status == "failed"
    assert "call limit" in run.error


async def test_event_and_message_contract(run_scenario):
    run, _ = await run_scenario("fix-bug")
    seqs = [e["seq"] for e in run.events]
    assert seqs == list(range(1, len(seqs) + 1))
    assert run.events[0]["type"] == "workflow_started"
    assert run.events[-1]["type"] == "workflow_completed"
    for e in run.events:
        assert {"seq", "workflow_id", "type", "agent", "t", "timestamp", "data"} <= e.keys()
        assert e["workflow_id"] == run.id
    messages = events_of(run, "message")
    assert messages
    for m in messages:
        assert {"sender", "receiver", "message_type", "content"} <= m["data"].keys()
    # the tester's failure report is forwarded to the developer
    assert any(m["data"]["sender"] == "tester" and m["data"]["receiver"] == "developer" for m in messages)


async def test_stream_replays_history_then_terminates(run_scenario):
    run, _ = await run_scenario("code-review")
    streamed = [e async for e in run.stream(after=3)]
    assert streamed[0]["seq"] == 4 and streamed[-1]["type"] == "workflow_completed"


async def test_known_scenario_skips_the_classifier_call(run_scenario, script):
    provider = ScriptedProvider(script("fix-bug"))
    run, _ = await run_scenario("fix-bug", provider=provider)
    assert "classifier" not in provider.calls
    assert events_of(run, "task_classified")[0]["data"]["confidence"] == 1.0


async def test_auto_mode_uses_the_llm_classifier(run_scenario, script):
    provider = ScriptedProvider(script("code-review"))
    run, _ = await run_scenario("code-review", provider=provider, task_hint="auto")
    assert provider.calls["classifier"] == 1
    assert events_of(run, "task_classified")[0]["data"]["task_type"] == "CODE_REVIEW"


async def test_static_checks_are_given_to_the_analyzer(run_scenario):
    run, _ = await run_scenario("code-review")
    tool = events_of(run, "tool_result")[0]["data"]["report"]
    rules = {f["rule"] for f in tool["findings"]}
    assert {"sql-injection", "bare-except", "resource-leak", "mutable-default"} <= rules
    assert any(m["data"]["sender"] == "tools" and m["data"]["receiver"] == "analyzer"
               for m in events_of(run, "message"))


async def test_invalid_developer_code_is_rejected_and_retried(run_scenario, script):
    s = script("fix-bug")
    broken = dict(s["developer"][0], code="def calculate_average(numbers:\n    return 0\n")
    s["developer"] = [broken] + s["developer"]
    run, result = await run_scenario("fix-bug", provider=ScriptedProvider(s))
    assert run.status == "completed"
    errors = events_of(run, "agent_error")
    assert errors[0]["agent"] == "developer" and "does not parse" in errors[0]["data"]["error"]
    # the second attempt received the automatic-check feedback in its inputs
    dev_starts = [e for e in events_of(run, "agent_started") if e["agent"] == "developer"]
    assert "validator_feedback" in dev_starts[1]["data"]["inputs"]


async def test_developer_cannot_drop_public_functions(run_scenario, script):
    s = script("fix-bug")
    renamed = dict(s["developer"][0], code="def mean(numbers):\n    return 0\n")
    s["developer"] = [renamed, renamed]
    run, result = await run_scenario("fix-bug", provider=ScriptedProvider(s))
    assert run.status == "failed"  # rejected twice -> abort
    assert "calculate_average" in events_of(run, "agent_error")[0]["data"]["error"]


async def test_tester_verdict_is_computed_from_traces(run_scenario, script):
    s = script("fix-bug")
    # the model's traces say one case fails: the verdict must follow, whatever the summary says
    v = s["tester_verify"][1]
    v["traces"][0]["passes"] = False
    s["tester_verify"] = [s["tester_verify"][0], v, s["tester_verify"][1]]
    run, _ = await run_scenario("fix-bug", provider=ScriptedProvider(s))
    outcomes = [e["data"]["outcome"] for e in events_of(run, "agent_completed") if e["agent"] == "tester"]
    assert outcomes[:2] == ["validation_failed", "validation_failed"]


async def test_tester_missing_trace_is_rejected(run_scenario, script):
    s = script("code-review")
    incomplete = dict(s["tester_verify"][0], traces=s["tester_verify"][0]["traces"][:2])
    s["tester_verify"] = [incomplete] + s["tester_verify"]
    run, _ = await run_scenario("code-review", provider=ScriptedProvider(s))
    assert run.status == "completed"
    assert "No trace for" in events_of(run, "agent_error")[0]["data"]["error"]
