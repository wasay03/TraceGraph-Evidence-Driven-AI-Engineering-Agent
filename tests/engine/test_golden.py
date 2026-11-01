import pytest
from pydantic import TypeAdapter

from tests.engine.helpers import REGISTRY, shop_graph
from tracegraph.engine import Evaluator, EdgeView, GraphSnapshot, NodeView, build_answer, compile_rpq, ir
from tracegraph.errors import Errors

QUERY = TypeAdapter(ir.Query)


@pytest.fixture(scope="module")
def ev() -> Evaluator:
    return Evaluator(shop_graph())


def keys(ev: Evaluator, result) -> set[str]:
    return {ev.graph.nodes[n].key for n in result.nodes}


def q(data: dict):
    return QUERY.validate_python(data)


def endpoint(key: str) -> dict:
    return {"op": "select", "type": "Endpoint", "where": {"key": key}}


def test_lookup_columns_of_table(ev):
    result = ev.evaluate(q({"op": "expand", "edge": "HAS_COLUMN",
                            "input": {"op": "select", "type": "Table", "where": {"key": "public.orders"}}}))
    assert {"orders.status", "orders.discount_code", "orders.total"} <= keys(ev, result)


def test_fixed_multi_hop_endpoint_writes(ev):
    result = ev.evaluate(q({"op": "reach", "input": endpoint("POST /orders"),
                            "rpq": "HANDLED_BY . (CALLS|INJECTS)* . WRITES_TO", "target_types": ["Table"]}))
    assert keys(ev, result) == {"public.orders"}
    path = [ev.graph.edges[e].type for e in result.nodes[next(iter(result.nodes))].edges]
    assert path[0] == "HANDLED_BY" and path[-1] == "WRITES_TO"


def test_constrained_reach_to_column(ev):
    result = ev.evaluate(q({"op": "reach", "input": {"op": "select", "type": "Endpoint"},
                            "rpq": "HANDLED_BY (CALLS|INJECTS)* WRITES_TO", "target_types": ["Column"]}))
    assert "orders.status" in keys(ev, result)


def test_reachability_and_hierarchy(ev):
    start = {"op": "select", "type": "Callable", "where": {"key": "app.api.create_order"}}
    result = ev.evaluate(q({"op": "reach", "input": start, "rpq": "CALLS*"}))
    assert {"app.services.calculate_total", "app.services.get_discount",
            "app.repository.OrderRepository.save"} <= keys(ev, result)
    methods = ev.evaluate(q({"op": "select", "type": "Callable"}))
    assert any(ev.graph.nodes[n].type == "Method" for n in methods.nodes)


def test_negation_is_three_valued(ev):
    untested = ev.evaluate(q({"op": "not_exists", "scope": {"op": "select", "type": "Endpoint"},
                              "rpq": "HANDLED_BY . CALLED_BY* . TESTED_BY", "target_types": ["Test"]}))
    assert {r["node"] for r in untested.rows} == set(untested.nodes)
    assert keys(ev, untested) == {"POST /orders", "POST /orders/{order_id}/refund"}
    assert {r["truth"] for r in untested.rows} <= {"TRUE", "UNKNOWN"}
    tested = ev.evaluate(q({"op": "not_exists", "rpq": "TESTED_BY", "target_types": ["Test"],
                            "scope": {"op": "select", "type": "Function", "where": {"key": "app.services.calculate_total"}}}))
    assert tested.rows == []


def test_unknown_when_region_has_holes():
    graph = GraphSnapshot(REGISTRY, 1, 1, "x")
    for i, key in ((1, "a.f"), (2, "a.g")):
        graph.add_node(NodeView(i, "Function", key, {"qualified_name": key}, "asserted"))
    graph.add_edge(EdgeView(10, "CALLS", 1, 2, {"resolution": "exact"}, "asserted"))
    scope = {"op": "select", "type": "Function", "where": {"key": "a.f"}}
    query = q({"op": "not_exists", "scope": scope, "rpq": "CALLS*", "target_types": ["Test"]})
    assert Evaluator(graph).evaluate(query).rows[0]["truth"] == "TRUE"
    graph.holes[2] = [{"kind": "untyped_receiver"}]
    result = Evaluator(graph).evaluate(query)
    assert result.rows[0]["truth"] == "UNKNOWN" and result.gaps == {(2, "untyped_receiver")}


