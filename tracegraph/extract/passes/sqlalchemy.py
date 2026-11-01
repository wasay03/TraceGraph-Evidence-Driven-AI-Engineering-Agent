import ast
import logging

from tracegraph.constants.extract import METHOD_ORM, normalize_sql_type
from tracegraph.extract.ast_utils import body_nodes, call_name, const_str, keyword, literal_bool
from tracegraph.extract.context import AnalysisContext
from tracegraph.extract.index import ClassInfo, FunctionInfo, evidence, span_of
from tracegraph.extract.records import EdgeRecord, NodeRecord, NodeRef
from tracegraph.extract.resolver import FunctionScope, dotted_name

logger = logging.getLogger(__name__)

EXTRACTOR = "sqlalchemy"
SCHEMA = "public"
_PY_SQL_TYPES = {"int": "INTEGER", "str": "VARCHAR", "bool": "BOOLEAN", "float": "FLOAT", "datetime": "TIMESTAMP",
                 "date": "DATE", "Decimal": "NUMERIC", "dict": "JSON", "bytes": "BYTEA", "UUID": "UUID"}
_STATEMENT_OPS = {"select": "select", "update": "update", "delete": "delete", "insert": "insert"}
_SESSION_OPS = {"get": "select", "query": "select", "add": "insert", "merge": "update", "delete": "delete"}
_READ_OPS = {"select"}


def _column_call(value: ast.expr | None) -> ast.Call | None:
    """
    #Feature: SQLAlchemy profile
    #Scenario: The mapped_column(...)/Column(...) call of an attribute, if any
    #Complexity: Time O(1) - constant
    """
    return value if call_name(value) in ("mapped_column", "Column") else None


def _mapped_inner(annotation: ast.expr | None) -> tuple[ast.expr | None, bool]:
    """
    #Feature: SQLAlchemy profile
    #Scenario: Inner type of Mapped[T] and whether it is Optional / T | None
    #Complexity: Time O(1) - constant
    """
    if not (isinstance(annotation, ast.Subscript) and (dotted_name(annotation.value) or "").endswith("Mapped")):
        return None, False
    inner = annotation.slice
    text = ast.unparse(inner)
    optional = "None" in text or text.startswith("Optional")
    if isinstance(inner, ast.BinOp):
        inner = inner.left if not (isinstance(inner.left, ast.Constant) and inner.left.value is None) else inner.right
    elif isinstance(inner, ast.Subscript) and (dotted_name(inner.value) or "").endswith("Optional"):
        inner = inner.slice
    return inner, optional


