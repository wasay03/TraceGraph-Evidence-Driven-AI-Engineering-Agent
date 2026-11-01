from tracegraph.ontology.registry import Registry
from tracegraph.ontology.specs import Bool, Enum, Float, List, Str

GUARD_KINDS = ("attribute_access", "call_on_value", "arithmetic", "subscript", "required_field")


def register_verification_nodes(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: pytest test and fixture node types (PRD 4.2)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry with abstract roots registered.
    """
    registry.node("Test", parent="VerificationObject", key="{node_id}", owner="pytest",
                  props={"node_id": Str(required=True), "markers": List(), "is_parametrized": Bool()})
    registry.node("Fixture", parent="VerificationObject", key="{qualified_name}", owner="pytest",
                  props={"qualified_name": Str(required=True),
                         "scope": Enum("function", "class", "module", "package", "session")})


def register_verification_edges(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: Test linkage and intra-procedural fact edges (PRD 4.3, D10)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry with code, data and verification node types registered.
    """
    registry.edge("TESTS", [("Test", "CodeSymbol")], cardinality="N:M", inverse="TESTED_BY",
                  props={"method": Enum("import", "call", "coverage", required=True), "strength": Float()},
                  tiers=frozenset({"asserted", "observed"}))
    registry.edge("USES_FIXTURE", [("Test", "Fixture")], cardinality="N:M", inverse="FIXTURE_USED_BY")
    registry.edge("ASSUMES_NOT_NULL", [("Callable", "Attribute"), ("Callable", "Column"),
                                       ("Callable", "Parameter")], cardinality="N:M",
                  inverse="ASSUMED_NOT_NULL_BY", props={"guard_kind": Enum(*GUARD_KINDS)}, flags={"fact": True})
    registry.edge("BRANCHES_ON", [("Callable", "Attribute"), ("Callable", "Column"),
                                  ("Callable", "EnumMember")], cardinality="N:M", inverse="BRANCHED_ON_BY",
                  props={"compared_values": List(), "has_default": Bool()}, flags={"fact": True})
    registry.edge("VALIDATES", [("Callable", "Attribute"), ("Callable", "Column"), ("Class", "Attribute"),
                                ("Class", "Column")], cardinality="N:M", inverse="VALIDATED_BY",
                  props={"validator_kind": Str()}, flags={"fact": True})
