from tracegraph.ontology.registry import Registry
from tracegraph.ontology.specs import Bool, Enum, Int, List, Str

PARAM_KINDS = ("positional_only", "positional_or_keyword", "var_positional", "keyword_only", "var_keyword")


def register_code_nodes(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: Abstract roots plus Python code symbol node types (PRD 4.2)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry to populate; abstract roots must be registered here first.
    """
    registry.node("Entity", abstract=True)
    registry.node("CodeSymbol", parent="Entity", abstract=True)
    registry.node("Callable", parent="CodeSymbol", abstract=True)
    registry.node("DataObject", parent="Entity", abstract=True)
    registry.node("InterfaceObject", parent="Entity", abstract=True)
    registry.node("VerificationObject", parent="Entity", abstract=True)
    registry.node("GovernanceObject", parent="Entity", abstract=True)

    registry.node("Repository", parent="Entity", key="{url}", owner="ingest",
                  props={"url": Str(required=True), "name": Str(), "default_branch": Str()})
    registry.node("Module", parent="CodeSymbol", key="{qualified_name}", owner="structure",
                  props={"qualified_name": Str(required=True), "path": Str(required=True),
                         "is_test": Bool(default=False), "is_package": Bool(default=False),
                         "content_hash": Str(), "signature_hash": Str()})
    registry.node("Class", parent="CodeSymbol", key="{qualified_name}", owner="structure",
                  props={"qualified_name": Str(required=True), "name": Str(), "is_abstract": Bool(),
                         "is_dataclass": Bool(), "is_enum": Bool(), "is_pydantic": Bool(),
                         "is_exception": Bool(), "is_orm_model": Bool()})
    registry.node("Function", parent="Callable", key="{qualified_name}", owner="structure",
                  props={"qualified_name": Str(required=True), "name": Str(), "is_async": Bool(default=False),
                         "return_annotation": Str(),
                         "returns_none": Enum("never", "some_paths", "always", "unknown")})
    registry.node("Method", parent="Function", key="{qualified_name}", owner="structure",
                  props={"kind": Enum("instance", "class", "static", "property")})
    registry.node("Parameter", parent="CodeSymbol", key="{callable_qname}#{position}", owner="structure",
                  props={"callable_qname": Str(required=True), "position": Int(required=True),
                         "name": Str(required=True), "annotation": Str(), "has_default": Bool(),
                         "kind": Enum(*PARAM_KINDS), "is_optional": Bool()})
    registry.node("Attribute", parent="CodeSymbol", key="{owner_qname}.{name}", owner="structure",
                  props={"owner_qname": Str(required=True), "name": Str(required=True), "annotation": Str(),
                         "is_classvar": Bool(), "default": Str(), "is_optional": Bool()})
    registry.node("Variable", parent="CodeSymbol", key="{qualified_name}", owner="structure",
                  props={"qualified_name": Str(required=True), "is_constant": Bool(), "annotation": Str()})
    registry.node("EnumMember", parent="CodeSymbol", key="{enum_qname}.{name}", owner="structure",
                  props={"enum_qname": Str(required=True), "name": Str(required=True), "value": Str()})
    registry.node("TypeExpr", parent="Entity", key="{text}", owner="resolver",
                  props={"text": Str(required=True), "is_optional": Bool(), "is_union": Bool(),
                         "base_names": List()})


def register_code_edges(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: Structural, call-graph and type edges between code symbols (PRD 4.3)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry with code node types already registered.
    """
    registry.edge("CONTAINS", [("Module", "CodeSymbol"), ("Class", "CodeSymbol")], cardinality="1:N",
                  inverse="CONTAINED_IN", flags={"acyclic": True, "transitive_closure": "CONTAINS*"})
    registry.edge("IMPORTS", [("Module", "Module"), ("Module", "CodeSymbol")], cardinality="N:M",
                  inverse="IMPORTED_BY", props={"alias": Str(), "is_type_only": Bool()})
    registry.edge("CALLS", [("Callable", "Callable")], cardinality="N:M", inverse="CALLED_BY",
                  props={"resolution": Enum("exact", "dispatch_candidate", "unresolved", required=True),
                         "is_await": Bool(), "n_args": Int(), "kwargs": List(), "has_star": Bool(),
                         "result_use": Enum("unused", "guarded", "unguarded", "returned")},
                  flags={"transitive_closure": "CALLS*"},
                  tiers=frozenset({"asserted", "observed", "inferred"}))
    registry.edge("INSTANTIATES", [("Callable", "Class")], cardinality="N:M", inverse="INSTANTIATED_BY")
    registry.edge("INHERITS", [("Class", "Class")], cardinality="N:M", inverse="INHERITED_BY",
                  props={"mro_index": Int()}, flags={"acyclic": True, "transitive_closure": "INHERITS*"})
    registry.edge("OVERRIDES", [("Method", "Method")], cardinality="N:1", inverse="OVERRIDDEN_BY")
    registry.edge("DECORATED_BY", [("Callable", "Callable"), ("Class", "Callable")], cardinality="N:M",
                  inverse="DECORATES", props={"order": Int()}, flags={"ordered": True})
    registry.edge("HAS_PARAM", [("Callable", "Parameter")], cardinality="1:N", inverse="PARAM_OF",
                  props={"position": Int()}, flags={"ordered": True})
    registry.edge("ANNOTATED_AS", [("Parameter", "TypeExpr"), ("Attribute", "TypeExpr"),
                                   ("Callable", "TypeExpr")], cardinality="N:1", inverse="ANNOTATES",
                  props={"role": Enum("param", "return", "attr")})
    registry.edge("READS_ATTR", [("Callable", "Attribute")], cardinality="N:M", inverse="ATTR_READ_BY")
    registry.edge("WRITES_ATTR", [("Callable", "Attribute")], cardinality="N:M", inverse="ATTR_WRITTEN_BY")
    registry.edge("RAISES", [("Callable", "Class")], cardinality="N:M", inverse="RAISED_BY")
    registry.edge("CATCHES", [("Callable", "Class")], cardinality="N:M", inverse="CAUGHT_BY")
