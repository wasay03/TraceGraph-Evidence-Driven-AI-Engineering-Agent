import ast
import logging
from dataclasses import dataclass, field

from tracegraph.constants.extract import METHOD_AST
from tracegraph.extract.ast_utils import body_nodes, call_name, const_str
from tracegraph.extract.context import AnalysisContext
from tracegraph.extract.index import AttrInfo, FunctionInfo, evidence
from tracegraph.extract.records import EdgeRecord, NodeRecord, NodeRef
from tracegraph.extract.resolver import FunctionScope, dotted_name

logger = logging.getLogger(__name__)

EXTRACTOR = "facts"
_VALIDATORS = {"field_validator", "validator"}
_STATEMENT_LISTS = ("body", "orelse", "finalbody")
_KIND_PRIORITY = {"call_on_value": 0, "arithmetic": 1, "subscript": 2, "attribute_access": 3}


@dataclass(slots=True)
class Branch:
    """
    #Feature: Facts pass
    #Scenario: Values one function compares an attribute against, and whether a default path exists
    #Complexity: Time O(1) - constant
    """

    attr: AttrInfo
    node: ast.AST
    values: list[str] = field(default_factory=list)
    members: list[NodeRef] = field(default_factory=list)
    has_default: bool = False


def _guarded(fn: ast.AST) -> set[str]:
    """
    #Feature: Facts pass
    #Scenario: Dotted expressions None-checked or truth-tested anywhere in the function (flow-insensitive)
    #Complexity: Time O(n) - linear in function nodes
    """
    guarded: set[str] = set()
    tests = [n.test for n in ast.walk(fn) if isinstance(n, (ast.If, ast.While, ast.IfExp, ast.Assert))]
    tests += [v for n in ast.walk(fn) if isinstance(n, ast.BoolOp) for v in n.values]
    for test in tests:
        for node in ast.walk(test):
            if isinstance(node, ast.Compare) and any(isinstance(c, ast.Constant) and c.value is None
                                                     for c in node.comparators):
                guarded.add(dotted_name(node.left) or "")
            elif isinstance(node, (ast.Name, ast.Attribute)) and node is test:
                guarded.add(dotted_name(node) or "")
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                guarded.add(dotted_name(node.operand) or "")
            elif call_name(node) == "isinstance" and node.args:
                guarded.add(dotted_name(node.args[0]) or "")
    return guarded - {""}


def _dereferences(fn: ast.AST) -> list[tuple[ast.expr, str]]:
    """
    #Feature: Facts pass
    #Scenario: Expressions whose value is used as if non-null: v.m(), v + 1, v[i], v.x (that priority per expression)
    #Complexity: Time O(n log n) - linear in function nodes plus a sort
    """
    found: dict[int, tuple[ast.expr, str]] = {}
    for node in body_nodes(fn):
        pairs: list[tuple[ast.expr, str]] = []
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            pairs.append((node.func.value, "call_on_value"))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, (ast.Attribute, ast.Name)):
            pairs.append((node.value, "attribute_access"))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv)):
            pairs += [(side, "arithmetic") for side in (node.left, node.right) if isinstance(side, ast.Attribute)]
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            pairs.append((node.value, "subscript"))
        for expr, kind in pairs:
            if id(expr) not in found or _KIND_PRIORITY[kind] < _KIND_PRIORITY[found[id(expr)][1]]:
                found[id(expr)] = (expr, kind)
    return sorted(found.values(), key=lambda p: (p[0].lineno, p[0].col_offset, _KIND_PRIORITY[p[1]]))


def _returns_none(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """
    #Feature: Facts pass
    #Scenario: never / some_paths / always / unknown from return statements, fall-through and annotation
    #Complexity: Time O(n) - linear in function nodes
    """
    returns = [n for n in body_nodes(fn) if isinstance(n, ast.Return)]
    if any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in body_nodes(fn)):
        return "unknown"
    valued = [r for r in returns if r.value is not None and not (isinstance(r.value, ast.Constant) and r.value.value is None)]
    falls_off = not fn.body or not isinstance(fn.body[-1], (ast.Return, ast.Raise))
    annotated_optional = fn.returns is not None and "None" in ast.unparse(fn.returns)
    if not valued:
        return "always"
    if len(valued) < len(returns) or falls_off or annotated_optional:
        return "some_paths"
    return "never"


