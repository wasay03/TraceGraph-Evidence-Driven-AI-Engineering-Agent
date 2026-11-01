from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from tests.engine.helpers import shop_graph
from tracegraph.agent.artifacts import Claim, Plan, Report
from tracegraph.agent.claim_checker import check_claims
from tracegraph.agent.context_compiler import repo_layout, scope_sources
from tracegraph.agent.partial_report import partial_report
from tracegraph.agent.phase_runner import PhaseRunner
from tracegraph.agent.plan_rules import validate_plan
from tracegraph.agent.state import RunState
from tracegraph.agent.verification import _scope_creep
from tracegraph.constants import agent as a
from tracegraph.interfaces.llm import ILlmClient, LlmTurn
from tracegraph.sandbox.run_sandbox import SandboxWorkspace
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


class SubmitsInvalidThenValid(ILlmClient):
    """Explores until the limit, then submits an invalid artifact, then repairs it."""

    def __init__(self) -> None:
        self.calls = 0
        self.offered: list[list[str]] = []

    async def turn(self, system, messages, tools):
        self.calls += 1
        self.offered.append([t["name"] for t in tools])
        limit = a.MAX_STEPS[a.PHASE_INTAKE]
        name, args = ("get_node", {"ref": "app.services.calculate_total", "unused": self.calls})
        if self.calls == limit:
            name, args = "submit_intake", {"kind": "nonsense", "summary": "s"}
        elif self.calls > limit:
            name, args = "submit_intake", {"kind": "question", "summary": "s"}
        call = {"type": "tool_use", "id": f"t{self.calls}", "name": name, "input": args}
        return LlmTurn([call], "tool_use", 1, 1, "fake", None, [call])


async def test_rejected_submit_at_the_limit_can_be_repaired_and_is_logged(graph):
    @asynccontextmanager
    async def services():
        yield None

    logged = []

    async def events(kind, phase, payload):
        logged.append(payload)

    llm = SubmitsInvalidThenValid()
    outcome = await PhaseRunner(llm, get_tool_registry(), services, events).run(ctx(graph, a.PHASE_INTAKE), "go")
    assert outcome.artifact.kind == "question"
    assert llm.calls == a.MAX_STEPS[a.PHASE_INTAKE] + 1 and llm.offered[-1] == ["submit_intake"]
    rejected = next(p for p in logged if p.get("error") == "Rejected")
    assert rejected["tool"] == "submit_intake" and "kind" in rejected["detail"]


def test_plan_rules_check_paths_and_test_ids(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "models.py").write_text("x = 1\n")
    (tmp_path / "tests").mkdir()
    step = {"id": "s", "description": "d", "targets": ["t"], "serves": ["t"]}
    bad = Plan(steps=[{**step, "files": ["alembic/versions/", "app", "gone/x.py"]}],
               scope_files=["alembic/versions/", "app", "gone/x.py"], tests=["test_new_enum_branch", "tests/test_no.py::t"])
    problems = "\n".join(validate_plan(bad, None, tmp_path))
    assert "'alembic/versions/' is a directory" in problems and "'app' is a directory" in problems
    assert "'gone/x.py' is not in the repository" in problems
    assert "must be a pytest id" in problems and "'tests/test_no.py' neither exists" in problems
    good = Plan(steps=[{**step, "files": ["app/models.py", "tests/test_new.py"]}],
                scope_files=["app/models.py", "tests/test_new.py"], tests=["tests/test_new.py::test_x"])
    assert validate_plan(good, None, tmp_path) == []


