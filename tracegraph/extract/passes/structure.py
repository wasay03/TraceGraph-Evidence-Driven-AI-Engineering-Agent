import ast
import logging

from tracegraph.constants.extract import ENUM_BASES, HOLE_PARSE_ERROR, METHOD_AST
from tracegraph.extract.builder import GraphBuilder
from tracegraph.extract.index import (
    AttrInfo,
    ClassInfo,
    FunctionInfo,
    ModuleInfo,
    ParamInfo,
    ProgramIndex,
    evidence,
    span_of,
)
from tracegraph.extract.records import EdgeRecord, HoleRecord, NodeRecord, NodeRef, Span
from tracegraph.extract.source import SourceFile
from tracegraph.utilities.ids import content_hash

logger = logging.getLogger(__name__)

EXTRACTOR = "structure"
_METHOD_KINDS = {"staticmethod": "static", "classmethod": "class", "property": "property"}


def _relative_base(module: str, is_package: bool, level: int, target: str | None) -> str:
    """
    #Feature: Structure pass
    #Scenario: Resolve "from ..x import y" against the importing module's package
    #Complexity: Time O(d) - linear in package depth
    """
    package = module.split(".") if is_package else module.split(".")[:-1]
    base = package[: len(package) - (level - 1)] if level > 1 else package
    return ".".join([*base, target] if target else base)


def _record_imports(info: ModuleInfo, node: ast.Import | ast.ImportFrom) -> None:
    """
    #Feature: Structure pass
    #Scenario: Map local alias -> fully qualified imported name
    #Complexity: Time O(a) - linear in aliases
    """
    if isinstance(node, ast.Import):
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            info.imports[local] = alias.name if alias.asname else alias.name.split(".")[0]
        return
    base = _relative_base(info.qname, info.is_package, node.level, node.module) if node.level else node.module or ""
    for alias in node.names:
        if alias.name != "*":
            info.imports[alias.asname or alias.name] = f"{base}.{alias.name}" if base else alias.name


def _type_expr(builder: GraphBuilder, module: ModuleInfo, annotation: ast.expr) -> NodeRef:
    """
    #Feature: Structure pass
    #Scenario: TypeExpr node for an annotation, keyed by its normalised text
    #Complexity: Time O(a) - linear in annotation size
    """
    text = ast.unparse(annotation)
    names = sorted({n.id for n in ast.walk(annotation) if isinstance(n, ast.Name)}
                   | {n.attr for n in ast.walk(annotation) if isinstance(n, ast.Attribute)})
    is_union = "|" in text or text.startswith(("Union[", "typing.Union["))
    is_optional = text.startswith(("Optional[", "typing.Optional[")) or "None" in names or "None" in text
    return builder.add_node(NodeRecord("TypeExpr", {"text": text, "is_optional": is_optional,
                                                    "is_union": is_union, "base_names": names}))


