from tracegraph.ontology.registry import Registry
from tracegraph.ontology.specs import Bool, Enum, Str

VIA = ("orm", "sql")
SQL_OPS = ("select", "insert", "update", "delete")


def register_data_nodes(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: Database schema, migration and query-site node types (PRD 4.2)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry with abstract roots registered.
    """
    registry.node("Table", parent="DataObject", key="{schema}.{name}", owner="schema",
                  props={"schema": Str(required=True), "name": Str(required=True), "comment": Str(),
                         "in_orm": Bool(), "in_db": Bool()})
    registry.node("Column", parent="DataObject", key="{table}.{name}", owner="schema",
                  props={"table": Str(required=True), "name": Str(required=True), "sql_type": Str(),
                         "nullable": Bool(), "default": Str(), "is_pk": Bool(),
                         "db_nullable": Bool(), "db_sql_type": Str(), "in_orm": Bool(), "in_db": Bool()})
    registry.node("Constraint", parent="DataObject", key="{table}.{name}", owner="schema",
                  props={"table": Str(required=True), "name": Str(required=True),
                         "kind": Enum("pk", "fk", "unique", "check", "not_null", required=True),
                         "expression": Str()})
    registry.node("Migration", parent="DataObject", key="{revision}", owner="alembic",
                  props={"revision": Str(required=True), "down_revision": Str(), "op_summary": Str()})
    registry.node("QuerySite", parent="DataObject", key="{file}:{line}", owner="sql",
                  props={"file": Str(required=True), "line": Str(required=True), "op": Enum(*SQL_OPS),
                         "dialect": Str(), "is_dynamic": Bool(default=False)})


def register_data_edges(registry: Registry) -> None:
    """
    #Feature: Ontology registry
    #Scenario: ORM mapping, schema structure, data access and migration edges (PRD 4.3)
    #Complexity: Time O(1) - fixed number of registrations

    Args:
        registry: Registry with code and data node types registered.
    """
    registry.edge("MAPS_TO", [("Class", "Table"), ("Attribute", "Column")], cardinality="1:1",
                  inverse="MAPPED_BY")
    registry.edge("HAS_COLUMN", [("Table", "Column")], cardinality="1:N", inverse="COLUMN_OF",
                  evidence="evidence_required")
    registry.edge("CONSTRAINED_BY", [("Table", "Constraint"), ("Column", "Constraint")], cardinality="N:M",
                  inverse="CONSTRAINS", evidence="evidence_required")
    registry.edge("REFERENCES_FK", [("Column", "Column")], cardinality="N:1", inverse="REFERENCED_BY_FK",
                  props={"on_delete": Str()}, evidence="evidence_required")
    registry.edge("EXECUTES", [("Callable", "QuerySite")], cardinality="1:N", inverse="EXECUTED_BY")
    data_access = [("Callable", "Table"), ("Callable", "Column"), ("QuerySite", "Table"), ("QuerySite", "Column")]
    registry.edge("READS_FROM", data_access, cardinality="N:M", inverse="READ_BY",
                  props={"via": Enum(*VIA)})
    registry.edge("WRITES_TO", data_access, cardinality="N:M", inverse="WRITTEN_BY",
                  props={"op": Enum(*SQL_OPS), "via": Enum(*VIA)})
    registry.edge("FILTERS_ON", [("QuerySite", "Column"), ("Callable", "Column")], cardinality="N:M",
                  inverse="FILTERED_BY", flags={"fact": True})
    registry.edge("MIGRATES", [("Migration", "Table"), ("Migration", "Column")], cardinality="N:M",
                  inverse="MIGRATED_BY", props={"op": Enum("add", "alter", "drop")})
    registry.edge("PRECEDES", [("Migration", "Migration")], cardinality="1:1", inverse="FOLLOWS",
                  flags={"acyclic": True})
