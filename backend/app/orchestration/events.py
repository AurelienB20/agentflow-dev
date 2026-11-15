"""Workflow runs and their event streams.

Every observable thing the backend does (classification, decisions, agent
start/finish, messages, transitions, usage) is appended to the run's event
log by the code that performs it. The SSE endpoint streams that log; late
subscribers first receive the history, so a reconnect never loses events.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any, AsyncIterator

TERMINAL_EVENTS = {"workflow_completed", "workflow_failed", "workflow_cancelled"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class WorkflowRun:
    def __init__(self, *, mode: str, provider: str, model: str, simulated: bool,
                 workflow_id: str | None = None) -> None:
        self.id = workflow_id or f"wf_{uuid.uuid4().hex[:12]}"
        self.mode = mode
        self.provider = provider
        self.model = model
        self.simulated = simulated
        self.created_at = _now_iso()
        self.created_monotonic = time.monotonic()
        self.status = "pending"
        self.events: list[dict[str, Any]] = []
        self.final_result: dict[str, Any] | None = None
        self.error: str | None = None
        self.task: asyncio.Task | None = None
        self.cached = False  # replay of a stored real run (no LLM call)
        self._changed = asyncio.Event()

    # ---------------------------------------------------------------- emit
    def emit(self, type_: str, *, agent: str | None = None, **data: Any) -> dict[str, Any]:
        event = {
            "seq": len(self.events) + 1,
            "workflow_id": self.id,
            "type": type_,
            "agent": agent,
            "t": round(time.monotonic() - self.created_monotonic, 3),
            "timestamp": _now_iso(),
            "data": data,
        }
        self.events.append(event)
        if type_ in TERMINAL_EVENTS:
            self.status = {"workflow_completed": "completed", "workflow_failed": "failed",
                           "workflow_cancelled": "cancelled"}[type_]
        changed, self._changed = self._changed, asyncio.Event()
        changed.set()
        return event

    def message(self, sender: str, receiver: str, msg_type: str, content: str,
                payload: dict[str, Any] | None = None) -> None:
        """Structured inter-agent message (sender, receiver, type, content, workflow, time)."""
        self.emit("message", agent=sender, sender=sender, receiver=receiver,
                  message_type=msg_type, content=content, payload=payload or {})

    def decision(self, decision: str, reason: str, *, kind: str, next_agents: list[str] | None = None,
                 **extra: Any) -> None:
        self.emit("decision", agent="orchestrator", decision=decision, reason=reason, kind=kind,
                  next=next_agents or [], **extra)

    def transition(self, source: str, target: str, kind: str, label: str = "") -> None:
        self.emit("transition", source=source, target=target, kind=kind, label=label)

    # -------------------------------------------------------------- stream
    @property
    def finished(self) -> bool:
        return self.status in {"completed", "failed", "cancelled"}

    async def stream(self, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        index = max(0, after)
        while True:
            waiter = self._changed
            while index < len(self.events):
                event = self.events[index]
                index += 1
                yield event
                if event["type"] in TERMINAL_EVENTS:
                    return
            if self.finished:
                return
            await waiter.wait()

    def snapshot(self) -> dict[str, Any]:
        return {
            "workflow_id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "event_count": len(self.events),
            "final_result": self.final_result,
            "error": self.error,
        }


class RunRegistry:
    """In-memory store of recent runs (MVP: no database needed)."""

    def __init__(self, max_runs: int = 200, ttl_s: float = 3600) -> None:
        self.max_runs = max_runs
        self.ttl_s = ttl_s
        self._runs: dict[str, WorkflowRun] = {}

    def add(self, run: WorkflowRun) -> None:
        self._prune()
        self._runs[run.id] = run

    def get(self, workflow_id: str) -> WorkflowRun | None:
        return self._runs.get(workflow_id)

    def active_count(self) -> int:
        """Running paid workflows (cache replays cost nothing and are not counted)."""
        return sum(1 for r in self._runs.values() if not r.finished and not r.cached)

    def _prune(self) -> None:
        now = time.monotonic()
        for wid, run in list(self._runs.items()):
            if run.finished and now - run.created_monotonic > self.ttl_s:
                del self._runs[wid]
        while len(self._runs) >= self.max_runs:
            oldest = min((r for r in self._runs.values() if r.finished),
                         key=lambda r: r.created_monotonic, default=None)
            if oldest is None:
                break
            del self._runs[oldest.id]


registry = RunRegistry()