async def test_edit_file_edits_creates_and_stays_in_scope(graph, shop_repo, tmp_path):
    sandbox = SandboxWorkspace.create(shop_repo, tmp_path / "sb", "HEAD", 1)
    state = RunState()
    context = ToolContext(1, a.PHASE_IMPLEMENT, "A4", state, graph, None, shop_repo, sandbox,
                          frozenset({"app/models.py", "app/new_mod.py"}))
    registry = get_tool_registry()
    edited = await registry.call(context, "edit_file", {"path": "app/models.py", "old_text": 'PAID = "paid"',
                                                        "new_text": 'PAID = "paid"\n    VOID = "void"'})
    assert edited.ok, edited.text
    assert 'VOID = "void"' in (sandbox.root / "app/models.py").read_text()
    created = await registry.call(context, "edit_file", {"path": "app/new_mod.py", "new_text": "X = 1"})
    assert created.ok and (sandbox.root / "app/new_mod.py").read_text() == "X = 1\n"
    assert [p["files"] for p in state.patches] == [["app/models.py"], ["app/new_mod.py"]]
    assert "a/app/models.py" in state.patches[0]["diff"]
    missing = await registry.call(context, "edit_file", {"path": "app/models.py", "old_text": "nope", "new_text": "x"})
    assert not missing.ok and "occurs 0 times" in missing.text
    outside = await registry.call(context, "edit_file", {"path": "app/services.py", "old_text": "a", "new_text": "b"})
    assert outside.error_code == "Forbidden"
    sandbox.cleanup()


def test_repo_layout_and_scope_sources(graph, tmp_path):
    layout = repo_layout(graph)
    assert "app/models.py" in layout and "Alembic head revision: 0002" in layout
    (tmp_path / "a.py").write_text("A = 1\n")
    sources = scope_sources(tmp_path, ["a.py", "b.py"])
    assert "A = 1" in sources and "new file" in sources


def _conformance_plan(**step) -> Plan:
    fields = {"id": "s1", "description": "d", "files": [], "targets": [], "serves": ["x"]} | step
    return Plan(steps=[fields], scope_files=fields["files"], tests=[], accepted_risks=[])


def test_scope_creep_allows_what_the_plan_asked_for_and_flags_the_rest(graph):
    base_keys = {"app.models.OrderStatus", "app.services.describe_status", "app.services.get_discount"}
    plan = _conformance_plan(files=["app/models.py", "tests/test_orders.py"], targets=["app.models.OrderStatus"])

    class Node:
        def __init__(self, key, file):
            self.key, self.file = key, file

    class Snapshot:
        def __init__(self, nodes):
            self.nodes = dict(enumerate(nodes))

    base = Snapshot([Node(k, "app/services.py") for k in base_keys])
    new = Snapshot([Node("app.models.OrderStatus.CANCELLED", "app/models.py"),
                    Node("tests.test_orders.test_cancelled", "tests/test_orders.py"),
                    Node("app.services.describe_status", "app/services.py"),
                    Node("app.services.brand_new", "app/services.py")])
    touched = {n.key for n in new.nodes.values()}
    assert _scope_creep(touched, set(), base, new, plan) == ["app.services.brand_new", "app.services.describe_status"]
    assert _scope_creep(touched, {"app.services.describe_status"}, base, new, plan) == ["app.services.brand_new"]


def test_partial_report_says_what_was_and_was_not_verified():
    state = RunState(patches=[{"diff": "x"}], artifacts={"intake": {}, "plan": {}}, verification={
        "rungs": [{"name": "patch_in_scope", "status": "passed"}, {"name": "lint", "status": "unavailable"},
                  {"name": "full_suite", "status": "failed"}],
        "conformance": {"obligations": {"a:x": "unmet", "b:y": "unchecked", "c:z": "met"}}})
    report = partial_report(a.PHASE_ANALYZE, "Run budget exhausted (llm_calls).", state)
    assert report["verified"] == ["patch_in_scope"] and report["failed"] == ["full_suite"]
    assert {"lint", "type_check", "targeted_tests"} <= set(report["not_verified"])
    assert report["unmet_obligations"] == ["a:x"] and report["unchecked_obligations"] == ["b:y"]
    assert report["completed_phases"] == ["intake", "plan"] and report["patches"] == 1
    assert partial_report(a.PHASE_INTAKE, "r", RunState())["verified"] == []
