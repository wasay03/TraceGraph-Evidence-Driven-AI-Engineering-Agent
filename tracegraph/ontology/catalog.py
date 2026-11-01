from typing import Any

from tracegraph.constants.graph import OWNER_KIND_EDGE, OWNER_KIND_NODE
from tracegraph.ontology.registry import Registry
from tracegraph.ontology.specs import PropSpec


def _prop_rows(owner_kind: str, owner_type_id: int, props: dict[str, PropSpec]) -> list[dict[str, Any]]:
    """
    #Feature: Ontology catalog
    #Scenario: Flatten declared props into prop_def rows
    #Complexity: Time O(p) - linear in props
    """
    return [
        {
            "owner_kind": owner_kind,
            "owner_type_id": owner_type_id,
            "name": name,
            "value_type": spec.value_type,
            "required": spec.required,
            "enum_values": list(spec.enum_values) if spec.enum_values else None,
        }
        for name, spec in props.items()
    ]


def _node_type_rows(registry: Registry) -> list[dict[str, Any]]:
    """
    #Feature: Ontology catalog
    #Scenario: node_type rows with parent ids resolved
    #Complexity: Time O(n) - linear in node types
    """
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "parent_id": registry.node_type(spec.parent).id if spec.parent else None,
            "is_abstract": spec.abstract,
            "natural_key": [spec.key] if spec.key else [],
            "tiers": sorted(spec.tiers),
            "owner": spec.owner,
        }
        for spec in registry.node_types
    ]


def _edge_type_rows(registry: Registry) -> list[dict[str, Any]]:
    """
    #Feature: Ontology catalog
    #Scenario: edge_type rows
    #Complexity: Time O(e) - linear in edge types
    """
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "cardinality": spec.cardinality,
            "inverse_name": spec.inverse,
            "flags": spec.flags,
            "tiers": sorted(spec.tiers),
            "evidence_policy": spec.evidence,
        }
        for spec in registry.edge_types
    ]


def to_catalog(registry: Registry) -> dict[str, list[dict[str, Any]]]:
    """
    #Feature: Ontology catalog
    #Scenario: Serialise the registry into the payload accepted by tg_ontology_sync
    #Complexity: Time O(n + e + s + p) - linear in registry size

    Args:
        registry: Ontology registry.

    Returns:
        Dict with node_types, edge_types, signatures and props rows.

    Raises:
        ValueError: When registry is None.
    """
    if registry is None:
        raise ValueError("[to_catalog] 'registry' is required and must not be None.")
    signatures = [
        {"edge_type_id": e.id, "domain_type_id": registry.node_type(d).id, "range_type_id": registry.node_type(r).id}
        for e in registry.edge_types
        for d, r in e.signatures
    ]
    props = [row for n in registry.node_types for row in _prop_rows(OWNER_KIND_NODE, n.id, n.props)]
    props += [row for e in registry.edge_types for row in _prop_rows(OWNER_KIND_EDGE, e.id, e.props)]
    return {
        "node_types": _node_type_rows(registry),
        "edge_types": _edge_type_rows(registry),
        "signatures": signatures,
        "props": props,
    }
