import pytest

from tests.engine.helpers import shop_graph
from tracegraph.errors import Errors
from tracegraph.impact import ImpactAnalyzer, check_all
from tracegraph.impact import changespec as cs


@pytest.fixture(scope="module")
def graph():
    return shop_graph()


def classes(graph, result) -> dict[str, str]:
    return {graph.nodes[f.node].key: f.cls for f in result.findings if f.node in graph.nodes}


def test_make_column_nullable(graph):
    result = ImpactAnalyzer(graph).analyze([cs.MakeColumnNullable(column="orders.discount_code")])
    found = classes(graph, result)
    assert found["app.services.calculate_total"] == "BREAKS"
    assert found["app.reports.count_rows"] == "UNKNOWN"  # dynamic SQL hole, never a confident FALSE
    assert found["POST /orders"] == "AT_RISK"
    assert {o.kind for o in result.obligations} == {"migration_alter_nullable", "orm_attribute_optional"}
    assert "tests/test_orders.py::test_calculate_total_applies_discount" == graph.nodes[result.tests[0].node].key
    assert any(d.violation.invariant == "INV-001" and d.status == "new" for d in result.invariants)
    breaks = next(f for f in result.findings if f.cls == "BREAKS")
    assert [graph.edges[e].type for e in breaks.derivation.edges] == ["MAPS_TO", "ASSUMES_NOT_NULL"]


def test_nullable_change_creates_drift_violation(graph):
    result = ImpactAnalyzer(graph).analyze([cs.MakeColumnNullable(column="orders.total")])
    assert any(d.violation.invariant == "INV-004" and d.status == "new" for d in result.invariants)
    assert "orders.total" not in {graph.nodes[v.node].key for v in check_all(graph, ["INV-004"])}


def test_add_enum_member(graph):
    result = ImpactAnalyzer(graph).analyze([cs.AddEnumMember(enum="app.models.OrderStatus", member="CANCELLED")])
    assert classes(graph, result)["app.services.describe_status"] == "GUARDED"
    assert "migration_alter_enum_type" in {o.kind for o in result.obligations}
    with pytest.raises(Errors.Domain.ChangeSpec):
        ImpactAnalyzer(graph).analyze([cs.AddEnumMember(enum="app.models.Order", member="X")])


def test_change_return_type_to_optional(graph):
    result = ImpactAnalyzer(graph).analyze([cs.ChangeReturnType(function="app.services.calculate_total",
                                                                new_type="int | None")])
    found = classes(graph, result)
    assert found["app.services.OrderService.create_order"] == "BREAKS"
    guarded = ImpactAnalyzer(graph).analyze([cs.ChangeReturnType(function="app.repository.OrderRepository.get",
                                                                 new_type="Order | None")])
    assert classes(graph, guarded)["app.services.OrderService.refund"] == "GUARDED"


def test_change_signature(graph):
    required = ImpactAnalyzer(graph).analyze([cs.ChangeSignature(function="app.services.get_discount",
                                                                 add=[cs.ParamChange(name="tenant_id")])])
    assert classes(graph, required)["app.services.calculate_total"] == "BREAKS"
    optional = ImpactAnalyzer(graph).analyze([cs.ChangeSignature(function="app.services.get_discount",
                                                                 add=[cs.ParamChange(name="tenant_id", has_default=True)])])
    assert classes(graph, optional)["app.services.calculate_total"] == "GUARDED"


def test_remove_symbol_and_invariant_resolution(graph):
    result = ImpactAnalyzer(graph).analyze([cs.RemoveSymbol(symbol="app.repository.OrderRepository.mark_refunded")])
    assert classes(graph, result)["app.services.OrderService.refund"] == "BREAKS"
    assert any(d.status == "resolved" and d.violation.invariant == "INV-002" for d in result.invariants)
    assert "app.repository.OrderRepository.mark_refunded" in {n.key for n in graph.nodes.values()}


