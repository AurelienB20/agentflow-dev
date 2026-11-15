"""Tester Agent — generates tests, then traces the code against each case.

Two focused LLM steps instead of one broad one (easier for small models):

1. ``write``  → a pytest module and the list of cases (``TestSuite``);
2. ``verify`` → one step-by-step trace per case (``TestVerification``).

The pass/fail verdict is then *computed by code* from the traces
(``passed = all(trace.passes)``), so the model cannot claim "all good" while
its own traces show a failure. No sandbox is available in the MVP, so tests
are generated, never executed (``executed: False``).
"""

from __future__ import annotations

from typing import Any

from app.agents.base import CONCISE_NOTE, UNTRUSTED_NOTE, AgentSpec, analysis_text, bullet_list, code_block, section
from app.schemas.agents import StaticValidation, TesterOutput, TestSuite, TestVerification
from app.services import static_checks

WRITE_SYSTEM = (
    "You are the Tester agent in a multi-agent software team, and your job is to BREAK the code, not to "
    "confirm it works. Write a complete pytest module (`from solution import ...`). Cover every requirement "
    "of the request with at least one test, then spend the rest on adversarial cases: boundaries (0, 1, -1, "
    "very large), empty and single-element inputs, one-shot iterators, duplicates, unicode, unusual but valid "
    "types, call sequences that change internal state, and inputs the docstring allows but the author probably "
    "forgot. Mark those cases `adversarial`. Only assert behaviour that the request or the docstring requires "
    "or clearly implies: never invent requirements. List every test function in `cases` with its exact name. "
    "At most 10 focused tests; keep the module compact. " + CONCISE_NOTE + " " + UNTRUSTED_NOTE
)

VERIFY_SYSTEM = (
    "You are the Tester agent, verification step. You cannot run code: for EACH test case, trace the code "
    "under test line by line with that input and write down what it really returns or raises. Then compare "
    "with what the test asserts. Set `passes` to true only if they match. Be literal: generators can be "
    "consumed only once, `if not x` is always False for a generator object, len() fails on generators.\n\n"
    "Example trace:\n"
    "  case: test_empty_list_raises\n"
    "  trace: numbers=[] -> `if not numbers` is True -> raise ValueError\n"
    "  expected: raises ValueError\n"
    "  predicted: raises ValueError\n"
    "  passes: true\n\n"
    "Produce exactly one trace per case, using the exact case names. " + CONCISE_NOTE + " " + UNTRUSTED_NOTE
)

FOCUS = {
    "BUG_FIX": "Validate the Developer's corrected code against the user's requirements.",
    "TEST_GEN": "Write tests that pin down the current behaviour of the original code. "
                "A trace `passes` when your expected value matches what the code really does.",
    "CODE_REVIEW": "Assess testability: write the cases a suite must cover; traces show which would fail today. "
                   "This review runs in parallel with the Analyzer; you do not see its report.",
}


def _target(state: dict[str, Any]) -> str:
    if state["task_type"] == "BUG_FIX" and state.get("generated_code"):
        return state["generated_code"]
    return state["original_code"]


