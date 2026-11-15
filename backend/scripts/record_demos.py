"""Record the Guided Demo workflows.

Runs each scenario through the real LangGraph engine and saves the full event
stream to demo/scenarios/<id>.json (and a copy for the frontend bundle).

    uv run python scripts/record_demos.py            # scripted model (offline, default)
    uv run python scripts/record_demos.py --live     # configured LLM provider (costs tokens)

Recordings made with the scripted model are flagged ``simulated: true`` and
the UI says so.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import PROJECT_ROOT, settings  # noqa: E402
from app.orchestration.events import WorkflowRun  # noqa: E402
from app.scenarios import SCENARIO_ORDER, SCENARIOS  # noqa: E402
from app.services import runner  # noqa: E402
from app.services.llm import ScriptedProvider, make_provider  # noqa: E402

OUT_DIRS = [PROJECT_ROOT / "demo" / "scenarios", PROJECT_ROOT / "frontend" / "src" / "data" / "recordings"]


async def record(scenario_id: str, live: bool) -> dict:
    sc = SCENARIOS[scenario_id]
    if live:
        provider = make_provider(settings, None)
        cfg = settings
    else:
        provider = ScriptedProvider(copy.deepcopy(sc["script"]), delay_scale=1.0)
        cfg = replace(settings, llm_provider="mock")
    run = WorkflowRun(mode="demo-recording", provider=provider.name, model=provider.model,
                      simulated=provider.simulated, workflow_id=f"demo_{scenario_id}")
    await runner.execute(run, provider, cfg, code=sc["code"], request=sc["request"],
                         task_hint=sc["task_type"], scenario_id=scenario_id)
    meta = {k: v for k, v in sc.items() if k != "script"}
    return {
        "scenario": meta,
        "recording": {
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "engine": "LangGraph (backend/app/orchestration/graph.py)",
            "provider": provider.name,
            "model": provider.model,
            "simulated": provider.simulated,
            "status": run.status,
            "duration_s": run.events[-1]["t"] if run.events else 0,
        },
        "events": run.events,
    }


def export_topology() -> None:
    """Write the compiled graph's topology for the frontend (the Guided Demo has no backend)."""
    from app.orchestration.graph import topology

    path = PROJECT_ROOT / "frontend" / "src" / "data" / "langgraph.json"
    path.write_text(json.dumps(topology(), indent=1) + "\n", encoding="utf-8")
    print(f"topology -> {path.relative_to(PROJECT_ROOT)}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="use the configured LLM provider")
    args = parser.parse_args()
    for d in OUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    export_topology()
    for scenario_id in SCENARIO_ORDER:
        data = await record(scenario_id, args.live)
        for d in OUT_DIRS:
            (d / f"{scenario_id}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{scenario_id}: {data['recording']['status']} in {data['recording']['duration_s']}s, "
              f"{len(data['events'])} events")


if __name__ == "__main__":
    asyncio.run(main())