def test_unknown_target_is_rejected(graph):
    with pytest.raises(Errors.Domain.ChangeSpec):
        ImpactAnalyzer(graph).analyze([cs.MakeColumnNullable(column="orders.nope")])


def test_seeded_invariant_violations(graph):
    found = {(v.invariant, graph.nodes[v.node].key) for v in check_all(graph)}
    assert ("INV-004", "tenants.name") in found
    assert ("INV-007", "app.api") in found
    assert ("INV-003", "app/repository.py:21") in found
    assert ("INV-003", "app/repository.py:24") not in found  # list_paid filters on tenant_id
    assert not any(inv == "INV-006" for inv, _ in found)  # RefundError is caught by the handler


def test_rename_symbol_breaks_references(graph):
    result = ImpactAnalyzer(graph).analyze([cs.RenameSymbol(symbol="app.services.get_discount", new_name="lookup")])
    found = classes(graph, result)
    assert found["app.services.calculate_total"] == "BREAKS" and found["tests.test_orders"] == "BREAKS"
    assert {o.kind for o in result.obligations} == {"update_references"}


def test_add_column_required_breaks_constructors_optional_does_not(graph):
    required = ImpactAnalyzer(graph).analyze([cs.AddColumn(table="public.orders", name="region", sql_type="VARCHAR",
                                                           nullable=False)])
    assert classes(graph, required)["app.services.OrderService.create_order"] == "BREAKS"
    assert {"migration_add_column", "orm_mapped_attribute"} <= {o.kind for o in required.obligations}
    optional = ImpactAnalyzer(graph).analyze([cs.AddColumn(table="public.orders", name="region", sql_type="VARCHAR")])
    assert classes(graph, optional)["app.services.OrderService.create_order"] == "AT_RISK"


def test_change_column_type_breaks_arithmetic_only_when_no_longer_numeric(graph):
    text = ImpactAnalyzer(graph).analyze([cs.ChangeColumnType(column="orders.total", new_type="VARCHAR")])
    found = classes(graph, text)
    assert found["app.services.calculate_total"] == "BREAKS" and found["app.services.OrderService.refund"] == "BREAKS"
    numeric = ImpactAnalyzer(graph).analyze([cs.ChangeColumnType(column="orders.total", new_type="NUMERIC(10,2)")])
    assert classes(graph, numeric)["app.services.calculate_total"] == "AT_RISK"


def test_add_raise_stops_at_catchers_and_breaks_uncaught_endpoints(graph):
    uncaught = ImpactAnalyzer(graph).analyze([cs.AddRaise(function="app.services.get_discount", exception="ValueError")])
    assert classes(graph, uncaught)["POST /orders"] == "BREAKS"
    caught = ImpactAnalyzer(graph).analyze([cs.AddRaise(function="app.repository.OrderRepository.mark_refunded",
                                                        exception="app.services.RefundError")])
    found = classes(graph, caught)
    assert found["app.api.refund_order"] == "GUARDED"
    assert found.get("POST /orders/{order_id}/refund") != "BREAKS"


def test_change_endpoint_contract(graph):
    result = ImpactAnalyzer(graph).analyze([cs.ChangeEndpointContract(endpoint="POST /orders", new_response="adds currency")])
    assert classes(graph, result)["app.api.create_order"] == "AT_RISK"
    assert "review_response_model" in {o.kind for o in result.obligations}


def test_dynamic_getattr_on_the_module_is_unknown_for_callable_changes(graph):
    result = ImpactAnalyzer(graph).analyze([cs.RemoveSymbol(symbol="app.services.describe_status")])
    assert classes(graph, result)["app.reports.run_hook"] == "UNKNOWN"
    other = ImpactAnalyzer(graph).analyze([cs.RemoveSymbol(symbol="app.repository.OrderRepository.mark_refunded")])
    assert "app.reports.run_hook" not in classes(graph, other)
