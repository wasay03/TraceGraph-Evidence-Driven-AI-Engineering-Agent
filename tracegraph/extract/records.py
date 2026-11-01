from dataclasses import dataclass, field
from typing import Any

from tracegraph.constants.graph import TIER_ASSERTED


@dataclass(frozen=True, slots=True)
class NodeRef:
    """
    #Feature: Extraction records
    #Scenario: Reference to a node by concrete type and natural key; ids are derived from it
    #Complexity: Time O(1) - constant
    """

    type: str
    key: str


@dataclass(frozen=True, slots=True)
class Span:
    """
    #Feature: Extraction records
    #Scenario: Inclusive 1-based line range in a file
    #Complexity: Time O(1) - constant
    """

    start: int
    end: int


@dataclass(slots=True)
class NodeRecord:
    """
    #Feature: Extraction records
    #Scenario: A node produced by an extraction pass, before validation and id assignment
    #Complexity: Time O(1) - constant
    """

    type: str
    props: dict[str, Any]
    file_path: str | None = None
    span: Span | None = None
    tier: str = TIER_ASSERTED


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """
    #Feature: Provenance
    #Scenario: Why an edge exists: extractor, method and source location
    #Complexity: Time O(1) - constant
    """

    extractor: str
    method: str
    file_path: str | None
    span: Span | None
    snippet_hash: str | None = None
    confidence: float | None = None
    rationale: str | None = None


@dataclass(slots=True)
class EdgeRecord:
    """
    #Feature: Extraction records
    #Scenario: A typed edge between two node refs with its evidence; owner_file drives incremental scope
    #Complexity: Time O(1) - constant
    """

    type: str
    src: NodeRef
    dst: NodeRef
    evidence: list[EvidenceRecord]
    props: dict[str, Any] = field(default_factory=dict)
    owner_file: str | None = None
    tier: str = TIER_ASSERTED
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class HoleRecord:
    """
    #Feature: Coverage map
    #Scenario: Region where a pass could not reach completeness
    #Complexity: Time O(1) - constant
    """

    kind: str
    file_path: str | None
    span: Span | None
    node: NodeRef | None = None
    detail: tuple[tuple[str, Any], ...] = ()
