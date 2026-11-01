import difflib
from pathlib import Path

from httpx import AsyncClient

from tests.agent.scripted_llm import ScriptedLlm, handles, issued_handles, patches
from tests.api.test_indexing_e2e import _index
from tracegraph.config import Settings
from tracegraph.core import Database
from tracegraph.engine import SnapshotCache
from tracegraph.schemas.runs import RunCreateRequest
from tracegraph.services.agent_executor import AgentExecutor

MODELS = "app/models.py"
MIGRATION = "migrations/versions/0003_cancelled.py"
TESTS = "tests/test_orders.py"
NEW_MIGRATION = '''import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.alter_column("orders", "status", type_=sa.String(20))


def downgrade() -> None:
    op.alter_column("orders", "status", type_=sa.String(20))
'''
NEW_TEST = '''

def test_cancelled_status() -> None:
    assert OrderStatus("cancelled") is OrderStatus.CANCELLED
'''


def unified(path: str, before: str, after: str) -> str:
    old = before.splitlines(keepends=True)
    diff = difflib.unified_diff(old, after.splitlines(keepends=True),
                                "/dev/null" if not before else f"a/{path}", f"b/{path}")
    return "".join(diff)


def script(repo: Path) -> dict:
    models = (repo / MODELS).read_text()
    tests = (repo / TESTS).read_text()
    models_diff = unified(MODELS, models, models.replace('    REFUNDED = "refunded"\n',
                                                         '    REFUNDED = "refunded"\n    CANCELLED = "cancelled"\n'))
    tests_after = tests.replace("from app.models import Order\n", "from app.models import Order, OrderStatus\n") + NEW_TEST
    plan = {
        "steps": [
            {"id": "s1", "description": "add the enum member", "files": [MODELS],
             "targets": ["app.models.OrderStatus", "app.models.OrderStatus.CANCELLED"], "serves": ["app.models.OrderStatus"]},
            {"id": "s2", "description": "migration for the enum column", "files": [MIGRATION],
             "targets": ["0003"], "serves": ["migration_alter_enum_type"]},
            {"id": "s3", "description": "test the new branch", "files": [TESTS],
             "targets": ["tests.test_orders.test_cancelled_status"], "serves": ["test_new_enum_branch"]},
        ],
        "scope_files": [MODELS, MIGRATION, TESTS],
        "tests": ["tests/test_orders.py::test_cancelled_status"],
    }
    incomplete = {**plan, "steps": plan["steps"][:1] + plan["steps"][2:], "scope_files": [MODELS, TESTS]}
    change = [{"kind": "add_enum_member", "enum": "app.models.OrderStatus", "member": "CANCELLED", "value": "cancelled"}]
    return {
        "intake": [
            lambda m: [("resolve_entity", {"text": "OrderStatus", "types": ["Class"]})],
            lambda m: [("submit_intake", {"kind": "change", "summary": "add a CANCELLED order status",
                                          "entities": ["app.models.OrderStatus"]})],
        ],
        "discover": [
            lambda m: [("tests_for", {"refs": ["app.models.OrderStatus"]}),
                       ("get_node", {"ref": "app.models.OrderStatus"})],
            lambda m: [("submit_context", {"node_keys": ["app.models.OrderStatus"], "handles": handles(m)})],
        ],
        "analyze": [
            lambda m: [("simulate_change", {"changes": change})],
            lambda m: [("submit_analysis", {"change_specs": change, "impact_handle": handles(m)[-1]})],
        ],
        "plan": [
            lambda m: [("submit_plan", incomplete)],
            lambda m: [("submit_plan", plan)],
        ],
        "implement": [
            lambda m: [("read_file", {"path": MODELS}),
                       ("apply_patch", {"diff": unified("app/services.py", "x\n", "y\n")})],
            lambda m: [("apply_patch", {"diff": models_diff, "step_id": "s1"}),
                       ("apply_patch", {"diff": unified(MIGRATION, "", NEW_MIGRATION), "step_id": "s2"}),
                       ("apply_patch", {"diff": unified(TESTS, tests, tests_after), "step_id": "s3"})],
            lambda m: [("submit_patchset", {"patch_ids": patches(m), "steps_done": ["s1", "s2", "s3"]})],
        ],
        "report": [
            lambda m: [("submit_report", {"summary": "Added CANCELLED with a migration and a test.", "claims": [
                {"text": "All branch sites over OrderStatus have a default path.", "handle": issued_handles(m)[2],
                 "truth": "ROWS"},
                {"text": "OrderStatus resolved to the enum class.", "handle": issued_handles(m)[0]},
            ]})],
        ],
    }



async def test_benchmark_run_end_to_end(client: AsyncClient, auth_headers, settings: Settings, shop_repo: Path,
                                        tmp_path: Path):
    repo = (await client.post("/repos", json={"url": str(shop_repo)}, headers=auth_headers)).json()
    await _index(client, auth_headers, settings, repo["id"], "full")
    run_settings = settings.model_copy(update={"sandbox_dir": str(tmp_path / "sandboxes")})
    database = Database(run_settings)
    llm = ScriptedLlm(script(shop_repo))
    executor = AgentExecutor(database, run_settings, SnapshotCache(), lambda: llm)
    try:
        async with executor.services() as services:
            run = await services.agent.start(RunCreateRequest(repo_id=repo["id"], request="Add a CANCELLED order status",
                                                              mode="benchmark", config="A4"))
        status = await executor.execute(run.id)
        async with executor.services() as services:
            result = await services.agent.get(run.id)
    finally:
        await database.dispose()

    state = result.state
    assert status == "completed", state.get("error")
    assert state["phase_history"] == ["intake", "discover", "analyze", "plan", "approval", "implement", "verify", "report"]
    tool_events = [e.payload for e in result.events if e.kind == "tool_call"]
    scope_refusal = next(e for e in tool_events if e["tool"] == "apply_patch" and not e["ok"])
    assert scope_refusal["error"] == "Forbidden"
    verification = state["verification"]
    assert verification["passed"], verification
    rungs = {r["name"]: r["status"] for r in verification["rungs"]}
    assert rungs["targeted_tests"] == "passed" and rungs["full_suite"] == "passed"
    assert verification["conformance"]["scope_creep"] == []
    assert verification["conformance"]["obligations"]["migration_alter_enum_type:orders.status"] == "met"
    assert "app.models.OrderStatus.CANCELLED" in verification["conformance"]["changed_symbols"]
    assert len(state["artifacts"]["report"]["claims"]) == 2
    plan_rejection = next(m for m in llm.results if "migration_alter_enum_type on orders.status has no step" in m)
    assert plan_rejection.startswith("Rejected")

