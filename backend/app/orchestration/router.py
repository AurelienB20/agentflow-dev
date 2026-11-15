"""Orchestrator policy: planning and result-driven routing decisions.

Pure functions (no I/O) so every routing rule is unit-tested directly.
The LangGraph orchestrator node calls ``build_plan`` once, then ``decide``
after every stage; the conditional edge only reads ``state["next_agents"]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

AGENT_IDS = ["analyzer", "developer", "tester", "reviewer"]

# Stages per mission. A stage with several agents is executed in parallel.
PIPELINES: dict[str, list[list[str]]] = {
    "BUG_FIX": [["analyzer"], ["developer"], ["tester"], ["reviewer"]],
    "TEST_GEN": [["analyzer"], ["tester"], ["reviewer"]],
    "CODE_REVIEW": [["analyzer", "tester"], ["reviewer"]],
}

PLAN_RATIONALE = {
    "BUG_FIX": "A fix needs a diagnosis, a patch, independent validation and a final review.",
    "TEST_GEN": "No code change is requested, so the Developer is skipped; tests are written and reviewed.",
    "CODE_REVIEW": "Quality and testability are independent questions: run both in parallel, then merge.",
}

DEFAULT_SUBTASKS = {
    "BUG_FIX": {
        "analyzer": "Find the root cause of the defect and list the requirements of the fix.",
        "developer": "Produce a complete corrected version of the code.",
        "tester": "Write pytest cases and statically check the corrected code against them.",
        "reviewer": "Decide whether the fix satisfies the request and is safe to merge.",
    },
    "TEST_GEN": {
        "analyzer": "Describe the behaviour of the code and its edge cases.",
        "developer": "",
        "tester": "Write a pytest module covering nominal, edge and error cases.",
        "reviewer": "Check that the tests cover the behaviours identified by the Analyzer.",
    },
    "CODE_REVIEW": {
        "analyzer": "Review quality, security and maintainability.",
        "developer": "",
        "tester": "Assess testability and the edge cases a test suite must cover.",
        "reviewer": "Merge both reviews into a single prioritised verdict.",
    },
}

_KEYWORDS = {
    "TEST_GEN": r"\b(unit ?tests?|test suite|pytest|generate tests?|write tests?|coverage)\b",
    "CODE_REVIEW": r"\b(review|audit|assess|feedback|production[- ]ready|code quality)\b",
    "BUG_FIX": r"\b(bug|fix|crash|error|exception|broken|fails?|wrong)\b",
}


def classify_heuristic(request: str) -> tuple[str, float, str]:
    """Keyword fallback used when the LLM classifier is unavailable."""
    text = request.lower()
    for task_type in ("TEST_GEN", "CODE_REVIEW", "BUG_FIX"):
        if re.search(_KEYWORDS[task_type], text):
            return task_type, 0.6, f"Keyword match for {task_type} in the request."
    return "CODE_REVIEW", 0.3, "No clear intent detected; defaulting to a read-only review."


def build_plan(task_type: str) -> dict[str, Any]:
    stages = [list(s) for s in PIPELINES[task_type]]
    selected = [a for a in AGENT_IDS if any(a in s for s in stages)]
    return {
        "stages": stages,
        "selected_agents": selected,
        "skipped_agents": [a for a in AGENT_IDS if a not in selected],
        "rationale": PLAN_RATIONALE[task_type],
    }


@dataclass
class Decision:
    kind: str                 # dispatch | parallel | retry | rework | retry_error | complete | abort | limit
    next_agents: list[str]
    stage_index: int
    reason: str
    decision: str
    iteration_increment: bool = False
    final_status: str | None = None
    error_retry_agents: list[str] = field(default_factory=list)
    use_best_version: bool = False


def stage_of(stages: list[list[str]], agent: str) -> int:
    for i, stage in enumerate(stages):
        if agent in stage:
            return i
    raise ValueError(f"{agent} is not part of the plan")


def _name(agent: str) -> str:
    return agent.capitalize()


def _advance(stages: list[list[str]], index: int, reason: str) -> Decision:
    nxt = index + 1
    if nxt >= len(stages):
        return Decision("complete", [], index, reason, "Workflow complete", final_status="completed")
    agents = stages[nxt]
    parallel = len(agents) > 1
    names = " + ".join(_name(a) for a in agents)
    return Decision("parallel" if parallel else "dispatch", agents, nxt, reason,
                    f"Run {names} in parallel" if parallel else f"Hand off to {names}")


def _deliver_best(index: int, best: dict[str, Any], max_iterations: int, why: str) -> Decision:
    return Decision("limit", [], index,
                    f"Correction limit reached ({max_iterations}) and {why}. Delivering the best reviewer-approved "
                    f"version instead (quality {best.get('score')}/10, round {best.get('iteration', 0) + 1}).",
                    "Deliver best version", final_status="completed", use_best_version=True)


def decide(state: dict[str, Any], max_iterations: int, max_error_retries: int = 1) -> Decision:
    """Choose the next step from the results of the stage that just ran."""
    stages: list[list[str]] = state["stages"]
    index: int = state["stage_index"]
    task_type: str = state["task_type"]
    iteration: int = state.get("iteration_count", 0)
    current = [s for s in state.get("completed_steps", []) if s["dispatch_id"] == state["dispatch_id"]]
    outcomes = {s["agent"]: s["outcome"] for s in current}

    # 1. Agent errors: retry the failed agent(s) once, then abort.
    failed = [a for a, o in outcomes.items() if o == "error"]
    if failed:
        retries = state.get("error_retries", {})
        retryable = [a for a in failed if retries.get(a, 0) < max_error_retries]
        if len(retryable) == len(failed):
            names = ", ".join(_name(a) for a in failed)
            return Decision("retry_error", failed, index,
                            f"{names} failed (provider error or output rejected by an automatic check); retrying once with the error.",
                            f"Retry {names} after error", error_retry_agents=failed)
        return Decision("abort", [], index,
                        f"{', '.join(_name(a) for a in failed)} failed again after a retry.",
                        "Abort workflow", final_status="failed")

    tests = state.get("test_results") or {}
    review = state.get("review_feedback") or {}
    best = state.get("best_version") or {}

    # 2. Tester verdicts.
    if "tester" in outcomes and outcomes["tester"] == "validation_failed" and task_type != "CODE_REVIEW":
        failing = ", ".join(tests.get("failing_cases", [])[:3]) or "see report"
        if iteration >= max_iterations:
            if best:
                return _deliver_best(index, best, max_iterations, "the last round failed validation")
            return Decision("limit", [], index,
                            f"Validation still failing after {iteration} correction(s) (limit {max_iterations}).",
                            "Stop: correction limit reached", final_status="max_iterations_reached")
        target = "developer" if task_type == "BUG_FIX" else "tester"
        return Decision("retry", [target], stage_of(stages, target),
                        f"Static validation failed ({failing}). Sending the report back to the {_name(target)} "
                        f"(correction {iteration + 1}/{max_iterations}).",
                        f"Retry correction with {_name(target)}", iteration_increment=True)

    # 3. Reviewer verdicts (approval needs both the reviewer's yes and a score above the quality bar).
    if "reviewer" in outcomes:
        score = review.get("score", "?")
        threshold = state.get("quality_threshold", 8.0)
        if outcomes["reviewer"] == "approved":
            return Decision("complete", [], index,
                            f"Reviewer approved with quality {score}/10 (bar: {threshold}).",
                            "Workflow complete", final_status="completed")
        if task_type == "CODE_REVIEW":
            return Decision("complete", [], index,
                            "The review verdict is the deliverable: changes requested, nothing to rework here.",
                            "Deliver review verdict", final_status="completed")
        target = "developer" if task_type == "BUG_FIX" else "tester"
        if iteration >= max_iterations:
            if best and best.get("score", 0) > (score if isinstance(score, (int, float)) else -1):
                return _deliver_best(index, best, max_iterations, f"the last round scored {score}/10")
            if outcomes["reviewer"] == "below_threshold":
                return Decision("limit", [], index,
                                f"Correction limit reached ({max_iterations}). The reviewer approves this version "
                                f"(quality {score}/10, bar {threshold}): delivering the best version so far.",
                                "Deliver best version", final_status="completed")
            return Decision("limit", [], index,
                            f"Reviewer still rejects after {iteration} correction(s) (limit {max_iterations}, "
                            f"quality {score}/10).",
                            "Stop: correction limit reached", final_status="max_iterations_reached")
        changes = "; ".join(review.get("required_changes", [])[:2])
        rubric = review.get("rubric") or {}
        weakest = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(rubric.items(), key=lambda kv: kv[1])[:2])
        floor = state.get("min_rubric_score", 0.0)
        weak = [f"{k.replace('_', ' ')} {v}" for k, v in rubric.items() if v < floor]
        if outcomes["reviewer"] != "below_threshold":
            why = f"Reviewer rejected (quality {score}/10)"
        elif isinstance(score, (int, float)) and score >= threshold and weak:
            why = f"Quality {score}/10 meets the bar of {threshold}, but {', '.join(weak)} is under the per-criterion floor of {floor}"
        else:
            why = f"Quality {score}/10 is below the bar of {threshold}"
        return Decision("rework", [target], stage_of(stages, target),
                        f"{why}{f' — weakest: {weakest}' if weakest else ''}. "
                        f"To do: {changes or 'see review'}. Routing back to the {_name(target)} "
                        f"(correction {iteration + 1}/{max_iterations}).",
                        f"Rework requested from {_name(target)}", iteration_increment=True)

    # 4. Otherwise move to the next stage of the plan.
    done = " + ".join(_name(a) for a in outcomes) or "Stage"
    return _advance(stages, index, f"{done} completed successfully.")
