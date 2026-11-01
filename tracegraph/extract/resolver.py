import ast
from dataclasses import dataclass, field

from tracegraph.constants.extract import WRAPPER_TYPES
from tracegraph.extract.ast_utils import dotted_name
from tracegraph.extract.index import FunctionInfo, ModuleInfo, ProgramIndex

_MAX_HOPS = 12

__all__ = ["FunctionScope", "NameResolver", "TypeInference", "dotted_name"]


class NameResolver:
    """
    #Feature: Name resolution (in-house replacement for scip-python, PRD D8)
    #Scenario: Resolve names through module scopes, imports and package re-exports to canonical qualified names
    #Complexity: Time O(d * h) per lookup - depth times re-export hops
    """

    def __init__(self, index: ProgramIndex) -> None:
        """
        #Feature: Name resolution
        #Scenario: Bind to the program index
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When index is None.
        """
        if index is None:
            raise ValueError("[NameResolver.__init__] 'index' is required.")
        self.index = index

    def is_known(self, qname: str) -> bool:
        """
        #Feature: Name resolution
        #Scenario: Whether a qualified name is a repo module, class or function
        #Complexity: Time O(1) - constant
        """
        i = self.index
        return qname in i.modules or qname in i.classes or qname in i.functions

    def canonical(self, dotted: str) -> str:
        """
        #Feature: Name resolution
        #Scenario: Follow re-exports ("pkg.Order" defined in pkg.models) to the defining qualified name
        #Complexity: Time O(d * h) - depth times hops
        """
        for _ in range(_MAX_HOPS):
            if self.is_known(dotted):
                return dotted
            parts = dotted.split(".")
            step = None
            for cut in range(len(parts) - 1, 0, -1):
                module = self.index.modules.get(".".join(parts[:cut]))
                if module is not None:
                    head = parts[cut]
                    target = module.symbols.get(head) or module.imports.get(head)
                    step = ".".join([target, *parts[cut + 1:]]) if target and target != dotted else None
                    break
            if step is None or step == dotted:
                return dotted
            dotted = step
        return dotted

    def resolve(self, module: ModuleInfo, dotted: str) -> str | None:
        """
        #Feature: Name resolution
        #Scenario: Resolve a name as written in a module (local def or import alias); None for builtins/unknown
        #Complexity: Time O(d * h) - depth times hops
        """
        head, _, rest = dotted.partition(".")
        base = module.symbols.get(head) or module.imports.get(head)
        if base is None:
            return None
        return self.canonical(f"{base}.{rest}" if rest else base)

    def resolve_expr(self, module: ModuleInfo, expr: ast.expr) -> str | None:
        """
        #Feature: Name resolution
        #Scenario: Resolve a Name/Attribute expression
        #Complexity: Time O(d * h) - depth times hops
        """
        name = dotted_name(expr)
        return self.resolve(module, name) if name else None

    def annotation_class(self, module: ModuleInfo, annotation: ast.expr | None) -> str | None:
        """
        #Feature: Type resolution
        #Scenario: Repo class named by an annotation, unwrapping Optional/Mapped/Annotated/"X"/X | None
        #Complexity: Time O(a) - linear in annotation size
        """
        if annotation is None:
            return None
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                return self.annotation_class(module, ast.parse(annotation.value, mode="eval").body)
            except SyntaxError:
                return None
        if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            sides = [s for s in (annotation.left, annotation.right) if not _is_none(s)]
            return self.annotation_class(module, sides[0]) if len(sides) == 1 else None
        if isinstance(annotation, ast.Subscript):
            wrapper = (dotted_name(annotation.value) or "").split(".")[-1]
            inner = annotation.slice.elts[0] if isinstance(annotation.slice, ast.Tuple) else annotation.slice
            return self.annotation_class(module, inner) if wrapper in WRAPPER_TYPES else None
        qname = self.resolve_expr(module, annotation)
        return qname if qname in self.index.classes else None


def _is_none(expr: ast.expr) -> bool:
    """
    #Feature: Type resolution
    #Scenario: Literal None in an annotation
    #Complexity: Time O(1) - constant
    """
    return isinstance(expr, ast.Constant) and expr.value is None