def build_prompt(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    task_type = state["task_type"]
    outputs = state.get("agent_outputs", {})
    review = state.get("review_feedback") or {}
    target = _target(state)
    parts = [
        section("Task from the orchestrator", state.get("subtasks", {}).get("tester", "")),
        section("Focus", FOCUS[task_type]),
        section("User request", state["user_request"]),
        section("Code under test", code_block(target)),
        section("Static analysis facts (verified by a parser, code not executed)",
                static_checks.format_for_prompt(static_checks.analyze(target))),
    ]
    inputs: dict[str, Any] = {"focus": FOCUS[task_type],
                              "code_under_test": "corrected code" if target != state["original_code"] else "original code"}
    if task_type != "CODE_REVIEW" and outputs.get("analyzer"):
        parts.append(section("Analyzer report", analysis_text(outputs["analyzer"])))
        inputs["analysis"] = outputs["analyzer"].get("summary", "")
    if task_type == "TEST_GEN" and review and not review.get("approved", True):
        parts.append(section("Your previous test module", code_block(state.get("test_code", ""))))
        parts.append(section("Reviewer required changes", bullet_list(review.get("required_changes", []))))
        inputs["review_feedback"] = review.get("required_changes", [])
    feedback = (state.get("agent_feedback") or {}).get("tester")
    if feedback:
        parts.append(section("Your previous output was rejected by an automatic check", feedback))
        inputs["validator_feedback"] = feedback
    return "\n".join(parts), inputs


def _verify_prompt(state: dict[str, Any], suite: TestSuite) -> str:
    cases = "\n".join(f"- {c.name} ({c.category}): {c.description}" for c in suite.cases)
    return "\n".join([
        section("User request", state["user_request"]),
        section("Code under test", code_block(_target(state))),
        section("Test module", code_block(suite.test_code)),
        section("Cases to trace (one trace each, exact names)", cases),
    ])


async def run(provider, state: dict[str, Any], prompt: str, budget) -> TesterOutput:
    suite = await provider.generate(role="tester", system=WRITE_SYSTEM, prompt=prompt, schema=TestSuite, budget=budget)
    verification = await provider.generate(role="tester_verify", system=VERIFY_SYSTEM,
                                           prompt=_verify_prompt(state, suite), schema=TestVerification,
                                           budget=budget)
    failing = [t.case for t in verification.traces if not t.passes]
    issues = list(verification.issues)
    for t in verification.traces:
        if not t.passes and not any(t.case in i for i in issues):
            issues.append(f"{t.case}: expected {t.expected}, but {t.predicted}")
    return TesterOutput(
        summary=suite.summary,
        test_code=suite.test_code,
        cases=suite.cases,
        traces=verification.traces,
        validation=StaticValidation(passed=not failing, failing_cases=failing, issues=issues),
    )


def validate(output: TesterOutput, state: dict[str, Any]) -> str | None:
    """Deterministic checks; a message means the output is rejected and the agent retried."""
    report = static_checks.analyze(output.test_code)
    if not report["syntax_ok"]:
        return f"The test module does not parse ({report['syntax_error']}). Return valid Python."
    defined = static_checks.collect_test_names(output.test_code)
    if not defined:
        return "The test module defines no test_* function."
    case_names = {c.name for c in output.cases}
    unknown = sorted(n for n in case_names if not any(n == d or n.startswith(d) for d in defined))
    if unknown:
        return f"These listed cases are not defined in the module: {', '.join(unknown)}."
    traced = {t.case for t in output.traces}
    missing = sorted(case_names - traced)
    if missing:
        return f"No trace for: {', '.join(missing)}. Trace every case."
    return None


def apply(output: TesterOutput, state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    v = output.validation
    results = {
        "executed": False,
        "method": "per-case code tracing by the Tester agent; verdict computed from the traces (tests not executed)",
        "passed": v.passed,
        "failing_cases": v.failing_cases,
        "issues": v.issues,
        "total_cases": len(output.cases),
    }
    outcome = "success"
    if not v.passed and state["task_type"] != "CODE_REVIEW":
        outcome = "validation_failed"
    return {"agent_outputs": {"tester": output.model_dump()}, "test_results": results,
            "test_code": output.test_code}, outcome


def summarize(output: TesterOutput) -> str:
    v = output.validation
    verdict = "all cases expected to pass" if v.passed else f"{len(v.failing_cases)} case(s) expected to fail"
    return f"{output.summary} [{len(output.cases)} tests generated, not executed — traced: {verdict}]"


SPEC = AgentSpec(
    id="tester",
    name="Tester Agent",
    role="Test generation & validation",
    objective="Write tests, hunt edge cases and decide whether the code is ready to move on.",
    responsibilities=["Generate pytest tests", "Trace the code against every case",
                      "Derive the verdict from the traces", "Request a correction when a case fails",
                      "Never claim unexecuted tests ran"],
    system=WRITE_SYSTEM,
    schema=TesterOutput,
    build_prompt=build_prompt,
    apply=apply,
    summarize=summarize,
    run=run,
    validate=validate,
)
