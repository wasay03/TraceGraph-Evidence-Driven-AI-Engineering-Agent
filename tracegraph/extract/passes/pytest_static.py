import ast
import logging

from tracegraph.constants.extract import METHOD_AST
from tracegraph.extract.ast_utils import body_nodes, const_str, keyword
from tracegraph.extract.context import AnalysisContext
from tracegraph.extract.index import FunctionInfo, ModuleInfo, evidence, span_of
from tracegraph.extract.records import EdgeRecord, NodeRecord, NodeRef

logger = logging.getLogger(__name__)

EXTRACTOR = "pytest"
STRENGTH_CALL = 1.0
STRENGTH_FIXTURE = 0.8
STRENGTH_IMPORT = 0.3


def _decorator_names(fn: FunctionInfo) -> list[str]:
    """
    #Feature: pytest pass
    #Scenario: Dotted decorator names without call parentheses: pytest.fixture, pytest.mark.parametrize
    #Complexity: Time O(d) - linear in decorators
    """
    return [ast.unparse(d.func if isinstance(d, ast.Call) else d) for d in fn.node.decorator_list]


def _is_test(fn: FunctionInfo) -> bool:
    """
    #Feature: pytest pass
    #Scenario: test_* functions, or test_* methods of Test* classes, in test modules
    #Complexity: Time O(1) - constant
    """
    if not fn.module.is_test or not fn.node.name.startswith("test"):
        return False
    return fn.class_qname is None or fn.class_qname.rsplit(".", 1)[-1].startswith("Test")


class PytestPass:
    """
    #Feature: Tests (PRD 5.1 step 8, static part)
    #Scenario: Test and Fixture nodes, USES_FIXTURE by parameter name, TESTS edges from direct calls (1.0),
               fixture calls (0.8) and module imports (0.3)
    #Complexity: Time O(T * n) - tests times body nodes
    """

    def __init__(self, ctx: AnalysisContext) -> None:
        """
        #Feature: pytest pass
        #Scenario: Bind to the analysis context
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When ctx is None.
        """
        if ctx is None:
            raise ValueError("[PytestPass.__init__] 'ctx' is required.")
        self.ctx = ctx
        self._b = ctx.builder

    def _fixtures(self) -> dict[str, list[FunctionInfo]]:
        """
        #Feature: pytest pass
        #Scenario: Fixture nodes keyed by fixture name
        #Complexity: Time O(F) - linear in functions
        """
        out: dict[str, list[FunctionInfo]] = {}
        for fn in self.ctx.index.functions.values():
            dec = next((d for d in fn.node.decorator_list
                        if ast.unparse(d.func if isinstance(d, ast.Call) else d).endswith("fixture")), None)
            if dec is None:
                continue
            scope = const_str(keyword(dec, "scope")) if isinstance(dec, ast.Call) else None
            self._b.add_node(NodeRecord("Fixture", {"qualified_name": fn.qname, "scope": scope or "function"},
                                        fn.module.path, span_of(fn.node)))
            out.setdefault(fn.node.name, []).append(fn)
        return out

    def _callees(self, fn: FunctionInfo) -> list[tuple[NodeRef, ast.Call]]:
        """
        #Feature: pytest pass
        #Scenario: Repo functions and classes a function calls directly
        #Complexity: Time O(n) - linear in body nodes
        """
        scope, index, out = self.ctx.scope(fn.qname), self.ctx.index, []
        for call in (n for n in body_nodes(fn.node) if isinstance(n, ast.Call)):
            target = self.ctx.types.callee(scope, call.func)
            if target in index.functions:
                out.append((index.functions[target].ref, call))
            elif target in index.classes:
                out.append((index.classes[target].ref, call))
        return out

    def _imported(self, module: ModuleInfo) -> list[NodeRef]:
        """
        #Feature: pytest pass
        #Scenario: Repo symbols a test module imports
        #Complexity: Time O(a) - linear in import aliases
        """
        index, refs = self.ctx.index, []
        for target in module.imports.values():
            qname = self.ctx.resolver.canonical(target)
            if qname in index.functions:
                refs.append(index.functions[qname].ref)
            elif qname in index.classes:
                refs.append(index.classes[qname].ref)
        return refs

    def _tests_edges(self, test: NodeRef, targets: list[tuple[NodeRef, ast.AST]], method: str, strength: float,
                     module: ModuleInfo) -> None:
        """
        #Feature: pytest pass
        #Scenario: TESTS edges with method and strength
        #Complexity: Time O(k) - linear in targets
        """
        for ref, node in targets:
            self._b.add_edge(EdgeRecord("TESTS", test, ref, [evidence(EXTRACTOR, METHOD_AST, module, node)],
                                        props={"method": method, "strength": strength}))

    def _test(self, fn: FunctionInfo, fixtures: dict[str, list[FunctionInfo]]) -> None:
        """
        #Feature: pytest pass
        #Scenario: One Test node with markers, fixtures and TESTS edges
        #Complexity: Time O(n) - linear in test and fixture bodies
        """
        parts = [fn.module.path, *([fn.class_qname.rsplit(".", 1)[-1]] if fn.class_qname else []), fn.node.name]
        markers = [d.split("pytest.mark.", 1)[1] for d in _decorator_names(fn) if "pytest.mark." in d]
        test = self._b.add_node(NodeRecord("Test", {"node_id": "::".join(parts), "markers": markers,
                                                    "is_parametrized": "parametrize" in markers},
                                           fn.module.path, span_of(fn.node)))
        self._tests_edges(test, [(fn.ref, fn.node)], "call", STRENGTH_CALL, fn.module)
        self._tests_edges(test, self._callees(fn), "call", STRENGTH_CALL, fn.module)
        for param in fn.params:
            for fixture in fixtures.get(param.name, []):
                self._b.add_edge(EdgeRecord("USES_FIXTURE", test, NodeRef("Fixture", fixture.qname),
                                            [evidence(EXTRACTOR, METHOD_AST, fn.module, fn.node)]))
                self._tests_edges(test, self._callees(fixture), "call", STRENGTH_FIXTURE, fixture.module)
        imported = [(ref, fn.node) for ref in self._imported(fn.module)]
        self._tests_edges(test, imported, "import", STRENGTH_IMPORT, fn.module)

    def run(self) -> None:
        """
        #Feature: pytest pass
        #Scenario: Fixtures first, then every test function
        #Complexity: Time O(T * n) - tests times body nodes
        """
        fixtures = self._fixtures()
        tests = [fn for fn in self.ctx.index.functions.values() if _is_test(fn)]
        for fn in tests:
            self._test(fn, fixtures)
        logger.info("pytest pass done", extra={"tests": len(tests), "fixtures": len(fixtures)})