@dataclass(slots=True)
class FunctionScope:
    """
    #Feature: Type resolution
    #Scenario: Local name -> repo class map for one function (flow-insensitive)
    #Complexity: Time O(1) per lookup
    """

    fn: FunctionInfo
    types: dict[str, str] = field(default_factory=dict)


class TypeInference:
    """
    #Feature: Type resolution
    #Scenario: Best-effort static types of receivers so method calls and attribute access resolve exactly
    #Complexity: Time O(n) per function - linear in its AST nodes
    """

    def __init__(self, resolver: NameResolver) -> None:
        """
        #Feature: Type resolution
        #Scenario: Bind to a resolver
        #Complexity: Time O(1) - constant
        """
        if resolver is None:
            raise ValueError("[TypeInference.__init__] 'resolver' is required.")
        self.r = resolver
        self.index = resolver.index

    def scope(self, fn: FunctionInfo) -> FunctionScope:
        """
        #Feature: Type resolution
        #Scenario: Seed types from self/cls and annotated params, then from local assignments
        #Complexity: Time O(n) - linear in function AST nodes
        """
        scope = FunctionScope(fn)
        for p in fn.params:
            cls = self.r.annotation_class(fn.module, p.annotation)
            if cls:
                scope.types[p.name] = cls
        if fn.class_qname and fn.params and fn.params[0].name in ("self", "cls"):
            scope.types[fn.params[0].name] = fn.class_qname
        for node in ast.walk(fn.node):
            self._learn(scope, node)
        return scope

    def _learn(self, scope: FunctionScope, node: ast.AST) -> None:
        """
        #Feature: Type resolution
        #Scenario: x = Cls(...), x: T = ..., with Cls() as x
        #Complexity: Time O(1) - constant per node
        """
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            cls = self.r.annotation_class(scope.fn.module, node.annotation) or (
                node.value is not None and self.expr_class(scope, node.value))
            if cls:
                scope.types[node.target.id] = cls
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            cls = self.expr_class(scope, node.value)
            if cls:
                scope.types.setdefault(node.targets[0].id, cls)
        elif isinstance(node, ast.withitem) and isinstance(node.optional_vars, ast.Name):
            cls = self.expr_class(scope, node.context_expr)
            if cls:
                scope.types[node.optional_vars.id] = cls

    def callee(self, scope: FunctionScope, func: ast.expr) -> str | None:
        """
        #Feature: Type resolution
        #Scenario: Statically named callee (function, class or Class.method) of a call expression
        #Complexity: Time O(d * h) - resolution cost
        """
        module = scope.fn.module
        if isinstance(func, ast.Name) and func.id not in scope.types:
            return self.r.resolve(module, func.id)
        if isinstance(func, ast.Attribute):
            qname = self.r.resolve_expr(module, func)
            if qname and self.r.is_known(qname):
                return qname
            owner = self.expr_class(scope, func.value)
            if owner:
                return self.index.find_method(owner, func.attr)
        return None

    def expr_class(self, scope: FunctionScope, expr: ast.expr) -> str | None:
        """
        #Feature: Type resolution
        #Scenario: Repo class of an expression value (names, attributes, constructor and annotated calls, await)
        #Complexity: Time O(d) - linear in expression depth
        """
        if isinstance(expr, ast.Await):
            return self.expr_class(scope, expr.value)
        if isinstance(expr, ast.Name):
            return scope.types.get(expr.id)
        if isinstance(expr, ast.Attribute):
            owner = self.expr_class(scope, expr.value)
            attr = self.index.find_attribute(owner, expr.attr) if owner else None
            if attr is not None:
                return self.r.annotation_class(self.index.classes[attr.owner].module, attr.annotation)
            return None
        if isinstance(expr, ast.Call):
            target = self.callee(scope, expr.func)
            if target in self.index.classes:
                return target
            fn = self.index.functions.get(target) if target else None
            return self.r.annotation_class(fn.module, fn.node.returns) if fn else None
        return None
