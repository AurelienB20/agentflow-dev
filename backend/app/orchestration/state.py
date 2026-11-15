"""Typed shared state for the LangGraph workflow.

Keys that can be written by several nodes in the same super-step (the
parallel Analyzer + Tester branch) use reducers, so concurrent updates are
merged instead of raising ``InvalidUpdateError``:

- ``agent_outputs``   dict merge (each agent writes its own key)
- ``completed_steps`` list concatenation
- ``errors``          list concatenation
- ``error_retries``   dict merge
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class StepRecord(TypedDict):
    agent: str
    dispatch_id: int
    outcome: str  # success | validation_failed | approved | rejected | error
    duration_ms: int
    iteration: int


class AgentState(TypedDict, total=False):
    # identity & request
    workflow_id: str
    task_type: str            # BUG_FIX | TEST_GEN | CODE_REVIEW (set by the orchestrator)
    task_hint: str            # optional hint from the UI ("auto" or a task type)
    user_request: str
    original_code: str

    # plan produced by the orchestrator
    selected_agents: list[str]
    stages: list[list[str]]   # ordered stages; a stage with >1 agent runs in parallel
    subtasks: dict[str, str]  # per-agent instruction (task decomposition)
    stage_index: int
    dispatch_id: int          # increments at every dispatch; tags step records
    next_agents: list[str]    # read by the conditional edge after the orchestrator

    # work products (shared between agents)
    generated_code: str
    test_code: str
    agent_outputs: Annotated[dict[str, Any], merge_dicts]
    test_results: dict[str, Any]
    review_feedback: dict[str, Any]

    # deterministic tool results and automatic-check feedback
    static_checks: dict[str, Any]                          # parser-based analysis of the original code
    agent_feedback: Annotated[dict[str, str], merge_dicts]  # validator message per agent ("" = none)

    # supervision
    completed_steps: Annotated[list[StepRecord], operator.add]
    error_retries: Annotated[dict[str, int], merge_dicts]
    iteration_count: int      # correction loops performed so far
    quality_threshold: float  # minimum reviewer score to accept the work
    min_rubric_score: float  # minimum grade on every rubric criterion
    best_version: dict[str, Any]  # best reviewer-approved snapshot (delivered if later rounds regress)
    status: str
    errors: Annotated[list[str], operator.add]
    final_result: dict[str, Any]
