"""Unit tests of the orchestrator policy (agent selection, routing, limits)."""

import pytest

from app.orchestration import router


def state(task_type, stage_index, outcomes, **extra):
    s = {
        "task_type": task_type,
        "stages": router.PIPELINES[task_type],
        "stage_index": stage_index,
        "dispatch_id": 5,
        "completed_steps": [{"agent": a, "dispatch_id": 5, "outcome": o, "duration_ms": 1, "iteration": 0}
                            for a, o in outcomes.items()],
        "iteration_count": 0,
    }
    s.update(extra)
    return s


@pytest.mark.parametrize("task_type, selected, skipped", [
    ("BUG_FIX", ["analyzer", "developer", "tester", "reviewer"], []),
    ("TEST_GEN", ["analyzer", "tester", "reviewer"], ["developer"]),
    ("CODE_REVIEW", ["analyzer", "tester", "reviewer"], ["developer"]),
])
def test_agent_selection(task_type, selected, skipped):
    plan = router.build_plan(task_type)
    assert plan["selected_agents"] == selected
    assert plan["skipped_agents"] == skipped


def test_code_review_plan_starts_with_parallel_stage():
    assert router.build_plan("CODE_REVIEW")["stages"][0] == ["analyzer", "tester"]


@pytest.mark.parametrize("request_text, expected", [
    ("Please write unit tests for this", "TEST_GEN"),
    ("Can you review this before production?", "CODE_REVIEW"),
    ("This crashes with an exception, fix it", "BUG_FIX"),
])
def test_heuristic_classifier(request_text, expected):
    assert router.classify_heuristic(request_text)[0] == expected


def test_advance_to_next_stage():
    d = router.decide(state("BUG_FIX", 0, {"analyzer": "success"}), 3)
    assert d.kind == "dispatch" and d.next_agents == ["developer"] and d.stage_index == 1


def test_failed_validation_routes_back_to_developer():
    s = state("BUG_FIX", 2, {"tester": "validation_failed"}, test_results={"passed": False, "failing_cases": ["t1"]})
    d = router.decide(s, 3)
    assert d.kind == "retry" and d.next_agents == ["developer"] and d.stage_index == 1
    assert d.iteration_increment


def test_passed_validation_goes_to_reviewer():
    d = router.decide(state("BUG_FIX", 2, {"tester": "success"}, test_results={"passed": True}), 3)
    assert d.next_agents == ["reviewer"]


def test_reviewer_rejection_routes_to_developer_for_bug_fix():
    s = state("BUG_FIX", 3, {"reviewer": "rejected"}, review_feedback={"approved": False, "required_changes": ["x"]})
    d = router.decide(s, 3)
    assert d.kind == "rework" and d.next_agents == ["developer"]


def test_reviewer_rejection_routes_to_tester_for_test_generation():
    s = state("TEST_GEN", 2, {"reviewer": "rejected"}, review_feedback={"approved": False, "required_changes": ["x"]})
    d = router.decide(s, 3)
    assert d.next_agents == ["tester"] and d.stage_index == 1


def test_code_review_rejection_is_the_deliverable():
    s = state("CODE_REVIEW", 1, {"reviewer": "rejected"}, review_feedback={"approved": False})
    d = router.decide(s, 3)
    assert d.kind == "complete" and d.final_status == "completed"


def test_approval_completes():
    d = router.decide(state("BUG_FIX", 3, {"reviewer": "approved"}, review_feedback={"approved": True, "score": 9}), 3)
    assert d.kind == "complete" and d.final_status == "completed"


def test_iteration_limit_stops_the_loop():
    s = state("BUG_FIX", 2, {"tester": "validation_failed"}, iteration_count=3, test_results={"passed": False})
    d = router.decide(s, 3)
    assert d.kind == "limit" and d.final_status == "max_iterations_reached" and d.next_agents == []


def test_parallel_stage_joins_into_reviewer():
    d = router.decide(state("CODE_REVIEW", 0, {"analyzer": "success", "tester": "success"}), 3)
    assert d.next_agents == ["reviewer"]


def test_agent_error_is_retried_once_then_aborts():
    s = state("BUG_FIX", 1, {"developer": "error"})
    first = router.decide(s, 3)
    assert first.kind == "retry_error" and first.next_agents == ["developer"]
    second = router.decide({**s, "error_retries": {"developer": 1}}, 3)
    assert second.kind == "abort" and second.final_status == "failed"


