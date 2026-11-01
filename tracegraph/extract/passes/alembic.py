import ast
import logging
from dataclasses import dataclass, field

from tracegraph.constants.extract import HOLE_RAW_SQL_MIGRATION, METHOD_SCHEMA, normalize_sql_type
from tracegraph.extract.ast_utils import call_name, const_str, dotted_root, keyword, literal_bool
from tracegraph.extract.context import AnalysisContext
from tracegraph.extract.index import ModuleInfo, evidence, span_of
from tracegraph.extract.passes.sqlalchemy import SCHEMA
from tracegraph.extract.records import EdgeRecord, HoleRecord, NodeRecord, NodeRef

logger = logging.getLogger(__name__)

EXTRACTOR = "alembic"


@dataclass(slots=True)
class MigrationOp:
    """
    #Feature: Alembic profile
    #Scenario: One schema operation inside upgrade()
    #Complexity: Time O(1) - constant
    """

    op: str
    table: str
    column: str | None
    node: ast.Call
    nullable: bool | None = None
    sql_type: str | None = None


@dataclass(slots=True)
class MigrationInfo:
    """
    #Feature: Alembic profile
    #Scenario: Revision metadata and its upgrade() operations
    #Complexity: Time O(1) - constant
    """

    module: ModuleInfo
    revision: str
    down_revision: str | None
    node: ast.AST
    ops: list[MigrationOp] = field(default_factory=list)


