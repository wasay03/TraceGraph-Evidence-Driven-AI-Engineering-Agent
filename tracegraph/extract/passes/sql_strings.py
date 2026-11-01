import ast
import logging

import sqlglot
from sqlglot import exp

from tracegraph.constants.extract import HOLE_DYNAMIC_SQL, METHOD_SQL
from tracegraph.extract.ast_utils import body_nodes, call_name, const_str
from tracegraph.extract.context import AnalysisContext
from tracegraph.extract.index import FunctionInfo, evidence, span_of
from tracegraph.extract.passes.sqlalchemy import SCHEMA
from tracegraph.extract.records import EdgeRecord, HoleRecord, NodeRecord, NodeRef

logger = logging.getLogger(__name__)

EXTRACTOR = "sql"
DIALECT = "postgres"
_SQL_CALLS = {"text", "exec_driver_sql"}
_OPS = {exp.Select: "select", exp.Insert: "insert", exp.Update: "update", exp.Delete: "delete"}


def _parse(sql: str) -> tuple[str, set[str], set[tuple[str, str]], set[tuple[str, str]]] | None:
    """
    #Feature: SQL strings pass
    #Scenario: (op, tables, all columns, WHERE columns) of a literal statement; columns resolve aliases and
               default to the only table when unqualified
    #Complexity: Time O(s) - linear in SQL length
    """
    try:
        tree = sqlglot.parse_one(sql, read=DIALECT)
    except sqlglot.errors.ParseError:
        return None
    op = next((name for kind, name in _OPS.items() if isinstance(tree, kind)), None)
    if op is None:
        return None
    aliases = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    tables = set(aliases.values())

    def owner(col: exp.Column) -> str | None:
        return aliases.get(col.table) if col.table else (next(iter(tables)) if len(tables) == 1 else None)

    columns = {(owner(c), c.name) for c in tree.find_all(exp.Column) if owner(c)}
    where = tree.args.get("where")
    filters = {(owner(c), c.name) for c in where.find_all(exp.Column) if owner(c)} if where else set()
    return op, tables, columns, filters


class SqlStringsPass:
    """
    #Feature: SQL strings (PRD 5.1 step 5)
    #Scenario: text("...") literals -> QuerySite with tables/columns via sqlglot; f-strings, concatenation and
               format() -> is_dynamic QuerySite plus a dynamic_sql coverage hole
    #Complexity: Time O(N + S) - AST nodes plus SQL text
    """

    def __init__(self, ctx: AnalysisContext) -> None:
        """
        #Feature: SQL strings pass
        #Scenario: Bind to the analysis context
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When ctx is None.
        """
        if ctx is None:
            raise ValueError("[SqlStringsPass.__init__] 'ctx' is required.")
        self.ctx = ctx
        self._b = ctx.builder

    def _site(self, fn: FunctionInfo, call: ast.Call, op: str | None, dynamic: bool) -> NodeRef:
        """
        #Feature: SQL strings pass
        #Scenario: QuerySite node and EXECUTES edge
        #Complexity: Time O(1) - constant
        """
        site = self._b.add_node(NodeRecord("QuerySite", {"file": fn.module.path, "line": str(call.lineno), "op": op,
                                                         "dialect": DIALECT, "is_dynamic": dynamic},
                                           fn.module.path, span_of(call)))
        self._b.add_edge(EdgeRecord("EXECUTES", fn.ref, site, [evidence(EXTRACTOR, METHOD_SQL, fn.module, call)]))
        return site

    def _literal(self, fn: FunctionInfo, call: ast.Call, sql: str) -> None:
        """
        #Feature: SQL strings pass
        #Scenario: Edges for a parsed literal statement
        #Complexity: Time O(s) - linear in SQL length
        """
        parsed = _parse(sql)
        if parsed is None:
            return
        op, tables, columns, filters = parsed
        site = self._site(fn, call, op, dynamic=False)
        kind = "READS_FROM" if op == "select" else "WRITES_TO"
        props = {"via": "sql"} if kind == "READS_FROM" else {"via": "sql", "op": op}
        for table in tables:
            for src in (site, fn.ref):
                self._b.add_edge(EdgeRecord(kind, src, NodeRef("Table", f"{SCHEMA}.{table}"),
                                            [evidence(EXTRACTOR, METHOD_SQL, fn.module, call)], props=dict(props)))
        for table, column in columns:
            self._b.add_edge(EdgeRecord(kind, site, NodeRef("Column", f"{table}.{column}"),
                                        [evidence(EXTRACTOR, METHOD_SQL, fn.module, call)], props=dict(props)))
        for table, column in filters:
            self._b.add_edge(EdgeRecord("FILTERS_ON", site, NodeRef("Column", f"{table}.{column}"),
                                        [evidence(EXTRACTOR, METHOD_SQL, fn.module, call)]))

    def _function(self, fn: FunctionInfo) -> int:
        """
        #Feature: SQL strings pass
        #Scenario: Inspect text()/exec_driver_sql() calls in one function
        #Complexity: Time O(n) - linear in function nodes
        """
        count = 0
        for call in (n for n in body_nodes(fn.node) if isinstance(n, ast.Call) and call_name(n) in _SQL_CALLS):
            if not call.args:
                continue
            arg = call.args[0]
            sql = const_str(arg)
            if sql is not None:
                self._literal(fn, call, sql)
            elif isinstance(arg, (ast.JoinedStr, ast.BinOp)) or call_name(arg) == "format":
                self._site(fn, call, None, dynamic=True)
                self._b.add_hole(HoleRecord(HOLE_DYNAMIC_SQL, fn.module.path, span_of(call), fn.ref,
                                            (("expression", ast.unparse(arg)[:200]),)))
            count += 1
        return count

    def run(self) -> None:
        """
        #Feature: SQL strings pass
        #Scenario: All functions
        #Complexity: Time O(N + S) - AST nodes plus SQL text
        """
        total = sum(self._function(fn) for fn in self.ctx.index.functions.values())
        logger.info("SQL strings pass done", extra={"sql_sites": total})
