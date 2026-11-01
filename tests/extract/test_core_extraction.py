from collections import Counter
from pathlib import Path

from tests.conftest import SHOP_FIXTURE
from tracegraph.extract import ModuleFingerprint, dirty_scope, run_extraction
from tracegraph.ontology import get_registry

REGISTRY = get_registry()
NODE_NAMES = {t.id: t.name for t in REGISTRY.node_types}
EDGE_NAMES = {t.id: t.name for t in REGISTRY.edge_types}


def _extract(root: Path = SHOP_FIXTURE):
    return run_extraction(REGISTRY, root, 1, "file:///shop", "c0ffee")


def _edges(payload, kind: str) -> set[tuple[str, str]]:
    keys = {n["id"]: n["natural_key"] for n in payload.nodes}
    return {(keys[e["src"]], keys[e["dst"]]) for e in payload.edges if EDGE_NAMES[e["type_id"]] == kind}


def test_structure_nodes():
    payload = _extract().payload
    by_key = {(NODE_NAMES[n["type_id"]], n["natural_key"]) for n in payload.nodes}
    assert ("Module", "app.services") in by_key
    assert ("Method", "app.services.OrderService.create_order") in by_key
    assert ("Function", "app.services.calculate_total") in by_key
    assert ("Parameter", "app.services.calculate_total#0") in by_key
    assert ("Attribute", "app.models.Order.discount_code") in by_key
    assert ("EnumMember", "app.models.OrderStatus.PAID") in by_key
    assert ("Attribute", "app.services.OrderService.repository") in by_key


def test_resolution_edges():
    payload = _extract().payload
    calls = _edges(payload, "CALLS")
    assert ("app.services.calculate_total", "app.services.get_discount") in calls
    assert ("app.services.OrderService.create_order", "app.services.calculate_total") in calls
    # self.repository is typed through the annotated __init__ parameter
    assert ("app.services.OrderService.create_order", "app.repository.OrderRepository.save") in calls
    assert ("app.api.create_order", "app.services.OrderService.create_order") in calls
    assert ("app.services.OrderService", "app.models.Order") not in calls
    assert ("app.repository.OrderRepository", "app.repository.Repository") in _edges(payload, "INHERITS")
    assert ("app.repository.OrderRepository.save", "app.repository.Repository.save") in _edges(payload, "OVERRIDES")
    assert ("app.services.OrderService.refund", "app.services.RefundError") in _edges(payload, "RAISES")
    assert ("app.api.refund_order", "app.services.RefundError") in _edges(payload, "CATCHES")
    assert ("app.services.calculate_total", "app.models.Order.discount_code") in _edges(payload, "READS_ATTR")
    assert ("app.api", "app.services.OrderService") in _edges(payload, "IMPORTS")
    assert ("app.services.OrderService.create_order", "app.models.Order") in _edges(payload, "INSTANTIATES")


def test_dispatch_candidates_and_holes():
    payload = _extract().payload
    holes = Counter(h["kind"] for h in payload.holes)
    assert holes["dynamic_attribute"] == 1
    resolutions = {e["props"]["resolution"] for e in payload.edges if EDGE_NAMES[e["type_id"]] == "CALLS"}
    assert "exact" in resolutions


def test_every_edge_has_evidence_with_span():
    payload = _extract().payload
    linked = {link["edge_id"] for link in payload.links}
    assert all(e["id"] in linked for e in payload.edges)
    assert all(ev["span_lo"] is not None for ev in payload.evidence)


def test_extraction_is_deterministic():
    a, b = _extract().payload, _extract().payload
    assert [n["id"] for n in a.nodes] == [n["id"] for n in b.nodes]
    assert sorted(e["id"] for e in a.edges) == sorted(e["id"] for e in b.edges)


def test_dirty_scope_adds_importers_on_signature_change():
    prev = {"a.py": ModuleFingerprint("1", "s1"), "b.py": ModuleFingerprint("2", "s2"), "c.py": ModuleFingerprint("3", "s")}
    body_only = {**prev, "a.py": ModuleFingerprint("1x", "s1")}
    api_change = {**prev, "a.py": ModuleFingerprint("1x", "s1x")}
    importers = {"a.py": {"b.py"}}
    assert dirty_scope(prev, body_only, importers) == ["a.py"]
    assert dirty_scope(prev, api_change, importers) == ["a.py", "b.py"]
    assert dirty_scope(prev, {k: v for k, v in prev.items() if k != "c.py"}, importers) == ["c.py"]