class StructurePass:
    """
    #Feature: Structure pass (PRD 5.1 step 2)
    #Scenario: Modules, classes, functions, methods, parameters, attributes, variables, enum members, spans
    #Complexity: Time O(N) - linear in AST nodes

    Built on the stdlib ast module; it also fills the ProgramIndex used by every later pass.
    """

    def __init__(self, builder: GraphBuilder, index: ProgramIndex) -> None:
        """
        #Feature: Structure pass
        #Scenario: Bind to the shared builder and index
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When an argument is None.
        """
        if builder is None or index is None:
            raise ValueError("[StructurePass.__init__] 'builder' and 'index' are required.")
        self._b = builder
        self._index = index

    def _contains(self, module: ModuleInfo, parent: NodeRef, child: NodeRef, node: ast.AST) -> None:
        """
        #Feature: Structure pass
        #Scenario: CONTAINS edge with AST evidence
        #Complexity: Time O(1) - constant
        """
        self._b.add_edge(EdgeRecord("CONTAINS", parent, child, [evidence(EXTRACTOR, METHOD_AST, module, node)]))

    def _annotate(self, module: ModuleInfo, src: NodeRef, annotation: ast.expr | None, role: str) -> None:
        """
        #Feature: Structure pass
        #Scenario: ANNOTATED_AS edge from a parameter, attribute or callable to its TypeExpr
        #Complexity: Time O(a) - linear in annotation size
        """
        if annotation is None:
            return
        type_ref = _type_expr(self._b, module, annotation)
        self._b.add_edge(EdgeRecord("ANNOTATED_AS", src, type_ref, [evidence(EXTRACTOR, METHOD_AST, module, annotation)],
                                    props={"role": role}))

    def _params(self, module: ModuleInfo, fn: ast.FunctionDef | ast.AsyncFunctionDef, qname: str,
                owner: NodeRef) -> list[ParamInfo]:
        """
        #Feature: Structure pass
        #Scenario: Parameter nodes with kind, default and annotation, plus HAS_PARAM edges
        #Complexity: Time O(p) - linear in parameters
        """
        a = fn.args
        positional = [(x, "positional_only") for x in a.posonlyargs] + [(x, "positional_or_keyword") for x in a.args]
        defaults = [False] * (len(positional) - len(a.defaults)) + [True] * len(a.defaults)
        entries = [(x, k, d) for (x, k), d in zip(positional, defaults, strict=True)]
        entries += [(a.vararg, "var_positional", False)] if a.vararg else []
        entries += [(x, "keyword_only", d is not None) for x, d in zip(a.kwonlyargs, a.kw_defaults, strict=True)]
        entries += [(a.kwarg, "var_keyword", False)] if a.kwarg else []
        out = []
        for pos, (arg, kind, has_default) in enumerate(entries):
            text = ast.unparse(arg.annotation) if arg.annotation else None
            ref = self._b.add_node(NodeRecord("Parameter", {
                "callable_qname": qname, "position": pos, "name": arg.arg, "annotation": text,
                "has_default": has_default, "kind": kind, "is_optional": bool(text and "None" in text)},
                module.path, span_of(arg)))
            self._b.add_edge(EdgeRecord("HAS_PARAM", owner, ref, [evidence(EXTRACTOR, METHOD_AST, module, arg)],
                                        props={"position": pos}))
            self._annotate(module, ref, arg.annotation, "param")
            out.append(ParamInfo(arg.arg, pos, kind, arg.annotation, has_default, ref))
        return out

    def _function(self, module: ModuleInfo, fn: ast.FunctionDef | ast.AsyncFunctionDef, parent: NodeRef,
                  class_qname: str | None) -> None:
        """
        #Feature: Structure pass
        #Scenario: Function or Method node, its parameters and return annotation
        #Complexity: Time O(p) - linear in parameters
        """
        prefix = class_qname or module.qname
        qname = f"{prefix}.{fn.name}"
        props = {"qualified_name": qname, "name": fn.name, "is_async": isinstance(fn, ast.AsyncFunctionDef),
                 "return_annotation": ast.unparse(fn.returns) if fn.returns else None}
        if class_qname:
            decorators = {ast.unparse(d).split(".")[-1] for d in fn.decorator_list}
            props["kind"] = next((v for k, v in _METHOD_KINDS.items() if k in decorators), "instance")
        ref = self._b.add_node(NodeRecord("Method" if class_qname else "Function", props, module.path, span_of(fn)))
        self._contains(module, parent, ref, fn)
        self._annotate(module, ref, fn.returns, "return")
        params = self._params(module, fn, qname, ref)
        self._index.functions[qname] = FunctionInfo(qname, module, fn, class_qname, params, ref)
        if class_qname:
            self._index.classes[class_qname].methods[fn.name] = qname
        else:
            module.symbols[fn.name] = qname

    def _attribute(self, module: ModuleInfo, cls: ClassInfo, name: str, annotation: ast.expr | None,
                   default: ast.expr | None, node: ast.AST, inferred: ast.expr | None = None) -> None:
        """
        #Feature: Structure pass
        #Scenario: Attribute node of a class (class-level or assigned on self); first definition wins.
                   inferred is the annotation of the parameter assigned to it, used only for type resolution.
        #Complexity: Time O(1) - constant
        """
        if name in cls.attributes:
            return
        text = ast.unparse(annotation) if annotation is not None else None
        ref = self._b.add_node(NodeRecord("Attribute", {
            "owner_qname": cls.qname, "name": name, "annotation": text,
            "is_classvar": bool(text and "ClassVar" in text),
            "default": ast.unparse(default)[:200] if default is not None else None,
            "is_optional": bool(text and ("Optional" in text or "None" in text))}, module.path, span_of(node)))
        self._contains(module, cls.ref, ref, node)
        self._annotate(module, ref, annotation, "attr")
        cls.attributes[name] = AttrInfo(name, annotation if annotation is not None else inferred, ref, cls.qname)

    def _enum_member(self, module: ModuleInfo, cls: ClassInfo, name: str, value: ast.expr, node: ast.AST) -> None:
        """
        #Feature: Structure pass
        #Scenario: EnumMember node for NAME = value inside an Enum subclass
        #Complexity: Time O(1) - constant
        """
        ref = self._b.add_node(NodeRecord("EnumMember", {"enum_qname": cls.qname, "name": name,
                                                         "value": ast.unparse(value)[:200]}, module.path, span_of(node)))
        self._contains(module, cls.ref, ref, node)
        cls.enum_members[name] = ref

    def _self_attributes(self, module: ModuleInfo, cls: ClassInfo, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """
        #Feature: Structure pass
        #Scenario: Attributes created by self.x = ... or self.x: T = ... inside methods
        #Complexity: Time O(n) - linear in method AST nodes
        """
        param_types = {a.arg: a.annotation for a in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
                       if a.annotation is not None}
        for node in ast.walk(fn):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(
                node, ast.AnnAssign) else []
            value = getattr(node, "value", None)
            inferred = param_types.get(value.id) if isinstance(value, ast.Name) else None
            for t in targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                    self._attribute(module, cls, t.attr, getattr(node, "annotation", None), value, node, inferred)

    def _class_body_item(self, module: ModuleInfo, cls: ClassInfo, item: ast.stmt) -> None:
        """
        #Feature: Structure pass
        #Scenario: Dispatch one statement of a class body
        #Complexity: Time O(1) - constant per statement
        """
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._function(module, item, cls.ref, cls.qname)
        elif isinstance(item, ast.ClassDef):
            self._class(module, item, cls.ref, cls.qname)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            self._attribute(module, cls, item.target.id, item.annotation, item.value, item)
        elif isinstance(item, ast.Assign):
            for t in (t for t in item.targets if isinstance(t, ast.Name) and not t.id.startswith("__")):
                if cls.is_enum:
                    self._enum_member(module, cls, t.id, item.value, item)
                else:
                    self._attribute(module, cls, t.id, None, item.value, item)

    def _class(self, module: ModuleInfo, node: ast.ClassDef, parent: NodeRef, prefix: str) -> None:
        """
        #Feature: Structure pass
        #Scenario: Class node, its body and self-assigned attributes
        #Complexity: Time O(n) - linear in class AST nodes
        """
        qname = f"{prefix}.{node.name}"
        decorators = {ast.unparse(d).split(".")[-1].split("(")[0] for d in node.decorator_list}
        is_enum = any(ast.unparse(b).split(".")[-1] in ENUM_BASES for b in node.bases)
        ref = self._b.add_node(NodeRecord("Class", {"qualified_name": qname, "name": node.name, "is_enum": is_enum,
                                                    "is_dataclass": "dataclass" in decorators},
                                          module.path, span_of(node)))
        self._contains(module, parent, ref, node)
        cls = ClassInfo(qname, module, node, ref, is_enum=is_enum)
        self._index.classes[qname] = cls
        if prefix == module.qname:
            module.symbols[node.name] = qname
        for item in node.body:
            self._class_body_item(module, cls, item)
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._self_attributes(module, cls, item)

    def _variables(self, module: ModuleInfo, item: ast.Assign | ast.AnnAssign) -> None:
        """
        #Feature: Structure pass
        #Scenario: Module-level Variable nodes; UPPER_CASE names are constants
        #Complexity: Time O(t) - linear in assignment targets
        """
        targets = item.targets if isinstance(item, ast.Assign) else [item.target]
        ann = ast.unparse(item.annotation) if isinstance(item, ast.AnnAssign) else None
        for t in (t for t in targets if isinstance(t, ast.Name)):
            ref = self._b.add_node(NodeRecord("Variable", {"qualified_name": f"{module.qname}.{t.id}",
                                                           "is_constant": t.id.isupper(), "annotation": ann},
                                              module.path, span_of(item)))
            self._contains(module, module.ref, ref, item)
            module.symbols.setdefault(t.id, f"{module.qname}.{t.id}")

    def _module_item(self, module: ModuleInfo, item: ast.stmt) -> None:
        """
        #Feature: Structure pass
        #Scenario: Dispatch one top-level statement
        #Complexity: Time O(1) - constant per statement
        """
        if isinstance(item, (ast.Import, ast.ImportFrom)):
            _record_imports(module, item)
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._function(module, item, module.ref, None)
        elif isinstance(item, ast.ClassDef):
            self._class(module, item, module.ref, module.qname)
        elif isinstance(item, (ast.Assign, ast.AnnAssign)):
            self._variables(module, item)
        elif isinstance(item, (ast.If, ast.Try)):
            for child in [*item.body, *getattr(item, "orelse", []), *getattr(item, "finalbody", [])]:
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    _record_imports(module, child)

    def _signature_hash(self, module: ModuleInfo) -> str:
        """
        #Feature: Incremental indexing (PRD 5.4 step 2)
        #Scenario: Hash of the module's public API; a change forces importers to be re-resolved
        #Complexity: Time O(s) - linear in public symbols
        """
        parts = []
        for name, qname in sorted(module.symbols.items()):
            fn = self._index.functions.get(qname)
            cls = self._index.classes.get(qname)
            sig = ast.unparse(fn.node.args) + str(fn.node.returns and ast.unparse(fn.node.returns)) if fn else ""
            if cls:
                sig = ",".join(sorted(cls.methods) + sorted(cls.attributes) + sorted(cls.enum_members))
            parts.append(f"{name}:{sig}")
        return content_hash("\n".join(parts) + repr(sorted(module.imports.items())))

    def run(self, sources: list[SourceFile]) -> None:
        """
        #Feature: Structure pass
        #Scenario: Parse every file; parse errors become coverage holes instead of failing the snapshot
        #Complexity: Time O(N) - linear in AST nodes
        """
        for src in sources:
            try:
                tree = ast.parse(src.text, filename=src.path)
            except SyntaxError as exc:
                self._b.add_hole(HoleRecord(HOLE_PARSE_ERROR, src.path, Span(exc.lineno or 1, exc.lineno or 1),
                                            detail=(("message", str(exc.msg)),)))
                continue
            module = ModuleInfo(src.qname, src.path, src.text, tree, src.is_test, src.is_package,
                                lines=src.text.splitlines())
            self._index.modules[src.qname] = module
            self._index.module_by_path[src.path] = module
            for item in tree.body:
                self._module_item(module, item)
            self._b.add_node(NodeRecord("Module", {
                "qualified_name": src.qname, "path": src.path, "is_test": src.is_test,
                "is_package": src.is_package, "content_hash": src.sha,
                "signature_hash": self._signature_hash(module)}, src.path, Span(1, max(len(module.lines), 1))))
        logger.info("Structure pass done", extra={"modules": len(self._index.modules),
                                                  "functions": len(self._index.functions)})
