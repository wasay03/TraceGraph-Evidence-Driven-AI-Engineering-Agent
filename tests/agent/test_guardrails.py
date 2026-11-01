from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from tests.engine.helpers import shop_graph
from tracegraph.agent.artifacts import Claim, Report
from tracegraph.agent.claim_checker import check_claims
from tracegraph.agent.phase_runner import PhaseRunner
from tracegraph.agent.state import RunState
from tracegraph.constants import agent as a
from tracegraph.interfaces.llm import ILlmClient, LlmTurn
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


class RecordingLlm(ILlmClient):
    """Keeps calling a harmless tool; records which tools each turn offered."""

    def __init__(self) -> None:
        self.offered: list[list[str]] = []
        self.last_messages: list = []

    async def turn(self, system, messages, tools):
        self.offered.append([t["name"] for t in tools])
        self.last_messages = messages
        step = len(self.offered)
        name, args = ("submit_intake", {"kind": "question", "summary": "s"}) if step == a.MAX_STEPS[a.PHASE_INTAKE] else (
            "get_node", {"ref": "app.services.calculate_total", "unused": step})
        call = {"type": "tool_use", "id": f"t{step}", "name": name, "input": args}
        return LlmTurn([call], "tool_use", 1, 1, "fake", None, [call])


async def test_last_step_offers_only_submit_and_reports_steps_left(graph):
    @asynccontextmanager
    async def services():
        yield None

    async def events(kind, phase, payload):
        return None

    llm = RecordingLlm()
    runner = PhaseRunner(llm, get_tool_registry(), services, events)
    outcome = await runner.run(ctx(graph, a.PHASE_INTAKE), "go")
    assert outcome.artifact.kind == "question"
    assert len(llm.offered[0]) > 1 and llm.offered[-1] == ["submit_intake"]
    notes = [b["text"] for m in llm.last_messages if m["role"] == "user" and isinstance(m["content"], list)
             for b in m["content"] if b["type"] == "text"]
    assert notes[0] == "Steps left in this phase: 2." and notes[-1].startswith("This is the final step")


def test_plan_phase_offers_no_exploration_tools():
    names = {t["name"] for t in get_tool_registry().definitions(a.PHASE_PLAN, "A4")}
    assert names <= {"get_source", "get_evidence", "read_file", "tests_for"}
    described = next(t for t in get_tool_registry().definitions(a.PHASE_ANALYZE, "A4") if t["name"] == "simulate_change")
    assert '"member": "NAME"' in described["description"]