def test_forall_callers_tested(ev):
    callers = {"op": "expand", "edge": "CALLED_BY",
               "input": {"op": "select", "type": "Function", "where": {"key": "app.services.get_discount"}}}
    result = ev.evaluate(q({"op": "forall", "scope": callers, "rpq": "TESTED_BY", "target_types": ["Test"]}))
    assert result.truth == "TRUE"


def test_aggregate_and_rank(ev):
    agg = ev.evaluate(q({"op": "aggregate", "groups": {"op": "select", "type": "Table"}, "rpq": "WRITTEN_BY",
                         "target_types": ["Callable"]}))
    top = agg.rows[0]
    assert ev.graph.nodes[top["node"]].key == "public.orders" and top["value"] == 2
    ranked = ev.evaluate(q({"op": "rank", "input": {"op": "select", "type": "Callable"}, "score": "fan_in",
                            "edges": ["CALLS"], "k": 3}))
    assert len(ranked.rows) == 3 and ranked.rows[0]["value"] >= ranked.rows[-1]["value"]


def test_paths_witness(ev):
    result = ev.evaluate(q({"op": "paths", "source": endpoint("POST /orders"), "k": 2,
                            "target": {"op": "select", "type": "Table", "where": {"key": "public.orders"}},
                            "rpq": "HANDLED_BY (CALLS|INJECTS)* WRITES_TO"}))
    assert result.truth == "TRUE" and result.rows[0]["rank"] == 0


def test_scc_detects_cycle():
    graph = GraphSnapshot(REGISTRY, 1, 1, "x")
    for i in (1, 2, 3):
        graph.add_node(NodeView(i, "Module", f"m{i}", {"qualified_name": f"m{i}", "path": f"m{i}.py"}, "asserted"))
    for eid, (s, d) in enumerate([(1, 2), (2, 1), (2, 3)], start=10):
        graph.add_edge(EdgeView(eid, "IMPORTS", s, d, {}, "asserted"))
    result = Evaluator(graph).evaluate(q({"op": "scc", "edge": "IMPORTS", "input": {"op": "select", "type": "Module"}}))
    assert result.rows == [{"component": 0, "nodes": [1, 2]}]


def test_resolve_ranks_candidates(ev):
    result = ev.evaluate(q({"op": "resolve", "text": "calculate_total", "types": ["Callable"]}))
    assert ev.graph.nodes[result.rows[0]["node"]].key == "app.services.calculate_total"


def test_type_errors():
    with pytest.raises(Errors.Domain.QueryType):
        compile_rpq("CALLS | (WRITES_TO", REGISTRY)
    with pytest.raises(Errors.Domain.QueryType):
        compile_rpq("NOT_AN_EDGE*", REGISTRY)
    with pytest.raises(Errors.Domain.QueryType):
        Evaluator(GraphSnapshot(REGISTRY, 1, 1, "x")).evaluate(q({"op": "select", "type": "Nope"}))


def test_answer_contract_has_derivations(ev):
    result = ev.evaluate(q({"op": "reach", "input": endpoint("POST /orders"),
                            "rpq": "HANDLED_BY . (CALLS|INJECTS)* . WRITES_TO", "target_types": ["Table"]}))
    answer = build_answer(ev.graph, result, "h", 100, {})
    assert answer.truth == "ROWS" and answer.rows[0]["node"]["key"] == "public.orders"
    assert answer.derivations[0].weakest_tier == "asserted"
    assert answer.derivations[0].path[0].type == "HANDLED_BY"
