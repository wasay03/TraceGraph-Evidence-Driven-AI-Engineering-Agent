import pytest

from tracegraph.errors import Errors
from tracegraph.ontology import get_registry, natural_key_of, to_catalog, validate_edge, validate_node


def test_hierarchy_and_subtypes():
    r = get_registry()
    assert r.ancestors("Method") == ("Method", "Function", "Callable", "CodeSymbol", "Entity")
    assert {"Function", "Method"} <= r.subtypes("Callable")
    assert "qualified_name" in r.node_props("Method")


def test_edge_signature_honours_subtypes():
    r = get_registry()
    assert r.edge_permits("CALLS", "Method", "Function")
    assert r.edge_permits("MAPS_TO", "Attribute", "Column")
    assert not r.edge_permits("MAPS_TO", "Attribute", "Table")


def test_natural_key_rendering():
    r = get_registry()
    assert natural_key_of(r, "Endpoint", {"method": "POST", "path": "/orders"}) == "POST /orders"
    assert natural_key_of(r, "Parameter", {"callable_qname": "app.f", "position": 0, "name": "x"}) == "app.f#0"


def test_write_path_rejects_violations():
    r = get_registry()
    with pytest.raises(Errors.Domain.UnknownType):
        validate_node(r, "Callable", {}, "asserted")
    with pytest.raises(Errors.Domain.PropertyViolation):
        validate_node(r, "Function", {"qualified_name": "a.f", "bogus": 1}, "asserted")
    with pytest.raises(Errors.Domain.PropertyViolation):
        validate_node(r, "Function", {"qualified_name": "a.f", "returns_none": "maybe"}, "asserted")
    with pytest.raises(Errors.Domain.TierViolation):
        validate_node(r, "Function", {"qualified_name": "a.f"}, "inferred")
    with pytest.raises(Errors.Domain.DomainViolation):
        validate_edge(r, "CALLS", "Function", "Table", {"resolution": "exact"}, "asserted", 1, True)
    with pytest.raises(Errors.Domain.MissingEvidence):
        validate_edge(r, "CALLS", "Function", "Function", {"resolution": "exact"}, "asserted", 0, False)
    with pytest.raises(Errors.Domain.PropertyViolation):
        validate_edge(r, "CALLS", "Function", "Function", {}, "asserted", 1, True)


def test_catalog_ids_are_consistent():
    catalog = to_catalog(get_registry())
    ids = {n["id"] for n in catalog["node_types"]}
    assert all(s["domain_type_id"] in ids and s["range_type_id"] in ids for s in catalog["signatures"])