def test_only_failed_parallel_branch_is_retried():
    d = router.decide(state("CODE_REVIEW", 0, {"analyzer": "success", "tester": "error"}), 3)
    assert d.kind == "retry_error" and d.next_agents == ["tester"]


def test_approved_but_below_quality_bar_is_reworked():
    s = state("BUG_FIX", 3, {"reviewer": "below_threshold"}, quality_threshold=8.0,
              review_feedback={"approved": True, "score": 7.2, "required_changes": ["cover empty input"],
                               "rubric": {"correctness": 9, "edge_cases": 5, "robustness": 7, "readability": 8}})
    d = router.decide(s, 3)
    assert d.kind == "rework" and d.next_agents == ["developer"] and d.iteration_increment
    assert "below the bar" in d.reason and "edge cases 5" in d.reason


def test_below_bar_at_limit_delivers_best_version():
    s = state("TEST_GEN", 2, {"reviewer": "below_threshold"}, iteration_count=3,
              review_feedback={"approved": True, "score": 7.5, "rubric": {}})
    d = router.decide(s, 3)
    assert d.kind == "limit" and d.final_status == "completed"


def test_reviewer_outcome_uses_computed_score():
    from app.agents.reviewer import apply
    from app.schemas.agents import ReviewerOutput
    out = ReviewerOutput(summary="ok", approved=True, findings=[], required_changes=[], risks=[],
                         rubric={"correctness": 9, "edge_cases": 6, "robustness": 7, "readability": 8})
    assert out.score == 7.5
    assert apply(out, {"task_type": "BUG_FIX", "quality_threshold": 8.0})[1] == "below_threshold"
    assert apply(out, {"task_type": "BUG_FIX", "quality_threshold": 7.0})[1] == "approved"
    assert apply(out, {"task_type": "CODE_REVIEW", "quality_threshold": 8.0})[1] == "approved"


def test_weak_criterion_under_floor_is_reworked_even_if_average_meets_bar():
    from app.agents.reviewer import apply
    from app.schemas.agents import ReviewerOutput
    out = ReviewerOutput(summary="ok", approved=True, findings=[], required_changes=[], risks=[],
                         rubric={"correctness": 9, "edge_cases": 8, "robustness": 7, "readability": 8})
    assert out.score == 8.0
    st = {"task_type": "BUG_FIX", "quality_threshold": 8.0, "min_rubric_score": 8.0}
    assert apply(out, st)[1] == "below_threshold"
    assert apply(out, {**st, "min_rubric_score": 7.0})[1] == "approved"
    s = state("BUG_FIX", 3, {"reviewer": "below_threshold"}, quality_threshold=8.0, min_rubric_score=8.0,
              review_feedback=out.model_dump())
    d = router.decide(s, 3)
    assert d.kind == "rework" and "robustness 7" in d.reason and "floor" in d.reason


def test_limit_after_failed_validation_delivers_best_approved_version():
    best = {"score": 8.2, "iteration": 2, "test_code": "def test_a(): pass", "review": {"approved": True}}
    s = state("TEST_GEN", 1, {"tester": "validation_failed"}, iteration_count=3,
              test_results={"passed": False, "failing_cases": ["t1"]}, best_version=best)
    d = router.decide(s, 3)
    assert d.kind == "limit" and d.final_status == "completed" and d.use_best_version
    assert "8.2" in d.reason
    # Without any approved version, the limit still stops the workflow as before.
    s.pop("best_version")
    assert router.decide(s, 3).final_status == "max_iterations_reached"


def test_reviewer_snapshots_only_improving_approved_versions():
    from app.agents.reviewer import apply
    from app.schemas.agents import ReviewerOutput
    def out(r, ok=True):
        return ReviewerOutput(summary="s", approved=ok, findings=[], required_changes=[], risks=[],
                              rubric=dict(zip(["correctness", "edge_cases", "robustness", "readability"], r)))
    st = {"task_type": "TEST_GEN", "quality_threshold": 8.0, "min_rubric_score": 8.0, "test_code": "v1"}
    upd, _ = apply(out([9, 7, 8, 8]), st)
    assert upd["best_version"]["score"] == 8.0 and upd["best_version"]["test_code"] == "v1"
    st["best_version"] = upd["best_version"]
    assert "best_version" not in apply(out([8, 7, 8, 7]), {**st, "test_code": "v2"})[0]   # worse
    assert "best_version" not in apply(out([10, 10, 10, 10], ok=False), st)[0]           # not approved
