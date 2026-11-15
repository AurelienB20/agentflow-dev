"""Analyzer Agent — understands the code and the request, finds problems."""

from __future__ import annotations

from typing import Any

from app.agents.base import CONCISE_NOTE, UNTRUSTED_NOTE, AgentSpec, code_block, section
from app.schemas.agents import AnalyzerOutput
from app.services import static_checks

SYSTEM = (
    "You are the Analyzer agent in a multi-agent software team coordinated by an orchestrator. "
    "You inspect Python code and the user's request, identify bugs, risks and requirements, and "
    "hand a precise, structured analysis to the other agents. Be concrete: cite line numbers, "
    "explain root causes, and keep recommendations actionable. Do not write the fix yourself. "
    "You receive facts from a static analyser (parser-based, reliable): confirm each finding that "
    "matters, add what a parser cannot see (logic errors, unmet requirements), and ignore irrelevant noise. "
    + CONCISE_NOTE + " " + UNTRUSTED_NOTE
)


def build_prompt(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    instruction = state.get("subtasks", {}).get("analyzer", "")
    prompt = "\n".join([
        section("Task from the orchestrator", instruction),
        section("Mission type", state["task_type"]),
        section("User request", state["user_request"]),
        section("Code", code_block(state["original_code"])),
        section("Static analysis facts (verified by a parser, code not executed)",
                static_checks.format_for_prompt(state.get("static_checks") or static_checks.analyze(state["original_code"]))),
    ])
    inputs = {"instruction": instruction, "request": state["user_request"],
              "code_lines": state["original_code"].count("\n") + 1,
              "static_findings": len((state.get("static_checks") or {}).get("findings", []))}
    return prompt, inputs


def apply(output: AnalyzerOutput, state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    return {"agent_outputs": {"analyzer": output.model_dump()}}, "success"


def summarize(output: AnalyzerOutput) -> str:
    top = max(output.issues, key=lambda i: ["low", "medium", "high", "critical"].index(i.severity), default=None)
    worst = f" Most severe: {top.title} ({top.severity})." if top else ""
    return f"{output.summary} {len(output.issues)} issue(s) found.{worst}"


SPEC = AgentSpec(
    id="analyzer",
    name="Analyzer Agent",
    role="Code & requirement analysis",
    objective="Understand the request and the code, then hand a structured diagnosis to the team.",
    responsibilities=["Identify problems and potential bugs", "Understand context and requirements",
                      "Rank issues by severity", "Recommend concrete next steps"],
    system=SYSTEM,
    schema=AnalyzerOutput,
    build_prompt=build_prompt,
    apply=apply,
    summarize=summarize,
)