class SqlAlchemyPass:
    """
    #Feature: SQLAlchemy 2.0 profile (PRD 5.1 step 4)
    #Scenario: Mapped classes -> Table/Column with nullability; ForeignKey -> REFERENCES_FK; select/update/
               delete/insert and session.get/add/delete -> QuerySite with READS_FROM/WRITES_TO/FILTERS_ON
    #Complexity: Time O(N) - linear in AST nodes
    """

    def __init__(self, ctx: AnalysisContext) -> None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Bind to the analysis context
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When ctx is None.
        """
        if ctx is None:
            raise ValueError("[SqlAlchemyPass.__init__] 'ctx' is required.")
        self.ctx = ctx
        self._b = ctx.builder

    # ---- mapping ------------------------------------------------------------------------

    def _sql_type(self, cls: ClassInfo, call: ast.Call | None, inner: ast.expr | None) -> str | None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Explicit SQL type argument, else derived from the Mapped[T] python type
        #Complexity: Time O(a) - linear in call arguments
        """
        for arg in (call.args if call else []):
            name = call_name(arg) or (dotted_name(arg) or "").split(".")[-1]
            if name and name != "ForeignKey" and const_str(arg) is None:
                return normalize_sql_type(name)
        if inner is None:
            return None
        qname = self.ctx.resolver.resolve_expr(cls.module, inner)
        if qname in self.ctx.index.classes and self.ctx.index.classes[qname].is_enum:
            return "ENUM"
        return _PY_SQL_TYPES.get((dotted_name(inner) or "").split(".")[-1])

    def _foreign_key(self, cls: ClassInfo, column: NodeRef, call: ast.Call | None, node: ast.AST) -> None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: ForeignKey("table.col", ondelete=...) -> REFERENCES_FK
        #Complexity: Time O(a) - linear in call arguments
        """
        for arg in (call.args if call else []):
            target = const_str(arg.args[0]) if call_name(arg) == "ForeignKey" and arg.args else None
            if target and "." in target:
                table, col = target.rsplit(".", 1)
                dst = self._b.add_node(NodeRecord("Column", {"table": table, "name": col}))
                on_delete = const_str(keyword(arg, "ondelete"))
                self._b.add_edge(EdgeRecord("REFERENCES_FK", column, dst, [evidence(EXTRACTOR, METHOD_ORM, cls.module, node)],
                                            props={"on_delete": on_delete} if on_delete else {}))

    def _column(self, cls: ClassInfo, table: str, table_ref: NodeRef, item: ast.AnnAssign | ast.Assign) -> None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: One mapped attribute -> Column node with SQLAlchemy 2.0 nullability rules
        #Complexity: Time O(a) - linear in call arguments
        """
        target = item.target if isinstance(item, ast.AnnAssign) else item.targets[0]
        if not isinstance(target, ast.Name) or call_name(item.value) == "relationship":
            return
        call = _column_call(item.value)
        inner, optional = _mapped_inner(getattr(item, "annotation", None))
        if call is None and inner is None:
            return
        explicit = literal_bool(keyword(call, "nullable")) if call else None
        pk = bool(call and literal_bool(keyword(call, "primary_key")))
        nullable = explicit if explicit is not None else (False if pk else optional if inner is not None else True)
        name = (const_str(call.args[0]) if call and call.args else None) or target.id
        default = keyword(call, "default") if call else None
        column = self._b.add_node(NodeRecord("Column", {
            "table": table, "name": name, "sql_type": self._sql_type(cls, call, inner), "nullable": nullable,
            "is_pk": pk, "default": ast.unparse(default)[:100] if default is not None else None, "in_orm": True},
            cls.module.path, span_of(item)))
        ev = [evidence(EXTRACTOR, METHOD_ORM, cls.module, item)]
        self._b.add_edge(EdgeRecord("HAS_COLUMN", table_ref, column, ev))
        if target.id in cls.attributes:
            self._b.add_edge(EdgeRecord("MAPS_TO", cls.attributes[target.id].ref, column, list(ev)))
        self.ctx.orm_columns[(cls.qname, target.id)] = name
        self._foreign_key(cls, column, call, item)

    def _mapped_class(self, cls: ClassInfo) -> None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Class with __tablename__ -> Table, MAPS_TO, columns
        #Complexity: Time O(b) - linear in class body
        """
        table = next((const_str(i.value) for i in cls.node.body if isinstance(i, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in i.targets)), None)
        if table is None:
            return
        table_ref = self._b.add_node(NodeRecord("Table", {"schema": SCHEMA, "name": table, "in_orm": True},
                                                cls.module.path, span_of(cls.node)))
        self._b.add_node(NodeRecord("Class", {"qualified_name": cls.qname, "is_orm_model": True}))
        self._b.add_edge(EdgeRecord("MAPS_TO", cls.ref, table_ref, [evidence(EXTRACTOR, METHOD_ORM, cls.module, cls.node)]))
        self.ctx.orm_tables[cls.qname] = table
        for item in cls.node.body:
            if isinstance(item, (ast.AnnAssign, ast.Assign)):
                self._column(cls, table, table_ref, item)

    # ---- query sites --------------------------------------------------------------------

    def _mapped_of(self, fn: FunctionInfo, scope: FunctionScope, expr: ast.expr, by_value: bool) -> str | None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Mapped class named by expr (Model or Model.col), or of expr's value when by_value
        #Complexity: Time O(d) - expression depth
        """
        if by_value:
            cls = self.ctx.types.expr_class(scope, expr)
        else:
            target = expr.value if isinstance(expr, ast.Attribute) else expr
            cls = self.ctx.resolver.resolve_expr(fn.module, target)
        return cls if cls in self.ctx.orm_tables else None

    def _query_target(self, fn: FunctionInfo, scope: FunctionScope, call: ast.Call) -> tuple[str, str] | None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: (op, mapped class) for statement constructors and session methods
        #Complexity: Time O(1) - constant
        """
        name = call_name(call)
        if not call.args:
            return None
        if name in _STATEMENT_OPS and isinstance(call.func, ast.Name):
            cls = self._mapped_of(fn, scope, call.args[0], by_value=False)
            return (_STATEMENT_OPS[name], cls) if cls else None
        if name in _SESSION_OPS and isinstance(call.func, ast.Attribute):
            by_value = name in ("add", "merge", "delete")
            cls = self._mapped_of(fn, scope, call.args[0], by_value=by_value)
            return (_SESSION_OPS[name], cls) if cls else None
        return None

    def _column_refs(self, fn: FunctionInfo, stmt: ast.stmt) -> tuple[list[NodeRef], list[NodeRef]]:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Columns compared in where()/filter() and columns assigned in values() of one statement
        #Complexity: Time O(n) - linear in statement nodes
        """
        filters, writes = [], []
        for node in ast.walk(stmt):
            if isinstance(node, ast.Compare):
                for side in [node.left, *node.comparators]:
                    if isinstance(side, ast.Attribute):
                        ref = self._column_ref(fn, side.value, side.attr)
                        filters += [ref] if ref else []
            elif isinstance(node, ast.Call) and call_name(node) == "values" and isinstance(node.func, ast.Attribute):
                cls = self._statement_class(fn, node.func.value)
                writes += [self._column_ref_cls(cls, kw.arg) for kw in node.keywords if cls and kw.arg]
        return [r for r in filters if r], [r for r in writes if r]

    def _statement_class(self, fn: FunctionInfo, expr: ast.expr) -> str | None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Mapped class at the root of a statement chain such as update(Model).where(...)
        #Complexity: Time O(d) - chain depth
        """
        while isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
            expr = expr.func.value
        if isinstance(expr, ast.Call) and expr.args:
            return self._mapped_of(fn, self.ctx.scope(fn.qname), expr.args[0], by_value=False)
        return None

    def _column_ref_cls(self, cls: str | None, attr: str) -> NodeRef | None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Column ref of a mapped attribute
        #Complexity: Time O(1) - constant
        """
        column = self.ctx.orm_columns.get((cls, attr)) if cls else None
        return NodeRef("Column", f"{self.ctx.orm_tables[cls]}.{column}") if column else None

    def _column_ref(self, fn: FunctionInfo, owner: ast.expr, attr: str) -> NodeRef | None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Column ref of Model.attr written in a query expression
        #Complexity: Time O(d) - resolution cost
        """
        return self._column_ref_cls(self._mapped_of(fn, self.ctx.scope(fn.qname), owner, by_value=False), attr)

    def _query_site(self, fn: FunctionInfo, stmt: ast.stmt, call: ast.Call, op: str, cls: str) -> None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: QuerySite node plus EXECUTES, table access, FILTERS_ON and column writes
        #Complexity: Time O(n) - linear in statement nodes
        """
        site = self._b.add_node(NodeRecord("QuerySite", {"file": fn.module.path, "line": str(call.lineno), "op": op,
                                                         "dialect": "postgresql", "is_dynamic": False},
                                           fn.module.path, span_of(call)))
        def ev() -> list:
            return [evidence(EXTRACTOR, METHOD_ORM, fn.module, call)]

        table = NodeRef("Table", f"{SCHEMA}.{self.ctx.orm_tables[cls]}")
        kind = "READS_FROM" if op in _READ_OPS else "WRITES_TO"
        props = {"via": "orm"} if kind == "READS_FROM" else {"via": "orm", "op": op}
        self._b.add_edge(EdgeRecord("EXECUTES", fn.ref, site, ev()))
        for src in (site, fn.ref):
            self._b.add_edge(EdgeRecord(kind, src, table, ev(), props=dict(props)))
        filters, writes = self._column_refs(fn, stmt)
        for column in filters:
            self._b.add_edge(EdgeRecord("FILTERS_ON", site, column, ev()))
            self._b.add_edge(EdgeRecord("READS_FROM", site, column, ev(), props={"via": "orm"}))
        for column in writes:
            self._b.add_edge(EdgeRecord("WRITES_TO", site, column, ev(), props={"via": "orm", "op": op}))
            self._b.add_edge(EdgeRecord("WRITES_TO", fn.ref, column, ev(), props={"via": "orm", "op": op}))

    def _function_queries(self, fn: FunctionInfo) -> None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Find ORM query calls per simple statement of a function
        #Complexity: Time O(n) - linear in function nodes
        """
        scope = self.ctx.scope(fn.qname)
        for stmt in (n for n in body_nodes(fn.node) if isinstance(n, (ast.Expr, ast.Assign, ast.Return, ast.AnnAssign))):
            for call in (n for n in ast.walk(stmt) if isinstance(n, ast.Call)):
                target = self._query_target(fn, scope, call)
                if target:
                    self._query_site(fn, stmt, call, *target)

    def run(self) -> None:
        """
        #Feature: SQLAlchemy profile
        #Scenario: Map classes first, then scan every function for query sites
        #Complexity: Time O(N) - linear in AST nodes
        """
        for cls in self.ctx.index.classes.values():
            self._mapped_class(cls)
        if not self.ctx.orm_tables:
            return
        for fn in self.ctx.index.functions.values():
            self._function_queries(fn)
        logger.info("SQLAlchemy pass done", extra={"tables": len(self.ctx.orm_tables),
                                                   "columns": len(self.ctx.orm_columns)})
