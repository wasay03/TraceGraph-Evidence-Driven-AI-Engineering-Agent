from pathlib import Path

import pytest

from tests.agent.scripted_llm import ScriptedLlm
from tests.agent.test_agent_run import script
from tests.conftest import SHOP_FIXTURE
from tracegraph.bench import (
    bootstrap_ci,
    load_suite,
    ndcg_at_k,
    prf,
    render_markdown,
    run_agent_benchmark,
    run_impact_benchmark,
    wilcoxon_signed_rank,
)
from tracegraph.config import Settings

SUITE = Path(__file__).resolve().parents[2] / "bench" / "suites" / "seeded.yaml"


def test_metrics():
    assert prf({"a", "b"}, {"b", "c"}) == {"precision": 0.5, "recall": 0.5, "f1": 0.5}
    assert prf(set(), set())["f1"] == 1.0
    assert ndcg_at_k(["x", "a"], {"a": 1.0}) < ndcg_at_k(["a", "x"], {"a": 1.0}) == 1.0
    mean, low, high = bootstrap_ci([0.0, 1.0, 1.0, 1.0])
    assert mean == 0.75 and low <= mean <= high
    assert wilcoxon_signed_rank([0, 0, 0, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1, 1, 1])["p_value"] < 0.05
    assert wilcoxon_signed_rank([1, 2], [1, 2])["n"] == 0
    with pytest.raises(ValueError):
        wilcoxon_signed_rank([1], [1, 2])


def test_impact_benchmark_on_seeded_suite():
    result = run_impact_benchmark(load_suite(SUITE))
    rows = {(r["task"], r["predictor"]): r for r in result["rows"]}
    assert rows[("tenant_name_nullable", "tracegraph")]["holes_reported"] is True
    assert rows[("tenant_name_nullable", "grep_baseline")]["holes_reported"] is False
    assert rows[("discount_code_nullable", "tracegraph")]["breaks_recall"] == 1.0
    # Known extraction gaps stay visible: the unary minus in refund is not a dereference fact.
    assert "app.services.OrderService.refund" not in rows[("total_nullable", "tracegraph")]["missed"]
    assert rows[("total_nullable", "tracegraph")]["breaks_recall"] < 1.0
    summary = result["summary"]
    assert summary["tracegraph"]["f1"][0] > summary["grep_baseline"]["f1"][0]
    assert "| metric |" in render_markdown(result)


async def test_agent_benchmark_plumbing(settings: Settings, migrated_db: str, tmp_path: Path):
    result = await run_agent_benchmark(load_suite(SUITE), ["A4"], 1, settings,
                                       lambda: ScriptedLlm(script(SHOP_FIXTURE)), task_ids=["status_cancelled"])
    row = result["rows"][0]
    assert row["status"] == "completed" and row["success"] is True, row
    assert row["scope_precision"] < 1.0 and row["scope_recall"] == 1.0  # gold fix touches only app/models.py
    assert result["summary"]["A4"]["success"][0] == 1.0
