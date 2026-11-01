import ast
import logging

from tracegraph.constants.extract import METHOD_AST
from tracegraph.extract.ast_utils import call_name, const_str, keyword
from tracegraph.extract.context import AnalysisContext
from tracegraph.extract.index import FunctionInfo, ModuleInfo, evidence, span_of
from tracegraph.extract.records import EdgeRecord, NodeRecord, NodeRef

logger = logging.getLogger(__name__)

EXTRACTOR = "fastapi"
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
_APP_FACTORIES = {"APIRouter", "FastAPI"}
_AUTH_HINTS = ("auth", "user", "token", "current")


class FastApiPass:
    """
    #Feature: FastAPI profile (PRD 5.1 step 4)
    #Scenario: Route decorators -> Endpoint + HANDLED_BY; Depends -> INJECTS; response_model -> RESPONDS_WITH;
               pydantic body params -> ACCEPTS
    #Complexity: Time O(F * d) - functions times decorators
    """

    def __init__(self, ctx: AnalysisContext) -> None:
        """
        #Feature: FastAPI profile
        #Scenario: Bind to the analysis context
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When ctx is None.
        """
        if ctx is None:
            raise ValueError("[FastApiPass.__init__] 'ctx' is required.")
        self.ctx = ctx
        self._b = ctx.builder

    def _routers(self, module: ModuleInfo) -> dict[str, str]:
        """
        #Feature: FastAPI profile
        #Scenario: Module-level `name = APIRouter(prefix=...)` / `FastAPI()` -> prefix
        #Complexity: Time O(s) - linear in top-level statements
        """
        out = {}
        for item in module.tree.body:
            if isinstance(item, ast.Assign) and call_name(item.value) in _APP_FACTORIES:
                prefix = const_str(keyword(item.value, "prefix")) or ""
                out.update({t.id: prefix for t in item.targets if isinstance(t, ast.Name)})
        return out

    def _ref_of(self, fn: FunctionInfo, expr: ast.expr | None) -> NodeRef | None:
        """
        #Feature: FastAPI profile
        #Scenario: Repo class or function named by an expression in fn's module
        #Complexity: Time O(d * h) - resolution cost
        """
        if expr is None:
            return None
        qname = self.ctx.resolver.resolve_expr(fn.module, expr)
        index = self.ctx.index
        if qname in index.classes:
            return index.classes[qname].ref
        return index.functions[qname].ref if qname in index.functions else None

    def _injects(self, fn: FunctionInfo, seen: set[str]) -> list[str]:
        """
        #Feature: FastAPI profile
        #Scenario: INJECTS for Depends(x) parameter defaults, recursively through dependency functions
        #Complexity: Time O(D) - linear in the dependency tree
        """
        if fn.qname in seen:
            return []
        seen.add(fn.qname)
        names = []
        args = fn.node.args
        for default in [*args.defaults, *[d for d in args.kw_defaults if d is not None]]:
            if call_name(default) != "Depends" or not default.args:
                continue
            target = self.ctx.resolver.resolve_expr(fn.module, default.args[0])
            dep = self.ctx.index.functions.get(target or "")
            if dep is None:
                continue
            self._b.add_edge(EdgeRecord("INJECTS", fn.ref, dep.ref, [evidence(EXTRACTOR, METHOD_AST, fn.module, default)]))
            names.append(dep.qname)
            names += self._injects(dep, seen)
        return names

    def _accepts(self, fn: FunctionInfo, endpoint: NodeRef, node: ast.AST) -> None:
        """
        #Feature: FastAPI profile
        #Scenario: ACCEPTS for parameters annotated with a pydantic model
        #Complexity: Time O(p) - linear in parameters
        """
        for p in fn.params:
            cls = self.ctx.resolver.annotation_class(fn.module, p.annotation)
            if cls and self.ctx.index.is_subclass_of(cls, {"pydantic.BaseModel", "pydantic.main.BaseModel"}):
                self._b.add_edge(EdgeRecord("ACCEPTS", endpoint, self.ctx.index.classes[cls].ref,
                                            [evidence(EXTRACTOR, METHOD_AST, fn.module, node)]))

    def _endpoint(self, fn: FunctionInfo, decorator: ast.Call, method: str, prefix: str) -> None:
        """
        #Feature: FastAPI profile
        #Scenario: One Endpoint node and its handler, response model, body and dependency edges
        #Complexity: Time O(p + D) - parameters plus dependency tree
        """
        path = prefix + ((const_str(decorator.args[0]) if decorator.args else None) or "")
        status = keyword(decorator, "status_code")
        injected = self._injects(fn, set())
        auth = next((q for q in injected if any(h in q.rsplit(".", 1)[-1].lower() for h in _AUTH_HINTS)), None)
        endpoint = self._b.add_node(NodeRecord("Endpoint", {
            "method": method.upper(), "path": path or "/",
            "status_codes": [status.value] if isinstance(status, ast.Constant) else [],
            "auth_dependency": auth}, fn.module.path, span_of(decorator)))
        ev = [evidence(EXTRACTOR, METHOD_AST, fn.module, decorator)]
        self._b.add_edge(EdgeRecord("HANDLED_BY", endpoint, fn.ref, ev))
        response = self._ref_of(fn, keyword(decorator, "response_model")) or self._ref_of(fn, fn.node.returns)
        if response is not None and response.type == "Class":
            self._b.add_edge(EdgeRecord("RESPONDS_WITH", endpoint, response, list(ev)))
        self._accepts(fn, endpoint, decorator)

    def run(self) -> None:
        """
        #Feature: FastAPI profile
        #Scenario: Scan decorators of module-level functions against known routers
        #Complexity: Time O(F * d) - functions times decorators
        """
        routers = {m.qname: self._routers(m) for m in self.ctx.index.modules.values()}
        count = 0
        for fn in self.ctx.index.functions.values():
            for dec in fn.node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                owner = dec.func.value.id if isinstance(dec.func.value, ast.Name) else None
                if dec.func.attr in _HTTP_METHODS and owner in routers.get(fn.module.qname, {}):
                    self._endpoint(fn, dec, dec.func.attr, routers[fn.module.qname][owner])
                    count += 1
        logger.info("FastAPI pass done", extra={"endpoints": count})
