from tracegraph.ontology.registry import Registry
from tracegraph.ontology.specs import Enum, List, Str


def register_governance_nodes(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: Invariant and business-rule node types (PRD 4.2)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry with abstract roots registered.
    """
    registry.node("Invariant", parent="GovernanceObject", key="{id}", owner="rule_pack",
                  props={"id": Str(required=True), "dsl": Str(), "severity": Enum("error", "warn", "info"),
                         "scope_types": List()})
    registry.node("BusinessRule", parent="GovernanceObject", key="{id}", owner="rule_pack",
                  props={"id": Str(required=True), "statement": Str(), "owner": Str()},
                  tiers=frozenset({"asserted", "inferred"}))


def register_governance_edges(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: Governance edges linking rules to code (PRD 4.3)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry with all node types registered.
    """
    registry.edge("GOVERNS", [("Invariant", "Entity")], cardinality="N:M", inverse="GOVERNED_BY",
                  evidence="none")
    registry.edge("IMPLEMENTS_RULE", [("CodeSymbol", "BusinessRule")], cardinality="N:M",
                  inverse="IMPLEMENTED_BY", tiers=frozenset({"inferred"}), evidence="evidence_required")
