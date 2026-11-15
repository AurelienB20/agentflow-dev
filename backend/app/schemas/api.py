"""Request / response models for the REST API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowCreate(BaseModel):
    scenario_id: str | None = Field(default=None, max_length=64)
    task_type: Literal["auto", "BUG_FIX", "TEST_GEN", "CODE_REVIEW"] = "auto"
    code: str = Field(min_length=1)
    request: str = Field(min_length=1)


class WorkflowCreated(BaseModel):
    workflow_id: str
    status: str
    events_url: str
    provider: str
    model: str
    simulated: bool
    cached: bool = False


class WorkflowSnapshot(BaseModel):
    workflow_id: str
    status: str
    created_at: str
    event_count: int
    final_result: dict[str, Any] | None = None
    error: str | None = None


class ScenarioInfo(BaseModel):
    id: str
    title: str
    short_title: str
    description: str
    task_type: str
    highlights: list[str]
    code: str
    request: str


class AgentInfo(BaseModel):
    id: str
    name: str
    role: str
    objective: str
    responsibilities: list[str]
