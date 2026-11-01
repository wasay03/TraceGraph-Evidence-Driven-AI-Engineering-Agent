from functools import lru_cache

from tracegraph.constants.ontology import ONTOLOGY_SEMVER
from tracegraph.ontology.catalog import to_catalog
from tracegraph.ontology.registry import Registry
from tracegraph.ontology.specs import EdgeTypeSpec, NodeTypeSpec, PropSpec
from tracegraph.ontology.types import (
    register_code_edges,
    register_code_nodes,
    register_data_edges,
    register_data_nodes,
    register_governance_edges,
    register_governance_nodes,
    register_interface_edges,
    register_interface_nodes,
    register_verification_edges,
    register_verification_nodes,
)
from tracegraph.ontology.validation import natural_key_of, validate_edge, validate_node


@lru_cache(maxsize=1)
def get_registry() -> Registry:
    """
    #Feature: Ontology registry
    #Scenario: Build the default code ontology once per process; registration order fixes type ids
    #Complexity: Time O(n + e) once, then O(1)

    Returns:
        The populated Registry.
    """
    registry = Registry(ONTOLOGY_SEMVER)
    register_code_nodes(registry)
    register_data_nodes(registry)
    register_interface_nodes(registry)
    register_verification_nodes(registry)
    register_governance_nodes(registry)
    register_code_edges(registry)
    register_data_edges(registry)
    register_interface_edges(registry)
    register_verification_edges(registry)
    register_governance_edges(registry)
    return registry


__all__ = [
    "EdgeTypeSpec",
    "NodeTypeSpec",
    "PropSpec",
    "Registry",
    "get_registry",
    "natural_key_of",
    "to_catalog",
    "validate_edge",
    "validate_node",
]
