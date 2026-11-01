from typing import Any

from pydantic import BaseModel


class PropSchema(BaseModel):
    """
    #Feature: Ontology API
    #Scenario: Declared property of a node or edge type
    #Complexity: Time O(1) - constant
    """

    name: str
    value_type: str
    required: bool
    enum_values: list[str] | None = None


class NodeTypeSchema(BaseModel):
    """
    #Feature: Ontology API
    #Scenario: Node type with hierarchy, key and effective props
    #Complexity: Time O(1) - constant
    """

    id: int
    name: str
    parent: str | None
    abstract: bool
    key: str | None
    tiers: list[str]
    owner: str | None
    props: list[PropSchema]


class EdgeTypeSchema(BaseModel):
    """
    #Feature: Ontology API
    #Scenario: Edge type with signatures, cardinality and flags
    #Complexity: Time O(1) - constant
    """

    id: int
    name: str
    signatures: list[tuple[str, str]]
    cardinality: str
    inverse: str | None
    flags: dict[str, Any]
    tiers: list[str]
    evidence: str
    props: list[PropSchema]


class OntologyResponse(BaseModel):
    """
    #Feature: Ontology API
    #Scenario: Full registry plus the catalog version loaded in the database
    #Complexity: Time O(1) - constant
    """

    semver: str
    catalog_version_id: int | None
    catalog_in_sync: bool
    node_types: list[NodeTypeSchema]
    edge_types: list[EdgeTypeSchema]
