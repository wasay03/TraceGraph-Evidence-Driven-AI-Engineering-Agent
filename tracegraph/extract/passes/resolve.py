import ast
import logging
import sys

from tracegraph.constants.extract import (
    ABC_BASES,
    DYNAMIC_CALL_HOLES,
    EXCEPTION_BASES,
    HOLE_UNTYPED_RECEIVER,
    METHOD_RESOLVE,
    PYDANTIC_BASES,
)
from tracegraph.extract.context import AnalysisContext
from tracegraph.extract.index import ClassInfo, FunctionInfo, ModuleInfo, evidence, span_of
from tracegraph.extract.records import EdgeRecord, HoleRecord, NodeRecord, NodeRef
from tracegraph.extract.resolver import FunctionScope, dotted_name

logger = logging.getLogger(__name__)

EXTRACTOR = "resolve"
_STDLIB = frozenset(sys.stdlib_module_names) | {"__future__", "typing_extensions"}


class ResolvePass:
    """
    #Feature: Resolution pass (PRD 5.1 step 3)
    #Scenario: IMPORTS, USES_PACKAGE, INHERITS, OVERRIDES, DECORATED_BY, CALLS, INSTANTIATES, RAISES,
               CATCHES, READS_ATTR, WRITES_ATTR and coverage holes for unresolvable receivers
    #Complexity: Time O(N * r) - AST nodes times resolution cost
    """

    def __init__(self, ctx: AnalysisContext) -> None:
        """
        #Feature: Resolution pass
        #Scenario: Bind to the analysis context
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When ctx is None.
        """
        if ctx is None:
            raise ValueError("[ResolvePass.__init__] 'ctx' is required.")
        self.ctx = ctx
        self._b = ctx.builder
        self._method_names: set[str] = set()

    def _edge(self, kind: str, src: NodeRef, dst: NodeRef, module: ModuleInfo, node: ast.AST, **props: object) -> None:
        """
        #Feature: Resolution pass
        #Scenario: Add one edge with resolver evidence
        #Complexity: Time O(1) - constant
        """
        self._b.add_edge(EdgeRecord(kind, src, dst, [evidence(EXTRACTOR, METHOD_RESOLVE, module, node)],
                                    props={k: v for k, v in props.items() if v is not None}))

    def _ref(self, qname: str) -> NodeRef | None:
        """
        #Feature: Resolution pass
        #Scenario: Node ref of a repo module, class or function by qualified name
        #Complexity: Time O(1) - constant
        """
        i = self.ctx.index
        if qname in i.functions:
            return i.functions[qname].ref
        if qname in i.classes:
            return i.classes[qname].ref
        return i.modules[qname].ref if qname in i.modules else None

    # ---- module level -------------------------------------------------------------------

    def _imports(self, module: ModuleInfo) -> None:
        """
        #Feature: Resolution pass
        #Scenario: IMPORTS to repo modules/symbols; USES_PACKAGE for third-party top-level packages
        #Complexity: Time O(a) - linear in import aliases
        """
        nodes = [n for n in ast.walk(module.tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        for node in nodes:
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                target = module.imports.get(local)
                if target is None:
                    continue
                canonical = self.ctx.resolver.canonical(target)
                ref = self._ref(canonical)
                if ref is not None and ref != module.ref:
                    self._edge("IMPORTS", module.ref, ref, module, node, alias=alias.asname)
                elif ref is None and canonical.split(".")[0] not in _STDLIB and not self._is_repo(canonical):
                    pkg = self._b.add_node(NodeRecord("ExternalPackage", {"name": canonical.split(".")[0]}))
                    self._edge("USES_PACKAGE", module.ref, pkg, module, node)

    def _is_repo(self, qname: str) -> bool:
        """
        #Feature: Resolution pass
        #Scenario: Whether the top-level package of a name belongs to the repository
        #Complexity: Time O(m) - linear in modules
        """
        top = qname.split(".")[0]
        return any(m == top or m.startswith(top + ".") for m in self.ctx.index.modules)

    def _inheritance(self, cls: ClassInfo) -> None:
        """
        #Feature: Resolution pass
        #Scenario: INHERITS edges with MRO index; record base names (repo or external) for flag checks
        #Complexity: Time O(b) - linear in bases
        """
        for position, base in enumerate(cls.node.bases):
            qname = self.ctx.resolver.resolve_expr(cls.module, base) or dotted_name(base) or ast.unparse(base)
            cls.base_qnames.append(qname)
            if qname in self.ctx.index.classes:
                self._edge("INHERITS", cls.ref, self.ctx.index.classes[qname].ref, cls.module, base,
                           mro_index=position)

    def _class_flags(self, cls: ClassInfo) -> None:
        """
        #Feature: Resolution pass
        #Scenario: Enrich Class props that need the resolved hierarchy
        #Complexity: Time O(c) - linear in ancestors
        """
        index = self.ctx.index
        abstract = index.is_subclass_of(cls.qname, ABC_BASES) or any(
            "abstractmethod" in ast.unparse(d) for f in cls.methods.values() for d in index.functions[f].node.decorator_list)
        self._b.add_node(NodeRecord("Class", {
            "qualified_name": cls.qname, "is_pydantic": index.is_subclass_of(cls.qname, PYDANTIC_BASES),
            "is_exception": index.is_subclass_of(cls.qname, EXCEPTION_BASES), "is_abstract": abstract}))

    def _overrides(self, cls: ClassInfo) -> None:
        """
        #Feature: Resolution pass
        #Scenario: OVERRIDES from a method to the nearest same-named method up the MRO
        #Complexity: Time O(m * c) - methods times ancestors
        """
        index = self.ctx.index
        ancestors = index.mro(cls.qname)[1:]
        for name, qname in cls.methods.items():
            base = next((index.classes[a].methods[name] for a in ancestors if name in index.classes[a].methods), None)
            if base:
                fn = index.functions[qname]
                self._edge("OVERRIDES", fn.ref, index.functions[base].ref, cls.module, fn.node)

    def _decorators(self, owner: NodeRef, module: ModuleInfo, decorators: list[ast.expr]) -> None:
        """
        #Feature: Resolution pass
        #Scenario: DECORATED_BY to repo callables, in decorator order
        #Complexity: Time O(d) - linear in decorators
        """
        for order, dec in enumerate(decorators):
            target = dec.func if isinstance(dec, ast.Call) else dec
            qname = self.ctx.resolver.resolve_expr(module, target)
            if qname in self.ctx.index.functions:
                self._edge("DECORATED_BY", owner, self.ctx.index.functions[qname].ref, module, dec, order=order)

    # ---- function bodies ----------------------------------------------------------------

    def _hole(self, fn: FunctionInfo, kind: str, node: ast.AST, **detail: object) -> None:
        """
        #Feature: Coverage map
        #Scenario: Record an extraction hole inside a function
        #Complexity: Time O(1) - constant
        """
        self._b.add_hole(HoleRecord(kind, fn.module.path, span_of(node), fn.ref, tuple(sorted(detail.items()))))

    def _call_target(self, fn: FunctionInfo, scope: FunctionScope, call: ast.Call, awaited: bool) -> None:
        """
        #Feature: Resolution pass
        #Scenario: Exact CALLS/INSTANTIATES, dispatch candidates for overrides, holes for dynamic or untyped calls
        #Complexity: Time O(s) - linear in subclasses for dispatch candidates
        """
        index, module = self.ctx.index, fn.module
        name = dotted_name(call.func) or ""
        hole_kind = DYNAMIC_CALL_HOLES.get(name) or DYNAMIC_CALL_HOLES.get(self.ctx.resolver.resolve(module, name) or "")
        if hole_kind:
            self._hole(fn, hole_kind, call, call=name)
            return
        target = self.ctx.types.callee(scope, call.func)
        if target in index.classes:
            self._edge("INSTANTIATES", fn.ref, index.classes[target].ref, module, call)
            target = index.find_method(target, "__init__")
        if target in index.functions:
            self._edge("CALLS", fn.ref, index.functions[target].ref, module, call, resolution="exact",
                       is_await=awaited or None)
            self._dispatch_candidates(fn, scope, call, target, awaited)
        elif target is None and isinstance(call.func, ast.Attribute) and call.func.attr in self._method_names:
            if self.ctx.resolver.resolve_expr(module, call.func) is None:
                self._hole(fn, HOLE_UNTYPED_RECEIVER, call, method=call.func.attr)

    def _dispatch_candidates(self, fn: FunctionInfo, scope: FunctionScope, call: ast.Call, target: str,
                             awaited: bool) -> None:
        """
        #Feature: Resolution pass
        #Scenario: Calls on a typed receiver may dispatch to overrides in subclasses (class-hierarchy analysis)
        #Complexity: Time O(s) - linear in subclasses
        """
        if not isinstance(call.func, ast.Attribute):
            return
        owner = self.ctx.types.expr_class(scope, call.func.value)
        if owner is None:
            return
        index = self.ctx.index
        for sub in index.subclasses(owner):
            override = index.classes[sub].methods.get(call.func.attr)
            if override and override != target:
                self._edge("CALLS", fn.ref, index.functions[override].ref, fn.module, call,
                           resolution="dispatch_candidate", is_await=awaited or None)

    def _exception_classes(self, module: ModuleInfo, expr: ast.expr | None) -> list[ClassInfo]:
        """
        #Feature: Resolution pass
        #Scenario: Repo exception classes named by raise X / raise X(...) / except (A, B)
        #Complexity: Time O(k) - linear in named types
        """
        if expr is None:
            return []
        exprs = expr.elts if isinstance(expr, ast.Tuple) else [expr.func if isinstance(expr, ast.Call) else expr]
        names = (self.ctx.resolver.resolve_expr(module, e) for e in exprs)
        return [self.ctx.index.classes[q] for q in names if q in self.ctx.index.classes]

    def _attribute_access(self, fn: FunctionInfo, scope: FunctionScope, node: ast.Attribute) -> None:
        """
        #Feature: Resolution pass
        #Scenario: READS_ATTR / WRITES_ATTR on attributes of statically typed receivers
        #Complexity: Time O(c) - linear in ancestors
        """
        owner = self.ctx.types.expr_class(scope, node.value)
        attr = self.ctx.index.find_attribute(owner, node.attr) if owner else None
        if attr is not None:
            kind = "WRITES_ATTR" if isinstance(node.ctx, (ast.Store, ast.Del)) else "READS_ATTR"
            self._edge(kind, fn.ref, attr.ref, fn.module, node)

    def _function_body(self, fn: FunctionInfo) -> None:
        """
        #Feature: Resolution pass
        #Scenario: Walk one function body (nested defs are attributed to it) and emit body-level edges
        #Complexity: Time O(n * r) - nodes times resolution cost
        """
        scope = self.ctx.scope(fn.qname)
        awaited = {id(n.value) for n in ast.walk(fn.node) if isinstance(n, ast.Await)}
        for node in ast.walk(fn.node):
            if isinstance(node, ast.Call):
                self._call_target(fn, scope, node, id(node) in awaited)
            elif isinstance(node, ast.Attribute):
                self._attribute_access(fn, scope, node)
            elif isinstance(node, ast.Raise):
                for cls in self._exception_classes(fn.module, node.exc):
                    self._edge("RAISES", fn.ref, cls.ref, fn.module, node)
            elif isinstance(node, ast.ExceptHandler):
                for cls in self._exception_classes(fn.module, node.type):
                    self._edge("CATCHES", fn.ref, cls.ref, fn.module, node)

    def run(self) -> None:
        """
        #Feature: Resolution pass
        #Scenario: Module imports, then the class hierarchy, then function bodies (which need the MRO)
        #Complexity: Time O(N * r) - AST nodes times resolution cost
        """
        index = self.ctx.index
        self._method_names = {name for cls in index.classes.values() for name in cls.methods}
        for module in index.modules.values():
            self._imports(module)
        for cls in index.classes.values():
            self._inheritance(cls)
        for cls in index.classes.values():
            self._class_flags(cls)
            self._overrides(cls)
            self._decorators(cls.ref, cls.module, cls.node.decorator_list)
        for fn in index.functions.values():
            self._decorators(fn.ref, fn.module, fn.node.decorator_list)
            self._function_body(fn)
        logger.info("Resolution pass done", extra={"functions": len(index.functions)})
