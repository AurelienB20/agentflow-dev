"""Runtime configuration, read once from environment variables.

Every limit that protects the public demo (rate limits, quotas, timeouts,
iteration caps, input sizes, LLM budget) lives here so it can be tuned per
deployment without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    for candidate in (PROJECT_ROOT / "backend" / ".env", PROJECT_ROOT / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# USD per million tokens (input, output). Used for the per-workflow budget.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}
DEFAULT_PRICE = (5.0, 25.0)  # conservative fallback for unknown models

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "",  # must be provided through LLM_MODEL
    "mock": "scripted-demo-model",
}


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "none"  # anthropic | openai | mock | none
    llm_model: str = ""
    llm_effort: str = "low"
    llm_max_tokens: int = 4096
    llm_call_timeout_s: float = 60.0

    max_iterations: int = 3
    quality_threshold: float = 8.0  # reviewer score (0-10) required to accept a fix or a test suite
    min_rubric_score: float = 8.0  # every rubric criterion must reach this too (no known weak spot)
    workflow_timeout_s: float = 180.0
    max_llm_calls_per_workflow: int = 14
    max_cost_per_workflow_usd: float = 0.50

    max_code_chars: int = 6000
    max_request_chars: int = 1000
    max_concurrent_workflows: int = 3
    rate_limit_per_ip_per_hour: int = 5
    quota_per_session: int = 2
    max_live_workflows_per_day: int = 50  # global cap on paid runs (cache hits excluded)
    trust_proxy: bool = True

    result_cache: bool = True
    result_cache_path: str = str(PROJECT_ROOT / "backend" / "data" / "result_cache.sqlite")
    result_cache_ttl_days: float = 30.0
    result_cache_include_simulated: bool = False

    allowed_origins: list[str] = field(default_factory=lambda: ["*"])
    mock_delay_scale: float = 1.0

    @property
    def live_available(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
        if self.llm_provider == "openai":
            return bool(os.environ.get("OPENAI_API_KEY")) and bool(self.llm_model)
        return self.llm_provider == "mock"

    @property
    def is_simulated(self) -> bool:
        return self.llm_provider == "mock"


def load_settings() -> Settings:
    _load_dotenv()
    provider = os.environ.get("LLM_PROVIDER", "none").strip().lower() or "none"
    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
    return Settings(
        llm_provider=provider,
        llm_model=os.environ.get("LLM_MODEL", "").strip() or DEFAULT_MODELS.get(provider, ""),
        llm_effort=os.environ.get("LLM_EFFORT", "low"),
        llm_max_tokens=_int("LLM_MAX_TOKENS", 4096),
        llm_call_timeout_s=_float("LLM_CALL_TIMEOUT_S", 60.0),
        max_iterations=_int("MAX_ITERATIONS", 3),
        quality_threshold=_float("QUALITY_THRESHOLD", 8.0),
        min_rubric_score=_float("MIN_RUBRIC_SCORE", 8.0),
        workflow_timeout_s=_float("WORKFLOW_TIMEOUT_S", 180.0),
        max_llm_calls_per_workflow=_int("MAX_LLM_CALLS_PER_WORKFLOW", 14),
        max_cost_per_workflow_usd=_float("MAX_COST_PER_WORKFLOW_USD", 0.50),
        max_code_chars=_int("MAX_CODE_CHARS", 6000),
        max_request_chars=_int("MAX_REQUEST_CHARS", 1000),
        max_concurrent_workflows=_int("MAX_CONCURRENT_WORKFLOWS", 3),
        rate_limit_per_ip_per_hour=_int("RATE_LIMIT_PER_IP_PER_HOUR", 5),
        quota_per_session=_int("QUOTA_PER_SESSION", 2),
        max_live_workflows_per_day=_int("MAX_LIVE_WORKFLOWS_PER_DAY", 50),
        trust_proxy=_bool("TRUST_PROXY", True),
        result_cache=_bool("RESULT_CACHE", True),
        result_cache_path=os.environ.get("RESULT_CACHE_PATH", "").strip()
        or str(PROJECT_ROOT / "backend" / "data" / "result_cache.sqlite"),
        result_cache_ttl_days=_float("RESULT_CACHE_TTL_DAYS", 30.0),
        result_cache_include_simulated=_bool("RESULT_CACHE_INCLUDE_SIMULATED", False),
        allowed_origins=origins or ["*"],
        mock_delay_scale=_float("MOCK_DELAY_SCALE", 1.0),
    )


settings = load_settings()
