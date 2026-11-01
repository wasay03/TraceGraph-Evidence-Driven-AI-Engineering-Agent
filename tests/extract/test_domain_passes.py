from collections import Counter

import pytest

from tests.conftest import SHOP_FIXTURE
from tracegraph.extract import run_extraction
from tracegraph.ontology import get_registry

REGISTRY = get_registry()
EDGE_NAMES = {t.id: t.name for t in REGISTRY.edge_types}


@pytest.fixture(scope="module")
def graph():
    payload = run_extraction(REGISTRY, SHOP_FIXTURE, 1, "file:///shop", "c0ffee").payload
    nodes = {n["id"]: n for n in payload.nodes}
    edges = {}
    for e in payload.edges:
        edges.setdefault(EDGE_NAMES[e["type_id"]], []).append(
            (nodes[e["src"]]["natural_key"], nodes[e["dst"]]["natural_key"], e["props"]))
    by_key = {n["natural_key"]: n for n in payload.nodes}
    return payload, by_key, edges


def _pairs(edges, kind):
    return {(s, d) for s, d, _ in edges.get(kind, [])}


def test_fastapi_endpoints(graph):
    _, nodes, edges = graph
    assert nodes["POST /orders"]["props"]["status_codes"] == [201]
    assert ("POST /orders", "app.api.create_order") in _pairs(edges, "HANDLED_BY")
    assert ("POST /orders", "app.schemas.OrderOut") in _pairs(edges, "RESPONDS_WITH")
    assert ("POST /orders", "app.schemas.OrderIn") in _pairs(edges, "ACCEPTS")
    assert ("app.api.get_order_service", "app.db.get_session") in _pairs(edges, "INJECTS")


def test_orm_mapping_and_nullability(graph):
    _, nodes, edges = graph
    assert nodes["orders.discount_code"]["props"]["nullable"] is True
    assert nodes["orders.status"]["props"]["nullable"] is False
    assert nodes["orders.id"]["props"]["is_pk"] is True
    assert ("app.models.Order.status", "orders.status") in _pairs(edges, "MAPS_TO")
    fk = {(s, d): p for s, d, p in edges["REFERENCES_FK"]}
    assert fk[("invoices.order_id", "orders.id")] == {"on_delete": "CASCADE"}


def test_query_sites(graph):
    _, _, edges = graph
    assert ("app.repository.OrderRepository.mark_refunded", "orders.status") in _pairs(edges, "WRITES_TO")
    assert ("app/repository.py:24", "orders.tenant_id") in _pairs(edges, "FILTERS_ON")
    assert ("app.repository.OrderRepository.get", "public.orders") in _pairs(edges, "READS_FROM")
    assert ("app/reports.py:6", "orders.status") in _pairs(edges, "FILTERS_ON")


def test_schema_replay_and_drift(graph):
    _, nodes, edges = graph
    name = nodes["tenants.name"]["props"]
    assert name["nullable"] is False and name["db_nullable"] is True  # seeded ORM/DB drift
    assert nodes["orders.discount_code"]["props"]["in_db"] is True
    assert ("0001", "0002") in _pairs(edges, "PRECEDES")
    assert ("0002", "orders.discount_code") in _pairs(edges, "MIGRATES")


def test_local_facts(graph):
    _, nodes, edges = graph
    not_null = {(s, d): p for s, d, p in edges["ASSUMES_NOT_NULL"]}
    assert not_null[("app.services.calculate_total", "app.models.Order.discount_code")] == {
        "guard_kind": "call_on_value"}
    assert all(not d.endswith((".session", ".repository")) for _, d in not_null)
    branches = {(s, d): p for s, d, p in edges["BRANCHES_ON"]}
    status = branches[("app.services.describe_status", "app.models.Order.status")]
    assert status == {"compared_values": ["PAID", "PENDING"], "has_default": True}
    assert ("app.services.describe_status", "app.models.OrderStatus.PAID") in branches
    assert nodes["app.services.get_discount"]["props"]["returns_none"] == "some_paths"
    assert nodes["app.services.describe_status"]["props"]["returns_none"] == "never"
    assert ("app.schemas.OrderIn.total_positive", "app.schemas.OrderIn.total") in _pairs(edges, "VALIDATES")


def test_tests_pass(graph):
    _, nodes, edges = graph
    test_id = "tests/test_orders.py::test_known_discounts"
    assert nodes[test_id]["props"]["is_parametrized"] is True
    tests = {(s, d): p for s, d, p in edges["TESTS"]}
    assert tests[(test_id, "app.services.get_discount")]["method"] == "call"
    via_fixture = tests[("tests/test_orders.py::test_calculate_total_applies_discount", "app.models.Order")]
    assert via_fixture["strength"] == 0.8
    assert ("tests/test_orders.py::test_calculate_total_applies_discount", "tests.conftest.order") in _pairs(
        edges, "USES_FIXTURE")


def test_dynamic_sql_hole(graph):
    payload, _, _ = graph
    assert Counter(h["kind"] for h in payload.holes)["dynamic_sql"] == 1


def test_constructor_keywords_and_unary_and_required_field_facts(graph):
    _, _, edges = graph
    assert ("app.services.OrderService.create_order", "app.models.Order.discount_code") in _pairs(edges, "WRITES_ATTR")
    not_null = {(s, d): p for s, d, p in edges["ASSUMES_NOT_NULL"]}
    assert not_null[("app.services.OrderService.refund", "app.models.Order.total")]["guard_kind"] == "arithmetic"
    assert not_null[("app.api.create_order", "app.models.Order.total")]["guard_kind"] == "required_field"


def test_include_router_prefix_is_applied(tmp_path):
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "__init__.py").write_text("")
    (tmp_path / "svc" / "routes.py").write_text(
        'from fastapi import APIRouter\nrouter = APIRouter(prefix="/items")\n\n@router.get("/{i}")\ndef read(i: int) -> int:\n    return i\n')
    (tmp_path / "svc" / "main.py").write_text(
        'from fastapi import FastAPI\nfrom svc.routes import router\napp = FastAPI()\napp.include_router(router, prefix="/api")\n')
    keys = {n["natural_key"] for n in run_extraction(REGISTRY, tmp_path, 1, "file:///x", "c").payload.nodes}
    assert "GET /api/items/{i}" in keys
