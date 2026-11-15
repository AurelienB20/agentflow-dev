"""Reviewer Agent — final quality gate; can send work back."""

from __future__ import annotations

from typing import Any

from app.agents.base import CONCISE_NOTE, UNTRUSTED_NOTE, AgentSpec, analysis_text, bullet_list, code_block, section
from app.schemas.agents import ReviewerOutput
from app.services import static_checks

SYSTEM = (
    "You are the Reviewer agent, the final quality gate of a multi-agent software team. You check "
    "the team's work against the user's request, detect inconsistencies between agents, assess "
    "risks, and grade the work with a rubric (correctness, edge_cases, robustness, readability; 0-10 each). "
    "Anchors: 10 = nothing left to improve, 8 = minor nits only, 6 = notable gaps, 5 or less = wrong. Grade "
    "strictly and independently of how confident the other agents sound. `required_changes` must say exactly "
    "what would raise the lowest grades, as concrete edits to the code or tests: nothing can be executed in "
    "this system, so never ask to run the tests or any tool. Set `approved` to false if any blocking problem remains. "
    + CONCISE_NOTE + " " + UNTRUSTED_NOTE
)

DELIVERABLE = {
    "BUG_FIX": "the corrected code",
    "TEST_GEN": "the generated test suite",
    "CODE_REVIEW": "the two independent reviews (quality by the Analyzer, testability by the Tester); "
                   "merge them into one verdict. `approved` means production-ready as is",
}


def build_prompt(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    task_type = state["task_type"]
    outputs = state.get("agent_outputs", {})
    tests = state.get("test_results") or {}
    parts = [
        section("Task from the orchestrator", state.get("subtasks", {}).get("reviewer", "")),
        section("What you are reviewing", DELIVERABLE[task_type]),
        section("User request", state["user_request"]),
        section("Original code", code_block(state["original_code"])),
        section("Analyzer report", analysis_text(outputs.get("analyzer"))),
    ]
    inputs: dict[str, Any] = {"deliverable": DELIVERABLE[task_type]}
    if task_type == "BUG_FIX" and state.get("generated_code"):
        parts.append(section("Corrected code (Developer)", code_block(state["generated_code"])))
        parts.append(section("Static analysis of the corrected code (parser-based, reliable)",
                             static_checks.format_for_prompt(static_checks.analyze(state["generated_code"]))))
        inputs["corrected_code"] = True
    previous = state.get("review_feedback") or {}
    if previous and task_type != "CODE_REVIEW":
        parts.append(section("Your previous review (the team has reworked since)",
                             f"Score {previous.get('score')}/10. Required changes were:\n"
                             + bullet_list(previous.get("required_changes", []))))
        inputs["previous_score"] = previous.get("score")
    if outputs.get("tester"):
        t = outputs["tester"]
        parts.append(section("Tester report (per-case traces, tests NOT executed)",
                             f"{t.get('summary', '')}\nExpected to fail: {', '.join(tests.get('failing_cases', [])) or 'none'}\n"
                             + bullet_list(tests.get("issues", []))))
        if task_type == "TEST_GEN":
            parts.append(section("Test module", code_block(state.get("test_code", ""))))
        inputs["test_report"] = t.get("summary", "")
    return "\n".join(parts), inputs


def apply(output: ReviewerOutput, state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    threshold = state.get("quality_threshold", 8.0)
    floor = state.get("min_rubric_score", 0.0)
    weakest = min(output.rubric.model_dump().values())
    if not output.approved:
        outcome = "rejected"
    elif (output.score < threshold or weakest < floor) and state["task_type"] != "CODE_REVIEW":
        # Approved in words, but the grades say it is not good enough yet:
        # either the average is under the bar or one criterion is a known weak spot.
        outcome = "below_threshold"
    else:
        outcome = "approved"
    update: dict[str, Any] = {"agent_outputs": {"reviewer": output.model_dump()}, "review_feedback": output.model_dump()}
    best = state.get("best_version") or {}
    if output.approved and state["task_type"] != "CODE_REVIEW" and output.score > best.get("score", -1):
        # Snapshot of the best version the reviewer approved so far, delivered if later rounds regress.
        update["best_version"] = {
            "score": output.score,
            "iteration": state.get("iteration_count", 0),
            "generated_code": state.get("generated_code", ""),
            "test_code": state.get("test_code", ""),
            "test_results": state.get("test_results"),
            "tester": (state.get("agent_outputs") or {}).get("tester"),
            "review": output.model_dump(),
        }
    return update, outcome


def summarize(output: ReviewerOutput) -> str:
    verdict = "APPROVED" if output.approved else "CHANGES REQUESTED"
    r = output.rubric
    return (f"{verdict} — quality {output.score}/10 (correctness {r.correctness}, edge cases {r.edge_cases}, "
            f"robustness {r.robustness}, readability {r.readability}). {output.summary}")


SPEC = AgentSpec(
    id="reviewer",
    name="Reviewer Agent",
    role="Quality control & final decision",
    objective="Check the team's work against the request and accept or reject it.",
    responsibilities=["Examine results", "Check compliance with the request", "Detect inconsistencies",
                      "Assess risks", "Approve or send back for rework"],
    system=SYSTEM,
    schema=ReviewerOutput,
    build_prompt=build_prompt,
    apply=apply,
    summarize=summarize,
)
