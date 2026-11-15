"""Structured outputs produced by the orchestrator and the four agents.

These Pydantic models are the contract between agents: every LLM call is
constrained to one of them, and the orchestrator routes on their fields
(e.g. ``TesterOutput.validation.passed`` or ``ReviewerOutput.approved``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

TaskType = Literal["BUG_FIX", "TEST_GEN", "CODE_REVIEW"]
Severity = Literal["low", "medium", "high", "critical"]


class Subtasks(BaseModel):
    analyzer: str = Field(default="", description="Instruction for the Analyzer agent, empty if not used")
    developer: str = Field(default="", description="Instruction for the Developer agent, empty if not used")
    tester: str = Field(default="", description="Instruction for the Tester agent, empty if not used")
    reviewer: str = Field(default="", description="Instruction for the Reviewer agent, empty if not used")


class ClassifierOutput(BaseModel):
    task_type: TaskType
    confidence: float = Field(ge=0, le=1)
    reason: str
    subtasks: Subtasks


class Issue(BaseModel):
    title: str
    severity: Severity
    line: int | None = None
    detail: str


class AnalyzerOutput(BaseModel):
    summary: str
    issues: list[Issue]
    recommendations: list[str]


class DeveloperOutput(BaseModel):
    summary: str
    code: str = Field(description="The complete updated source code")
    changes: list[str]


class TestCase(BaseModel):
    name: str
    category: Literal["nominal", "edge", "error", "adversarial"]
    description: str


class TestSuite(BaseModel):
    """Tester step 1: write the tests (LLM output)."""
    summary: str
    test_code: str = Field(description="A complete pytest module")
    cases: list[TestCase]


class CaseTrace(BaseModel):
    case: str = Field(description="Exact name of the test case")
    trace: str = Field(description="Short step-by-step walk through the code for this input")
    expected: str = Field(description="What the test asserts")
    predicted: str = Field(description="What the code actually returns or raises, from the trace")
    passes: bool = Field(description="True only if predicted matches expected")


class TestVerification(BaseModel):
    """Tester step 2: trace the code against every case (LLM output)."""
    traces: list[CaseTrace]
    issues: list[str] = Field(description="Problems found while tracing; empty if none")


class StaticValidation(BaseModel):
    passed: bool
    failing_cases: list[str]
    issues: list[str]


class TesterOutput(BaseModel):
    """Combined Tester result. ``validation`` is derived from the traces by code, not by the model."""
    summary: str
    test_code: str
    cases: list[TestCase]
    traces: list[CaseTrace]
    validation: StaticValidation


class Rubric(BaseModel):
    """Reviewer grades, 0-10 each. 10 = nothing left to improve, 8 = minor nits only,
    6 = notable gaps, 5 or less = wrong or unusable."""
    correctness: int = Field(ge=0, le=10, description="Does it do exactly what the request requires?")
    edge_cases: int = Field(ge=0, le=10, description="Empty, extreme, unusual and invalid inputs handled or covered")
    robustness: int = Field(ge=0, le=10, description="Errors, resources and failure modes handled safely")
    readability: int = Field(ge=0, le=10, description="Clear names, structure, docstrings, type hints")


class ReviewerOutput(BaseModel):
    summary: str
    approved: bool
    rubric: Rubric
    findings: list[str]
    required_changes: list[str] = Field(description="Concrete changes that would raise the lowest grades")
    risks: list[str]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def score(self) -> float:
        """Overall quality, computed by code from the rubric (mean, one decimal)."""
        r = self.rubric
        return round((r.correctness + r.edge_cases + r.robustness + r.readability) / 4, 1)


AGENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "analyzer": AnalyzerOutput,
    "developer": DeveloperOutput,
    "tester": TesterOutput,
    "reviewer": ReviewerOutput,
}
