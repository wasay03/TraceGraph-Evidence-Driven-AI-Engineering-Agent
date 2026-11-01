from tracegraph.ontology.registry import Registry
from tracegraph.ontology.specs import Enum, List, Str


def register_interface_nodes(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: HTTP endpoint, configuration and package node types (PRD 4.2)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry with abstract roots registered.
    """
    registry.node("Endpoint", parent="InterfaceObject", key="{method} {path}", owner="fastapi",
                  props={"method": Str(required=True), "path": Str(required=True), "status_codes": List(),
                         "auth_dependency": Str()})
    registry.node("ConfigKey", parent="InterfaceObject", key="{name}", owner="structure",
                  props={"name": Str(required=True), "source": Enum("env", "settings"), "default": Str()})
    registry.node("ExternalPackage", parent="InterfaceObject", key="{name}", owner="manifest",
                  props={"name": Str(required=True), "version_spec": Str()})


def register_interface_edges(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: Endpoint handling, DTO, dependency injection, config and package edges (PRD 4.3)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry with code and interface node types registered.
    """
    registry.edge("HANDLED_BY", [("Endpoint", "Callable")], cardinality="N:1", inverse="HANDLES")
    registry.edge("ACCEPTS", [("Endpoint", "Class")], cardinality="N:M", inverse="ACCEPTED_BY")
    registry.edge("RESPONDS_WITH", [("Endpoint", "Class")], cardinality="N:M", inverse="RESPONSE_OF")
    registry.edge("INJECTS", [("Callable", "Callable")], cardinality="N:M", inverse="INJECTED_BY")
    registry.edge("USES_CONFIG", [("Callable", "ConfigKey")], cardinality="N:M", inverse="CONFIG_USED_BY")
    registry.edge("USES_PACKAGE", [("Module", "ExternalPackage")], cardinality="N:M", inverse="PACKAGE_USED_BY")
