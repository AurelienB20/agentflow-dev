"""Developer Agent — writes or corrects code, taking feedback into account."""

from __future__ import annotations

from typing import Any

from app.agents.base import CONCISE_NOTE, UNTRUSTED_NOTE, AgentSpec, analysis_text, bullet_list, code_block, section
from app.schemas.agents import DeveloperOutput
from app.services import static_checks

SYSTEM = (
    "You are the Developer agent in a multi-agent software team. You receive the Analyzer's "
    "diagnosis and, on later iterations, the Tester's validation report or the Reviewer's "
    "required changes. Produce the complete corrected Python source (not a diff), keep the public "
    "function names, and address every piece of feedback explicitly in `changes`. "
    + CONCISE_NOTE + " " + UNTRUSTED_NOTE
)


def build_prompt(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    outputs = state.get("agent_outputs", {})
    tests = state.get("test_results") or {}
    review = state.get("review_feedback") or {}
    previous = state.get("generated_code", "")
    parts = [
        section("Task from the orchestrator", state.get("subtasks", {}).get("developer", "")),
        section("User request", state["user_request"]),
        section("Original code", code_block(state["original_code"])),
        section("Analyzer report", analysis_text(outputs.get("analyzer"))),
    ]
    inputs: dict[str, Any] = {"analysis": outputs.get("analyzer", {}).get("summary", "")}
    if previous:
        parts.append(section("Your previous attempt", code_block(previous)))
        inputs["previous_attempt"] = True
    if tests and not tests.get("passed", True):
        parts.append(section("Tester report — validation FAILED",
                             bullet_list(tests.get("issues", []) + [f"Failing: {c}" for c in tests.get("failing_cases", [])])))
        inputs["test_feedback"] = tests.get("issues", [])
    if review and not review.get("approved", True):
        parts.append(section("Reviewer required changes", bullet_list(review.get("required_changes", []))))
        inputs["review_feedback"] = review.get("required_changes", [])
    feedback = (state.get("agent_feedback") or {}).get("developer")
    if feedback:
        parts.append(section("Your previous output was rejected by an automatic check", feedback))
        inputs["validator_feedback"] = feedback
    return "\n".join(parts), inputs


def validate(output: DeveloperOutput, state: dict[str, Any]) -> str | None:
    """Reject code that does not parse or that drops a public function of the original."""
    report = static_checks.analyze(output.code)
    if not report["syntax_ok"]:
        return f"The code does not parse ({report['syntax_error']}). Return the complete, valid Python source."
    missing = sorted(static_checks.public_names(state["original_code"]) - static_checks.public_names(output.code))
    if missing:
        return f"Public names removed: {', '.join(missing)}. Keep the original function names."
    return None


def apply(output: DeveloperOutput, state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    return {"agent_outputs": {"developer": output.model_dump()}, "generated_code": output.code}, "success"


def summarize(output: DeveloperOutput) -> str:
    return f"{output.summary} ({len(output.changes)} change(s))"


SPEC = AgentSpec(
    id="developer",
    name="Developer Agent",
    role="Code generation & correction",
    objective="Turn the diagnosis and the feedback of other agents into working code.",
    responsibilities=["Fix bugs", "Generate and improve functions", "Apply recommendations",
                      "Incorporate Tester and Reviewer feedback"],
    system=SYSTEM,
    schema=DeveloperOutput,
    build_prompt=build_prompt,
    apply=apply,
    summarize=summarize,
    validate=validate,
)
