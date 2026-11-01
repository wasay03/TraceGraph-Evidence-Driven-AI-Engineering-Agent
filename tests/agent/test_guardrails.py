from pathlib import Path

import pytest

from tests.engine.helpers import shop_graph
from tracegraph.agent.artifacts import Claim, Report
from tracegraph.agent.claim_checker import check_claims
from tracegraph.agent.state import RunState
from tracegraph.constants import agent as a
from tracegraph.tools import ToolContext, get_tool_registry


@pytest.fixture(scope="module")
def graph():
    return shop_graph()


def ctx(graph, phase: str, config: str = "A4", state: RunState | None = None) -> ToolContext:
    return ToolContext(1, phase, config, state or RunState(), graph, None, Path("."))


async def test_phase_and_config_gating(graph):
    registry = get_tool_registry()
    refused = await registry.call(ctx(graph, a.PHASE_IMPLEMENT), "simulate_change", {"changes": [{}]})
    assert refused.error_code == "PhaseViolation"
    hidden = await registry.call(ctx(graph, a.PHASE_DISCOVER, "B0"), "get_callers", {"ref": "x"})
    assert hidden.error_code == "UnknownTool"
    assert "simulate_change" not in {t["name"] for t in registry.definitions(a.PHASE_ANALYZE, "A3")}


async def test_loop_detection_and_validation(graph):
    registry, context = get_tool_registry(), ctx(graph, a.PHASE_DISCOVER)
    for _ in range(a.MAX_REPEATED_CALLS):
        first = await registry.call(context, "get_node", {"ref": "app.services.calculate_total"})
        assert first.ok
    again = await registry.call(context, "get_node", {"ref": "app.services.calculate_total"})
    assert again.error_code == "LoopDetected"
    invalid = await registry.call(context, "get_node", {"reference": "x"})
    assert invalid.error_code == "InvalidInput"
    ambiguous = await registry.call(context, "get_node", {"ref": "calculate"})
    assert not ambiguous.ok and "app.services.calculate_total" in ambiguous.text


async def test_budget_exhaustion(graph):
    state = RunState()
    state.budget.tool_calls = a.MAX_TOOL_CALLS
    refused = await get_tool_registry().call(ctx(graph, a.PHASE_DISCOVER, state=state), "describe_ontology", {})
    assert refused.error_code == "BudgetExceeded"


async def test_claims_must_cite_handles_from_the_run():
    report = Report(summary="s", claims=[Claim(text="a", handle="ans_" + "0" * 32, truth="TRUE"),
                                         Claim(text="b", handle="ans_" + "1" * 32, truth="FALSE")])

    async def truth_of(handle: str) -> str | None:
        return "TRUE"

    problems = await check_claims(report, ["ans_" + "1" * 32], truth_of)
    assert len(problems) == 2
    assert "no tool returned" in problems[0] and "has truth TRUE" in problems[1]


def test_llm_call_cap_exhausts_the_budget():
    state = RunState()
    state.budget.llm_calls = state.budget.max_llm_calls
    assert state.budget.exhausted() == "llm_calls"
