from app.agents import analyzer, developer, reviewer, tester
from app.agents.base import AgentSpec

AGENTS: dict[str, AgentSpec] = {
    "analyzer": analyzer.SPEC,
    "developer": developer.SPEC,
    "tester": tester.SPEC,
    "reviewer": reviewer.SPEC,
}

ORCHESTRATOR_INFO = {
    "id": "orchestrator",
    "name": "Orchestrator",
    "role": "Planning, routing & supervision",
    "objective": "Classify the mission, select and sequence agents, react to their results and decide when the work is done.",
    "responsibilities": [
        "Classify the request", "Select agents and decompose tasks", "Run independent agents in parallel",
        "Route on results (retry, rework, complete)", "Enforce iteration, time and budget limits",
    ],
}
