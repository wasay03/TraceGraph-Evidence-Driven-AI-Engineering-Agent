import ast
from dataclasses import dataclass, field

from tracegraph.extract.records import EvidenceRecord, NodeRef, Span
from tracegraph.utilities.ids import content_hash


@dataclass(slots=True)
class ModuleInfo:
    """
    #Feature: Program index
    #Scenario: Parsed module with its import aliases and top-level definitions
    #Complexity: Time O(1) - constant
    """

    qname: str
    path: str
    source: str
    tree: ast.Module
    is_test: bool
    is_package: bool
    lines: list[str] = field(default_factory=list)
    imports: dict[str, str] = field(default_factory=dict)
    symbols: dict[str, str] = field(default_factory=dict)

    @property
    def ref(self) -> NodeRef:
        """
        #Feature: Program index
        #Scenario: Graph ref of this module
        #Complexity: Time O(1) - constant
        """
        return NodeRef("Module", self.qname)


@dataclass(slots=True)
class ParamInfo:
    """
    #Feature: Program index
    #Scenario: One parameter of a callable
    #Complexity: Time O(1) - constant
    """

    name: str
    position: int
    kind: str
    annotation: ast.expr | None
    has_default: bool
    ref: NodeRef


@dataclass(slots=True)
class AttrInfo:
    """
    #Feature: Program index
    #Scenario: Class-level or self-assigned attribute
    #Complexity: Time O(1) - constant
    """

    name: str
    annotation: ast.expr | None
    ref: NodeRef
    owner: str


@dataclass(slots=True)
class FunctionInfo:
    """
    #Feature: Program index
    #Scenario: Function or method definition with its parameters
    #Complexity: Time O(1) - constant
    """

    qname: str
    module: ModuleInfo
    node: ast.FunctionDef | ast.AsyncFunctionDef
    class_qname: str | None
    params: list[ParamInfo]
    ref: NodeRef


@dataclass(slots=True)
class ClassInfo:
    """
    #Feature: Program index
    #Scenario: Class definition; base_qnames is filled by the resolution pass
    #Complexity: Time O(1) - constant
    """

    qname: str
    module: ModuleInfo
    node: ast.ClassDef
    ref: NodeRef
    is_enum: bool = False
    methods: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, AttrInfo] = field(default_factory=dict)
    enum_members: dict[str, NodeRef] = field(default_factory=dict)
    base_qnames: list[str] = field(default_factory=list)


class ProgramIndex:
    """
    #Feature: Program index
    #Scenario: Whole-repo symbol tables shared by every pass after structure
    #Complexity: Time O(1) per lookup
    """

    def __init__(self) -> None:
        """
        #Feature: Program index
        #Scenario: Empty index
        #Complexity: Time O(1) - constant
        """
        self.modules: dict[str, ModuleInfo] = {}
        self.classes: dict[str, ClassInfo] = {}
        self.functions: dict[str, FunctionInfo] = {}
        self.module_by_path: dict[str, ModuleInfo] = {}

    def mro(self, class_qname: str) -> list[str]:
        """
        #Feature: Program index
        #Scenario: Depth-first, left-to-right ancestor order of repo classes (class itself first)
        #Complexity: Time O(c) - linear in ancestors
        """
        order: list[str] = []
        stack = [class_qname]
        while stack:
            current = stack.pop(0)
            if current in order or current not in self.classes:
                continue
            order.append(current)
            stack = self.classes[current].base_qnames + stack
        return order

    def find_method(self, class_qname: str, name: str) -> str | None:
        """
        #Feature: Program index
        #Scenario: Resolve a method through the class MRO
        #Complexity: Time O(c) - linear in ancestors
        """
        for qname in self.mro(class_qname):
            method = self.classes[qname].methods.get(name)
            if method:
                return method
        return None

    def find_attribute(self, class_qname: str, name: str) -> AttrInfo | None:
        """
        #Feature: Program index
        #Scenario: Resolve an attribute through the class MRO
        #Complexity: Time O(c) - linear in ancestors
        """
        for qname in self.mro(class_qname):
            attr = self.classes[qname].attributes.get(name)
            if attr:
                return attr
        return None

    def subclasses(self, class_qname: str) -> list[str]:
        """
        #Feature: Program index
        #Scenario: Transitive repo subclasses, used for dispatch candidates
        #Complexity: Time O(C * c) - classes times ancestors
        """
        return [q for q in self.classes if q != class_qname and class_qname in self.mro(q)]

    def is_subclass_of(self, class_qname: str, base_names: set[str]) -> bool:
        """
        #Feature: Program index
        #Scenario: Whether any ancestor (repo or external, by qualified name) is in base_names
        #Complexity: Time O(c) - linear in ancestors
        """
        return any(b in base_names for q in self.mro(class_qname) for b in self.classes[q].base_qnames + [q])


def span_of(node: ast.AST) -> Span:
    """
    #Feature: Provenance
    #Scenario: Line span of an AST node
    #Complexity: Time O(1) - constant
    """
    start = getattr(node, "lineno", 1)
    return Span(start, getattr(node, "end_lineno", None) or start)


def evidence(extractor: str, method: str, module: ModuleInfo, node: ast.AST, **extra: object) -> EvidenceRecord:
    """
    #Feature: Provenance
    #Scenario: Evidence pointing at the source lines of an AST node, with a snippet hash
    #Complexity: Time O(l) - linear in spanned lines
    """
    span = span_of(node)
    snippet = "\n".join(module.lines[span.start - 1 : span.end])
    return EvidenceRecord(extractor=extractor, method=method, file_path=module.path, span=span,
                          snippet_hash=content_hash(snippet), **extra)
