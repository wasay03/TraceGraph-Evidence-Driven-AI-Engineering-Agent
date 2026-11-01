import pytest

from tests.engine.helpers import shop_graph
from tracegraph.engine import Evaluator, ir
from tracegraph.engine.datalog import RULES_DIR, stratify
from tracegraph.engine.dsl import parse_program
from tracegraph.errors import Errors
from tracegraph.impact import check_all


@pytest.fixture(scope="module")
def graph():
    return shop_graph()


def keys(graph, result) -> set[str]:
    ids = set(result.nodes) | {r["node"] for r in result.rows or [] if r.get("node") is not None}
    return {graph.nodes[i].key for i in ids}


def test_dsl_rule_with_reach_and_column_literal(graph):
    text = '''
    # Endpoints that reach a write of orders.status
    writes_status(E) :- Endpoint(E), HANDLED_BY(E, H), reach(H, F, "(CALLS|INJECTS)*", max_hops=8),
        WRITES_TO(F, C), C == column("orders.status").
    ?- writes_status(E).
    '''
    result = Evaluator(graph).evaluate(ir.Dsl(text=text))
    assert keys(graph, result) == {"POST /orders/{order_id}/refund"}
    assert result.rows[0]["derivation"].edges  # why-provenance: the joined witness path


def test_dsl_negation_is_three_valued_and_matches_the_python_invariant(graph):
    text = (RULES_DIR / "invariants" / "inv_002.tg").read_text()
    result = Evaluator(graph).evaluate(ir.Dsl(text=text))
    python = {(graph.nodes[v.node].key, v.truth) for v in check_all(graph, ["INV-002"])}
    assert {(graph.nodes[r["node"]].key, r["truth"]) for r in result.rows} == python


def test_dsl_aggregate_order_and_limit(graph):
    text = ('?- aggregate(T, count_distinct(E)) :- Endpoint(E), HANDLED_BY(E, H), reach(H, F, "CALLS*"), '
            'WRITES_TO(F, T), Table(T) order by 2 desc limit 10.')
    rows = Evaluator(graph).evaluate(ir.Dsl(text=text)).rows
    assert [(graph.nodes[r["node"]].key, r["value"]) for r in rows] == [("public.orders", 2)]


def test_dsl_errors_are_query_errors(graph):
    for bad in ["?- Endpoint(E)", "?- reach(X, Y, \"CALLS\").", "p(X) :- Endpoint(X), not p(X) scope Endpoint.",
                "?- aggregate(T, median(E)) :- Table(T).", "?- Nope(E)."]:
        with pytest.raises(Errors.Domain.QueryType):
            Evaluator(graph).evaluate(ir.Dsl(text=bad))


def test_stratification_orders_negated_predicates_first():
    program = parse_program("b(X) :- Endpoint(X), not a(X) scope Endpoint. a(X) :- Endpoint(X).")
    assert [[r.head.pred for r in stratum] for stratum in stratify(program.rules)] == [["a"], ["b"]]


def test_derive_core_pack(graph):
    result = Evaluator(graph).evaluate(ir.Derive(rule_pack="core", predicates=["endpoint_writes"]))
    pairs = {(graph.nodes[r["nodes"][0]].key, graph.nodes[r["nodes"][1]].key) for r in result.rows}
    assert ("POST /orders", "public.orders") in pairs
    untested = Evaluator(graph).evaluate(ir.Derive(rule_pack="core", predicates=["untested_writer"]))
    assert {graph.nodes[r["nodes"][0]].key for r in untested.rows} == {
        graph.nodes[v.node].key for v in check_all(graph, ["INV-002"])}
    with pytest.raises(Errors.Domain.QueryType):
        Evaluator(graph).evaluate(ir.Derive(rule_pack="../etc"))


def test_match_binds_pattern_variables(graph):
    q = ir.Match(nodes=[ir.PatternNode(var="F", type="Callable"),
                        ir.PatternNode(var="C", type="Column", where={"nullable": True})],
                 edges=[ir.PatternEdge(src="F", dst="C", rpq="ASSUMES_NOT_NULL . MAPS_TO")])
    rows = Evaluator(graph).evaluate(q).rows
    assert {(graph.nodes[r["bindings"]["F"]].key, graph.nodes[r["bindings"]["C"]].key) for r in rows} == {
        ("app.services.calculate_total", "orders.discount_code")}
    with pytest.raises(Errors.Domain.QueryType):
        Evaluator(graph).evaluate(ir.Match(nodes=[ir.PatternNode(var="F")], edges=[ir.PatternEdge(src="F", dst="G", rpq="CALLS")]))


def test_check_operator(graph):
    result = Evaluator(graph).evaluate(ir.Check(invariants=["INV-004"]))
    assert result.truth == "FALSE" and keys(graph, result) == {"tenants.name"}


def test_with_overlay_and_diff(graph):
    nullable = ir.Select(type="Column", where={"nullable": True})
    change = [{"kind": "make_column_nullable", "column": "orders.total"}]
    assert "orders.total" in keys(graph, Evaluator(graph).evaluate(ir.WithOverlay(changes=change, query=nullable)))
    assert "orders.total" not in keys(graph, Evaluator(graph).evaluate(nullable))
    rows = Evaluator(graph).evaluate(ir.Diff(query=nullable, changes=change)).rows
    assert rows == [{"change": "added", "type": "Column", "key": "orders.total"}]
    with pytest.raises(Errors.Domain.QueryType):
        Evaluator(graph).evaluate(ir.Diff(query=nullable, snapshot_a=99))


def test_why_not_reports_holes_hop_limits_and_missing_edges(graph):
    hook = ir.Reach(input=ir.Select(type="Function", where={"key": "app.reports.run_hook"}), rpq="CALLS+",
                    target_types=["Callable"])
    result = Evaluator(graph).evaluate(ir.WhyNot(query=hook, expected="app.services.describe_status"))
    assert result.truth == "UNKNOWN"
    assert {r["reason"] for r in result.rows} == {"coverage_hole", "missing_edge"}
    endpoint = ir.Select(type="Endpoint", where={"key": "POST /orders"})
    short = ir.Reach(input=endpoint, rpq="HANDLED_BY . CALLS*", target_types=["Callable"], max_hops=1)
    rows = Evaluator(graph).evaluate(ir.WhyNot(query=short, expected="app.services.calculate_total")).rows
    assert [r["reason"] for r in rows] == ["hop_limit"]
    found = ir.Reach(input=endpoint, rpq="HANDLED_BY . CALLS*", target_types=["Callable"])
    assert Evaluator(graph).evaluate(ir.WhyNot(query=found, expected="app.services.calculate_total")).truth == "TRUE"