def _module_str(module: ModuleInfo, name: str) -> tuple[str | None, ast.AST | None]:
    """
    #Feature: Alembic profile
    #Scenario: Module-level `name = "..."` (or `name: str = "..."`) value and its node
    #Complexity: Time O(s) - linear in top-level statements
    """
    for item in module.tree.body:
        targets = item.targets if isinstance(item, ast.Assign) else [item.target] if isinstance(item, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return const_str(item.value), item
    return None, None


def _column_def(call: ast.expr) -> tuple[str | None, bool | None, str | None]:
    """
    #Feature: Alembic profile
    #Scenario: (name, nullable, type) of sa.Column("name", sa.Type(), nullable=..., primary_key=...)
    #Complexity: Time O(a) - linear in arguments
    """
    if call_name(call) != "Column" or not call.args:
        return None, None, None
    nullable = literal_bool(keyword(call, "nullable"))
    if nullable is None:
        nullable = not literal_bool(keyword(call, "primary_key"))
    type_arg = call.args[1] if len(call.args) > 1 else None
    sql_type = (call_name(type_arg) or (type_arg.attr if isinstance(type_arg, ast.Attribute) else None))
    return const_str(call.args[0]), nullable, normalize_sql_type(sql_type)


def _ops(call: ast.Call) -> list[MigrationOp]:
    """
    #Feature: Alembic profile
    #Scenario: Translate one op.* call into schema operations
    #Complexity: Time O(a) - linear in arguments
    """
    name, args = call_name(call), call.args
    table = const_str(args[0]) if args else None
    if table is None:
        return []
    if name == "create_table":
        columns = [_column_def(a) for a in args[1:]]
        return [MigrationOp("add", table, None, call)] + [
            MigrationOp("add", table, c, call, n, t) for c, n, t in columns if c]
    if name == "add_column" and len(args) > 1:
        column, nullable, sql_type = _column_def(args[1])
        return [MigrationOp("add", table, column, call, nullable, sql_type)] if column else []
    if name == "alter_column" and len(args) > 1:
        type_arg = keyword(call, "type_")
        return [MigrationOp("alter", table, const_str(args[1]), call, literal_bool(keyword(call, "nullable")),
                            normalize_sql_type(call_name(type_arg)))]
    if name in ("drop_column", "drop_table"):
        column = const_str(args[1]) if name == "drop_column" and len(args) > 1 else None
        return [MigrationOp("drop", table, column, call)]
    return []


def _chain(migrations: dict[str, MigrationInfo]) -> list[MigrationInfo]:
    """
    #Feature: Alembic profile
    #Scenario: Order migrations from the root along down_revision links (linear history)
    #Complexity: Time O(m) - linear in migrations
    """
    children = {m.down_revision: m for m in migrations.values()}
    ordered, current = [], children.get(None)
    while current is not None and current not in ordered:
        ordered.append(current)
        current = children.get(current.revision)
    return ordered + [m for m in migrations.values() if m not in ordered]


class AlembicPass:
    """
    #Feature: Alembic profile and schema replay (PRD 5.1 steps 4 and 6)
    #Scenario: Migration nodes, PRECEDES chain, MIGRATES edges; replay ops statically to derive the database
               schema (in_db, db_nullable, db_sql_type) so ORM/DB drift is checkable without a live database
    #Complexity: Time O(M * o) - migrations times operations
    """

    def __init__(self, ctx: AnalysisContext) -> None:
        """
        #Feature: Alembic profile
        #Scenario: Bind to the analysis context
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When ctx is None.
        """
        if ctx is None:
            raise ValueError("[AlembicPass.__init__] 'ctx' is required.")
        self.ctx = ctx
        self._b = ctx.builder

    def _collect(self) -> dict[str, MigrationInfo]:
        """
        #Feature: Alembic profile
        #Scenario: Modules under a versions/ directory that declare `revision`
        #Complexity: Time O(m * n) - modules times statements
        """
        out = {}
        for module in self.ctx.index.modules.values():
            if "versions" not in module.path.split("/")[:-1]:
                continue
            revision, node = _module_str(module, "revision")
            if revision is None:
                continue
            down, _ = _module_str(module, "down_revision")
            info = MigrationInfo(module, revision, down, node)
            upgrade = next((f for f in module.tree.body if isinstance(f, ast.FunctionDef) and f.name == "upgrade"), None)
            for call in (n for n in ast.walk(upgrade) if isinstance(n, ast.Call)) if upgrade else []:
                if isinstance(call.func, ast.Attribute) and dotted_root(call.func) == "op":
                    info.ops.extend(_ops(call))
                    if call.func.attr == "execute":
                        self._b.add_hole(HoleRecord(HOLE_RAW_SQL_MIGRATION, module.path, span_of(call)))
            out[revision] = info
        return out

    def _target(self, op: MigrationOp) -> NodeRef:
        """
        #Feature: Alembic profile
        #Scenario: Table or Column ref an operation touches
        #Complexity: Time O(1) - constant
        """
        if op.column is None:
            return self._b.add_node(NodeRecord("Table", {"schema": SCHEMA, "name": op.table}))
        return self._b.add_node(NodeRecord("Column", {"table": op.table, "name": op.column}))

    def _replay(self, ordered: list[MigrationInfo]) -> dict[tuple[str, str | None], tuple[MigrationOp, MigrationInfo]]:
        """
        #Feature: Schema replay
        #Scenario: Apply add/alter/drop in chain order; the result is the head schema keyed by (table, column)
        #Complexity: Time O(M * o) - migrations times operations
        """
        schema: dict[tuple[str, str | None], tuple[MigrationOp, MigrationInfo]] = {}
        for migration in ordered:
            for op in migration.ops:
                key = (op.table, op.column)
                if op.op == "drop":
                    for k in [k for k in schema if k == key or (op.column is None and k[0] == op.table)]:
                        del schema[k]
                elif op.op == "add" or key not in schema:
                    schema[key] = (op, migration)
                else:
                    prev = schema[key][0]
                    nullable = op.nullable if op.nullable is not None else prev.nullable
                    schema[key] = (MigrationOp("add", op.table, op.column, op.node, nullable,
                                               op.sql_type or prev.sql_type), migration)
        return schema

    def _emit_schema(self, schema: dict[tuple[str, str | None], tuple[MigrationOp, MigrationInfo]]) -> None:
        """
        #Feature: Schema replay
        #Scenario: Database-side Table/Column props and HAS_COLUMN for the head schema
        #Complexity: Time O(c) - linear in columns
        """
        for (table, column), (op, migration) in schema.items():
            ev = [evidence(EXTRACTOR, METHOD_SCHEMA, migration.module, op.node)]
            if column is None:
                self._b.add_node(NodeRecord("Table", {"schema": SCHEMA, "name": table, "in_db": True},
                                            migration.module.path, span_of(op.node)))
                continue
            ref = self._b.add_node(NodeRecord("Column", {"table": table, "name": column, "in_db": True,
                                                         "db_nullable": op.nullable, "db_sql_type": op.sql_type},
                                              migration.module.path, span_of(op.node)))
            self._b.add_edge(EdgeRecord("HAS_COLUMN", NodeRef("Table", f"{SCHEMA}.{table}"), ref, ev))

    def run(self) -> None:
        """
        #Feature: Alembic profile
        #Scenario: Migration graph, then schema replay
        #Complexity: Time O(M * o) - migrations times operations
        """
        migrations = self._collect()
        if not migrations:
            return
        for m in migrations.values():
            summary = ", ".join(f"{o.op} {o.table}{'.' + o.column if o.column else ''}" for o in m.ops)[:500]
            ref = self._b.add_node(NodeRecord("Migration", {"revision": m.revision, "down_revision": m.down_revision,
                                                            "op_summary": summary}, m.module.path, span_of(m.node)))
            for op in m.ops:
                self._b.add_edge(EdgeRecord("MIGRATES", ref, self._target(op),
                                            [evidence(EXTRACTOR, METHOD_SCHEMA, m.module, op.node)], props={"op": op.op}))
            if m.down_revision in migrations:
                self._b.add_edge(EdgeRecord("PRECEDES", NodeRef("Migration", m.down_revision), ref,
                                            [evidence(EXTRACTOR, METHOD_SCHEMA, m.module, m.node)]))
        self._emit_schema(self._replay(_chain(migrations)))
        logger.info("Alembic pass done", extra={"migrations": len(migrations)})
