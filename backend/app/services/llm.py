"""LLM provider abstraction with a hard per-workflow budget.

Providers:
- ``AnthropicProvider``  — Claude via the official ``anthropic`` SDK, structured outputs.
- ``OpenAIProvider``     — OpenAI-compatible chat completions in JSON mode.
- ``ScriptedProvider``   — deterministic, offline "model" replaying a scenario
  script. Used by the test-suite and to record the Guided Demo. It is always
  reported as *simulated* in events and in the UI.

API keys are read from the server environment only and never leave the backend.
"""

from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import DEFAULT_PRICE, MODEL_PRICES, Settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """A model call failed or returned unusable output (retryable by the orchestrator)."""


class BudgetExceeded(Exception):
    """The workflow hit its call or cost ceiling (never retried)."""


@dataclass
class BudgetTracker:
    max_calls: int
    max_cost_usd: float
    price_in: float  # USD / 1M input tokens
    price_out: float  # USD / 1M output tokens
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def before_call(self) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"LLM call limit reached ({self.max_calls} calls per workflow)")
        if self.cost_usd >= self.max_cost_usd:
            raise BudgetExceeded(f"Budget reached (${self.cost_usd:.4f} of ${self.max_cost_usd:.2f})")
        self.calls += 1

    def record(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += input_tokens / 1e6 * self.price_in + output_tokens / 1e6 * self.price_out

    def snapshot(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 5),
            "max_cost_usd": self.max_cost_usd,
        }


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""
    simulated: bool = False

    @abstractmethod
    async def generate(self, *, role: str, system: str, prompt: str, schema: type[T],
                       budget: BudgetTracker) -> T: ...

    def new_budget(self, settings: Settings) -> BudgetTracker:
        price_in, price_out = MODEL_PRICES.get(self.model, DEFAULT_PRICE)
        if self.simulated:
            price_in = price_out = 0.0
        return BudgetTracker(settings.max_llm_calls_per_workflow, settings.max_cost_per_workflow_usd,
                             price_in, price_out)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        import anthropic

        self._anthropic = anthropic
        self.model = settings.llm_model
        self.effort = settings.llm_effort
        self.max_tokens = settings.llm_max_tokens
        self.client = anthropic.AsyncAnthropic(timeout=settings.llm_call_timeout_s, max_retries=1)

    async def generate(self, *, role: str, system: str, prompt: str, schema: type[T],
                       budget: BudgetTracker) -> T:
        a = self._anthropic
        budget.before_call()
        try:
            response = await self.client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                output_config={"effort": self.effort},
            )
        except a.RateLimitError as exc:
            raise LLMError("LLM provider rate limit reached, please retry later") from exc
        except a.AuthenticationError as exc:
            raise LLMError("LLM provider rejected the server credentials") from exc
        except a.BadRequestError as exc:
            raise LLMError(f"LLM request rejected: {exc.message}") from exc
        except a.APIStatusError as exc:
            raise LLMError(f"LLM provider error ({exc.status_code})") from exc
        except a.APIConnectionError as exc:
            raise LLMError("Could not reach the LLM provider") from exc
        except ValidationError as exc:
            raise LLMError(f"{role} returned output that does not match its schema") from exc

        budget.record(response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason == "refusal":
            raise LLMError(f"{role}: the model declined this request")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"{role}: output truncated (LLM_MAX_TOKENS too low)")
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError(f"{role}: no structured output returned")
        return parsed


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        import openai

        self._openai = openai
        self.model = settings.llm_model
        self.max_tokens = settings.llm_max_tokens
        self.client = openai.AsyncOpenAI(timeout=settings.llm_call_timeout_s, max_retries=1)

    async def generate(self, *, role: str, system: str, prompt: str, schema: type[T],
                       budget: BudgetTracker) -> T:
        budget.before_call()
        schema_json = json.dumps(schema.model_json_schema())
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": f"{system}\n\nReply with one JSON object matching this JSON Schema:\n{schema_json}"},
                    {"role": "user", "content": prompt},
                ],
            )
        except self._openai.APIError as exc:
            raise LLMError(f"LLM provider error: {exc.__class__.__name__}") from exc
        if response.usage:
            budget.record(response.usage.prompt_tokens, response.usage.completion_tokens)
        content = response.choices[0].message.content or ""
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            raise LLMError(f"{role} returned output that does not match its schema") from exc


# Simulated latency per role, in seconds, for the scripted model.
SCRIPTED_LATENCY = {"classifier": 1.2, "analyzer": 2.6, "developer": 3.0, "tester": 2.4, "tester_verify": 1.8,
                    "reviewer": 2.4}


class ScriptedProvider(LLMProvider):
    """Deterministic offline model: returns the next scripted output for each role.

    ``failures`` lets tests inject errors: {"developer": 1} makes the first
    developer call raise ``LLMError``.
    """

    name = "mock"
    model = "scripted-demo-model"
    simulated = True

    def __init__(self, script: dict[str, list[dict[str, Any]]], delay_scale: float = 0.0,
                 failures: dict[str, int] | None = None) -> None:
        self.script = script
        self.delay_scale = delay_scale
        self.failures = dict(failures or {})
        self.calls: dict[str, int] = {}

    async def generate(self, *, role: str, system: str, prompt: str, schema: type[T],
                       budget: BudgetTracker) -> T:
        budget.before_call()
        if self.delay_scale:
            await asyncio.sleep(SCRIPTED_LATENCY.get(role, 2.0) * self.delay_scale)
        budget.record(len(system + prompt) // 4, 400)  # token estimate, priced at $0
        if self.failures.get(role, 0) > 0:
            self.failures[role] -= 1
            raise LLMError(f"{role}: simulated provider timeout")
        outputs = self.script.get(role)
        if not outputs:
            raise LLMError(f"No scripted output for role '{role}'")
        index = self.calls.get(role, 0)
        self.calls[role] = index + 1
        return schema.model_validate(outputs[min(index, len(outputs) - 1)])


def make_provider(settings: Settings, scenario_script: dict[str, list[dict[str, Any]]] | None) -> LLMProvider:
    """Build the provider configured for live workflows."""
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings)
    if settings.llm_provider == "openai":
        return OpenAIProvider(settings)
    if settings.llm_provider == "mock":
        if scenario_script is None:
            raise LLMError("The simulated model only knows the three built-in scenarios")
        return ScriptedProvider(scenario_script, delay_scale=settings.mock_delay_scale)
    raise LLMError("Live AI mode is not configured on this server (set LLM_PROVIDER)")


def provider_available(settings: Settings) -> bool:
    if settings.llm_provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    return settings.live_available