class FactsPass:
    """
    #Feature: Intra-procedural facts (PRD 5.1 step 7, D10)
    #Scenario: ASSUMES_NOT_NULL, BRANCHES_ON (with compared values and default-branch flag), returns_none,
               pydantic VALIDATES
    #Complexity: Time O(N) - linear in AST nodes
    """

    def __init__(self, ctx: AnalysisContext) -> None:
        """
        #Feature: Facts pass
        #Scenario: Bind to the analysis context
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When ctx is None.
        """
        if ctx is None:
            raise ValueError("[FactsPass.__init__] 'ctx' is required.")
        self.ctx = ctx
        self._b = ctx.builder

    def _attr_of(self, scope: FunctionScope, expr: ast.expr) -> AttrInfo | None:
        """
        #Feature: Facts pass
        #Scenario: Repo attribute denoted by receiver.attr when the receiver type is known
        #Complexity: Time O(c) - linear in ancestors
        """
        if not isinstance(expr, ast.Attribute):
            return None
        owner = self.ctx.types.expr_class(scope, expr.value)
        return self.ctx.index.find_attribute(owner, expr.attr) if owner else None

    def _nullable_candidate(self, attr: AttrInfo) -> bool:
        """
        #Feature: Facts pass
        #Scenario: Attributes whose nullability is data, not wiring: ORM-mapped columns or Optional annotations
        #Complexity: Time O(1) - constant
        """
        if (attr.owner, attr.name) in self.ctx.orm_columns:
            return True
        text = ast.unparse(attr.annotation) if attr.annotation is not None else ""
        return "None" in text or text.startswith("Optional")

    def _not_null(self, fn: FunctionInfo, scope: FunctionScope) -> None:
        """
        #Feature: Facts pass
        #Scenario: Unguarded dereference of a mapped/Optional attribute value, or of an Optional parameter
        #Complexity: Time O(n) - linear in function nodes
        """
        guarded, seen = _guarded(fn.node), set()
        optional_params = {p.name: p for p in fn.params if p.annotation is not None
                           and "None" in ast.unparse(p.annotation)}
        for expr, kind in _dereferences(fn.node):
            if (dotted_name(expr) or "") in guarded:
                continue
            attr = self._attr_of(scope, expr)
            attr = attr if attr is not None and self._nullable_candidate(attr) else None
            target = attr.ref if attr else (optional_params[expr.id].ref if isinstance(expr, ast.Name)
                                            and expr.id in optional_params else None)
            if target is not None and target not in seen:
                seen.add(target)
                self._b.add_edge(EdgeRecord("ASSUMES_NOT_NULL", fn.ref, target,
                                            [evidence(EXTRACTOR, METHOD_AST, fn.module, expr)],
                                            props={"guard_kind": kind}))

    def _compared(self, fn: FunctionInfo, scope: FunctionScope, test: ast.expr) -> list[tuple[AttrInfo, ast.expr]]:
        """
        #Feature: Facts pass
        #Scenario: (attribute, compared expression) pairs in a branch test
        #Complexity: Time O(t) - linear in test nodes
        """
        out = []
        for node in (n for n in ast.walk(test) if isinstance(n, ast.Compare)):
            attr = self._attr_of(scope, node.left)
            for comp in node.comparators if attr else []:
                out += [(attr, e) for e in (comp.elts if isinstance(comp, (ast.Tuple, ast.List, ast.Set)) else [comp])]
        return out

    def _value_label(self, fn: FunctionInfo, expr: ast.expr) -> tuple[str, NodeRef | None]:
        """
        #Feature: Facts pass
        #Scenario: Label of a compared value; enum members resolve to their EnumMember node
        #Complexity: Time O(d) - resolution cost
        """
        if isinstance(expr, ast.Constant):
            return ("None" if expr.value is None else repr(expr.value)), None
        if isinstance(expr, ast.Attribute):
            owner = self.ctx.resolver.resolve_expr(fn.module, expr.value)
            cls = self.ctx.index.classes.get(owner or "")
            if cls is not None and expr.attr in cls.enum_members:
                return expr.attr, cls.enum_members[expr.attr]
        return ast.unparse(expr)[:80], None

    def _if_chain(self, fn: FunctionInfo, scope: FunctionScope, node: ast.If, has_next: bool,
                  out: dict[NodeRef, Branch]) -> None:
        """
        #Feature: Facts pass
        #Scenario: if/elif/else chain; default exists when there is an else or code after the chain
        #Complexity: Time O(c) - chain length
        """
        current, has_default = node, has_next
        while True:
            for attr, value in self._compared(fn, scope, current.test):
                label, member = self._value_label(fn, value)
                branch = out.setdefault(attr.ref, Branch(attr, node))
                branch.values.append(label)
                branch.members += [member] if member else []
            if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
                current = current.orelse[0]
                continue
            has_default = has_default or bool(current.orelse)
            break
        for branch in out.values():
            if branch.node is node:
                branch.has_default = branch.has_default or has_default

    def _match(self, fn: FunctionInfo, scope: FunctionScope, node: ast.Match, out: dict[NodeRef, Branch]) -> None:
        """
        #Feature: Facts pass
        #Scenario: match subject.attr: case Enum.X ... case _
        #Complexity: Time O(c) - number of cases
        """
        attr = self._attr_of(scope, node.subject)
        if attr is None:
            return
        branch = out.setdefault(attr.ref, Branch(attr, node))
        for case in node.cases:
            if isinstance(case.pattern, ast.MatchValue):
                label, member = self._value_label(fn, case.pattern.value)
                branch.values.append(label)
                branch.members += [member] if member else []
            elif isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None:
                branch.has_default = True

    def _branches(self, fn: FunctionInfo, scope: FunctionScope) -> None:
        """
        #Feature: Facts pass
        #Scenario: BRANCHES_ON to attributes and to each compared enum member
        #Complexity: Time O(n) - linear in function nodes
        """
        out: dict[NodeRef, Branch] = {}
        holders = [fn.node, *(n for n in body_nodes(fn.node) if any(hasattr(n, f) for f in _STATEMENT_LISTS))]
        for holder in holders:
            for name in _STATEMENT_LISTS:
                stmts = getattr(holder, name, None) or []
                for i, stmt in enumerate(stmts if isinstance(stmts, list) else []):
                    if isinstance(stmt, ast.If) and not (holder is not fn.node and name == "orelse" and len(stmts) == 1
                                                         and isinstance(holder, ast.If)):
                        self._if_chain(fn, scope, stmt, i < len(stmts) - 1, out)
                    elif isinstance(stmt, ast.Match):
                        self._match(fn, scope, stmt, out)
        for branch in out.values():
            ev = [evidence(EXTRACTOR, METHOD_AST, fn.module, branch.node)]
            props = {"compared_values": sorted(set(branch.values)), "has_default": branch.has_default}
            self._b.add_edge(EdgeRecord("BRANCHES_ON", fn.ref, branch.attr.ref, ev, props=dict(props)))
            for member in branch.members:
                self._b.add_edge(EdgeRecord("BRANCHES_ON", fn.ref, member, list(ev), props=dict(props)))

    def _validators(self, fn: FunctionInfo) -> None:
        """
        #Feature: Facts pass
        #Scenario: @field_validator("a", "b") on a pydantic method -> VALIDATES from method and class
        #Complexity: Time O(d) - linear in decorators
        """
        cls = self.ctx.index.classes.get(fn.class_qname or "")
        for dec in (d for d in fn.node.decorator_list if call_name(d) in _VALIDATORS) if cls else []:
            for name in filter(None, (const_str(a) for a in dec.args)):
                attr = cls.attributes.get(name)
                if attr is None:
                    continue
                ev = [evidence(EXTRACTOR, METHOD_AST, fn.module, dec)]
                for src in (fn.ref, cls.ref):
                    self._b.add_edge(EdgeRecord("VALIDATES", src, attr.ref, list(ev),
                                                props={"validator_kind": call_name(dec)}))

    def run(self) -> None:
        """
        #Feature: Facts pass
        #Scenario: All facts for every indexed function
        #Complexity: Time O(N) - linear in AST nodes
        """
        for fn in self.ctx.index.functions.values():
            scope = self.ctx.scope(fn.qname)
            self._not_null(fn, scope)
            self._branches(fn, scope)
            self._validators(fn)
            self._b.add_node(NodeRecord(fn.ref.type, {"qualified_name": fn.qname,
                                                      "returns_none": _returns_none(fn.node)}))
        logger.info("Facts pass done", extra={"functions": len(self.ctx.index.functions)})
