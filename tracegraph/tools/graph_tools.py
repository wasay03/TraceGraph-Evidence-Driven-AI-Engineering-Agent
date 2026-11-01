import asyncio
from typing import Any, Literal

from pydantic import Field, TypeAdapter, ValidationError

from tracegraph.constants import agent as a
from tracegraph.engine import ir
from tracegraph.errors import Errors
from tracegraph.sandbox.run_sandbox import read_at_commit
from tracegraph.schemas.impact import InvariantCheckRequest
from tracegraph.tools.common import ToolInput, ask, node_line, resolve_ref, select_key
from tracegraph.tools.registry import ToolContext, ToolOutput, ToolSpec

ANY_PHASE = frozenset(a.LLM_PHASES)
# Plan works from the compiled analysis, so exploration tools are not offered there (they only burn model turns).
DISCOVERY = frozenset({a.PHASE_INTAKE, a.PHASE_DISCOVER, a.PHASE_ANALYZE})
ANALYSIS = frozenset({a.PHASE_DISCOVER, a.PHASE_ANALYZE})
VERIFYING = frozenset({a.PHASE_DISCOVER, a.PHASE_ANALYZE, a.PHASE_IMPLEMENT})


class RefInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Single node reference by exact natural key
    #Complexity: Time O(1) - constant
    """

    ref: str = Field(min_length=1, description="Exact natural key, e.g. app.services.calculate_total")


class ResolveInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Free text and optional node types
    #Complexity: Time O(1) - constant
    """

    text: str = Field(min_length=1)
    types: list[str] = Field(default_factory=list, description="Node type names, exactly as in the ontology: Class, "
                             "Function, Method, Attribute, EnumMember, Table, Column, Endpoint, Test, Module. "
                             "Callable covers Function and Method.")


class NeighborsInput(RefInput):
    """
    #Feature: Tool catalog
    #Scenario: One labelled hop (edge name, or inverse name for the reverse direction)
    #Complexity: Time O(1) - constant
    """

    edge: str = Field(min_length=1)


class ReachInput(RefInput):
    """
    #Feature: Tool catalog
    #Scenario: Regular path query from a node
    #Complexity: Time O(1) - constant
    """

    rpq: str = Field(default="CALLS*", min_length=1)
    max_hops: int = Field(default=8, ge=1, le=16)
    target_types: list[str] = Field(default_factory=list)


class DependentsInput(RefInput):
    """
    #Feature: Tool catalog
    #Scenario: Reverse reachability with stop types (PRD 9.1 example)
    #Complexity: Time O(1) - constant
    """

    via: str = "(CALLED_BY|INJECTED_BY)*"
    stop_at: list[str] = Field(default_factory=lambda: ["Endpoint"])
    min_tier: Literal["asserted", "observed", "derived", "inferred"] = "asserted"
    max_hops: int = Field(default=8, ge=1, le=16)


class PathsInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Witness paths between two nodes
    #Complexity: Time O(1) - constant
    """

    source: str
    target: str
    rpq: str = "(CALLS|INJECTS|HANDLED_BY|READS_FROM|WRITES_TO|MAPS_TO|READS_ATTR)*"
    k: int = Field(default=3, ge=1, le=10)


class RefsInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Several node references
    #Complexity: Time O(1) - constant
    """

    refs: list[str] = Field(min_length=1, max_length=20)


class UntestedInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Scope type for three-valued "untested" negation
    #Complexity: Time O(1) - constant
    """

    scope_type: str = "Endpoint"
    key_prefix: str | None = None


class QueryInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Raw IR for run_query (budgeted)
    #Complexity: Time O(1) - constant
    """

    query: dict[str, Any]


class InvariantInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Invariant ids to check (all when empty)
    #Complexity: Time O(1) - constant
    """

    invariants: list[str] = Field(default_factory=list)


class EvidenceInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Answer handle to expand
    #Complexity: Time O(1) - constant
    """

    handle: str = Field(pattern=r"^ans_[0-9a-f]{32}$")


class SourceInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Source of a node (by key) or of a file line range
    #Complexity: Time O(1) - constant
    """

    ref: str | None = None
    path: str | None = None
    start: int = Field(default=1, ge=1)
    end: int | None = Field(default=None, ge=1)


async def describe_ontology(ctx: ToolContext, args: ToolInput) -> ToolOutput:
    """
    #Feature: Tool catalog (meta)
    #Scenario: Node types with keys and edge types with signatures
    #Complexity: Time O(n + e) - registry size
    """
    r = ctx.graph.registry
    nodes = [f"{t.name}<{t.parent}> key={t.key}" for t in r.node_types if not t.abstract]
    edges = [f"{e.name}/{e.inverse}: " + ", ".join(f"{d}->{g}" for d, g in e.signatures) for e in r.edge_types]
    return ToolOutput("Node types:\n  " + "\n  ".join(nodes) + "\nEdge types (name/inverse):\n  " + "\n  ".join(edges))


async def resolve_entity(ctx: ToolContext, args: ResolveInput) -> ToolOutput:
    """
    #Feature: Tool catalog (discovery)
    #Scenario: Ranked candidates for free text; never commits to one
    #Complexity: Time O(n) - scan
    """
    return await ask(ctx, ir.Resolve(text=args.text, types=args.types, limit=10), f"candidates for {args.text!r}")


async def get_node(ctx: ToolContext, args: RefInput) -> ToolOutput:
    """
    #Feature: Tool catalog (discovery)
    #Scenario: Node props and location
    #Complexity: Time O(n) - lookup
    """
    node = resolve_ref(ctx, args.ref)
    props = ", ".join(f"{k}={v}" for k, v in sorted(node.props.items()) if v not in (None, [], ""))
    holes = [h["kind"] for h in ctx.graph.holes.get(node.id, [])]
    return ToolOutput(f"{node.type} {node.key} ({node.file}:{node.line_start}-{node.line_end}) tier={node.tier}\n"
                      f"  {props}" + (f"\n  coverage holes: {holes}" if holes else ""))


async def get_source(ctx: ToolContext, args: SourceInput) -> ToolOutput:
    """
    #Feature: Tool catalog (discovery)
    #Scenario: Source lines of a node or file range at the snapshot commit
    #Complexity: Time O(s) - file size

    Raises:
        Errors.HTTP.BadRequest: When neither ref nor path is given.
    """
    if args.ref:
        node = resolve_ref(ctx, args.ref)
        path, start, end = node.file, node.line_start or 1, node.line_end
    elif args.path:
        path, start, end = args.path, args.start, args.end
    else:
        raise Errors.HTTP.BadRequest("Pass either ref or path.")
    if not path:
        raise Errors.HTTP.BadRequest(f"{args.ref} has no source location.")
    lines = await asyncio.to_thread(read_at_commit, ctx.repo_path, ctx.state.commit or "HEAD", path)
    stop = min(end or len(lines), len(lines), start + 200)
    return ToolOutput(f"{path}:{start}-{stop}\n" + "\n".join(f"{i:5} {lines[i - 1]}" for i in range(start, stop + 1)))


async def get_evidence(ctx: ToolContext, args: EvidenceInput) -> ToolOutput:
    """
    #Feature: Tool catalog (discovery)
    #Scenario: Derivation paths and source spans behind an answer handle
    #Complexity: Time O(d) - derivations
    """
    try:
        report = await ctx.services.impact.get_report(args.handle)
        lines = [f"{f.cls} {f.node.key}: " + " -> ".join(p.type for p in f.path) + " | "
                 + ", ".join(f"{e.file}:{e.lines[0]}" for e in f.evidence) for f in report.findings[:40]]
        return ToolOutput("\n".join(lines) or "no findings", args.handle)
    except Errors.HTTP.NotFound:
        answer = await ctx.services.query.get_answer(args.handle)
    lines = [f"row {d.row}: " + " -> ".join(f"{p.src} -[{p.type}]-> {p.dst}" for p in d.path) + " | "
             + ", ".join(f"{e.file}:{e.lines[0]}-{e.lines[1]}" for e in d.evidence) for d in answer.derivations[:40]]
    return ToolOutput("\n".join(lines) or "no derivations (anchor rows)", args.handle)


async def get_neighbors(ctx: ToolContext, args: NeighborsInput) -> ToolOutput:
    """
    #Feature: Tool catalog (structural)
    #Scenario: One typed hop
    #Complexity: Time O(deg) - degree
    """
    node = resolve_ref(ctx, args.ref)
    return await ask(ctx, ir.Expand(input=select_key(node), edge=args.edge), f"{args.edge} of {node.key}")


async def get_callers(ctx: ToolContext, args: RefInput) -> ToolOutput:
    """
    #Feature: Tool catalog (structural)
    #Scenario: Direct callers
    #Complexity: Time O(deg) - degree
    """
    node = resolve_ref(ctx, args.ref, ("Callable",))
    return await ask(ctx, ir.Expand(input=select_key(node), edge="CALLED_BY"), f"callers of {node.key}")


async def get_callees(ctx: ToolContext, args: RefInput) -> ToolOutput:
    """
    #Feature: Tool catalog (structural)
    #Scenario: Direct callees
    #Complexity: Time O(deg) - degree
    """
    node = resolve_ref(ctx, args.ref, ("Callable",))
    return await ask(ctx, ir.Expand(input=select_key(node), edge="CALLS"), f"callees of {node.key}")


async def reachable_from(ctx: ToolContext, args: ReachInput) -> ToolOutput:
    """
    #Feature: Tool catalog (structural)
    #Scenario: RPQ from a node
    #Complexity: Time O((n + e) * q)
    """
    node = resolve_ref(ctx, args.ref)
    query = ir.Reach(input=select_key(node), rpq=args.rpq, max_hops=args.max_hops, target_types=args.target_types)
    return await ask(ctx, query, f"{args.rpq} from {node.key}")


async def find_dependents(ctx: ToolContext, args: DependentsInput) -> ToolOutput:
    """
    #Feature: Tool catalog (structural)
    #Scenario: Transitive dependents up to endpoints (handlers lifted to their Endpoint)
    #Complexity: Time O((n + e) * q)
    """
    node = resolve_ref(ctx, args.ref)
    anchor = select_key(node)
    callables = ir.Reach(input=anchor, rpq=args.via, max_hops=args.max_hops, min_tier=args.min_tier,
                         target_types=["Callable"], include_start=True)
    endpoints = ir.Reach(input=anchor, rpq=f"{args.via} . HANDLED_BY^-1", max_hops=args.max_hops + 1,
                         min_tier=args.min_tier, target_types=args.stop_at)
    return await ask(ctx, ir.Union_(inputs=[callables, endpoints]), f"dependents of {node.key}")


async def trace_paths(ctx: ToolContext, args: PathsInput) -> ToolOutput:
    """
    #Feature: Tool catalog (structural)
    #Scenario: k shortest witness paths
    #Complexity: Time bounded by the path budget
    """
    src, dst = resolve_ref(ctx, args.source), resolve_ref(ctx, args.target)
    out = await ask(ctx, ir.Paths(source=select_key(src), target=select_key(dst), rpq=args.rpq, k=args.k),
                    f"paths {src.key} -> {dst.key}")
    answer = await ctx.services.query.get_answer(out.handle)
    paths = ["  " + " -> ".join([d.path[0].src] + [f"[{p.type}] {p.dst}" for p in d.path]) for d in answer.derivations]
    return ToolOutput(out.text + "\n" + "\n".join(paths), out.handle, out.data)


async def find_cycles(ctx: ToolContext, args: ToolInput) -> ToolOutput:
    """
    #Feature: Tool catalog (structural)
    #Scenario: Import cycles
    #Complexity: Time O(n + e)
    """
    return await ask(ctx, ir.SCC(input=ir.Select(type="Module"), edge="IMPORTS"), "import cycles")


async def inspect_table(ctx: ToolContext, args: RefInput) -> ToolOutput:
    """
    #Feature: Tool catalog (data)
    #Scenario: Columns of a table (with nullability) and the classes mapped to it
    #Complexity: Time O(deg) - degree
    """
    table = resolve_ref(ctx, args.ref if "." in args.ref else f"public.{args.ref}", ("Table",))
    out = await ask(ctx, ir.Expand(input=select_key(table), edge="HAS_COLUMN"), f"columns of {table.key}")
    columns = [n for n in ctx.graph.of_type("Column") if n.props.get("table") == table.props.get("name")]
    detail = "\n".join(f"  {c.key}: {c.props.get('sql_type')} nullable={c.props.get('nullable')} "
                       f"db_nullable={c.props.get('db_nullable')} pk={c.props.get('is_pk')}" for c in columns)
    return ToolOutput(out.text + "\n" + detail, out.handle, out.data)


async def column_usage(ctx: ToolContext, args: RefInput) -> ToolOutput:
    """
    #Feature: Tool catalog (data)
    #Scenario: Callables and query sites reading, writing, filtering, mapping or assuming a column
    #Complexity: Time O((n + e) * q)
    """
    column = resolve_ref(ctx, args.ref, ("Column",))
    rpq = "(READ_BY|WRITTEN_BY|FILTERED_BY) . EXECUTED_BY? | MAPPED_BY . (ATTR_READ_BY|ATTR_WRITTEN_BY|ASSUMED_NOT_NULL_BY|BRANCHED_ON_BY)"
    return await ask(ctx, ir.Reach(input=select_key(column), rpq=rpq, max_hops=3), f"usage of {column.key}")


async def get_endpoint(ctx: ToolContext, args: RefInput) -> ToolOutput:
    """
    #Feature: Tool catalog (interface)
    #Scenario: Handler, DTOs and dependencies of an endpoint ("POST /orders")
    #Complexity: Time O(deg) - degree
    """
    ep = resolve_ref(ctx, args.ref, ("Endpoint",))
    rpq = "HANDLED_BY | ACCEPTS | RESPONDS_WITH | HANDLED_BY . INJECTS+"
    return await ask(ctx, ir.Reach(input=select_key(ep), rpq=rpq, max_hops=4), f"endpoint {ep.key}")


async def tests_for(ctx: ToolContext, args: RefsInput) -> ToolOutput:
    """
    #Feature: Tool catalog (tests)
    #Scenario: Tests reaching the given nodes directly or through callers
    #Complexity: Time O((n + e) * q)
    """
    anchors = [select_key(resolve_ref(ctx, r)) for r in args.refs]
    source = anchors[0] if len(anchors) == 1 else ir.Union_(inputs=anchors)
    return await ask(ctx, ir.Reach(input=source, rpq="CALLED_BY* . TESTED_BY", target_types=["Test"]), "tests")


async def untested(ctx: ToolContext, args: UntestedInput) -> ToolOutput:
    """
    #Feature: Tool catalog (tests)
    #Scenario: Scope nodes no test reaches; each row TRUE or UNKNOWN (three-valued negation)
    #Complexity: Time O(|scope| * (n + e) * q)
    """
    scope = ir.Select(type=args.scope_type)
    rpq = "HANDLED_BY . CALLED_BY* . TESTED_BY" if args.scope_type == "Endpoint" else "CALLED_BY* . TESTED_BY"
    out = await ask(ctx, ir.NotExists(scope=scope, rpq=rpq, target_types=["Test"]), f"untested {args.scope_type}")
    if args.key_prefix:
        kept = [line for line in out.text.splitlines()[1:] if f" {args.key_prefix}" in line]
        return ToolOutput("\n".join([out.text.splitlines()[0], *kept]), out.handle, out.data)
    return out


async def run_query(ctx: ToolContext, args: QueryInput) -> ToolOutput:
    """
    #Feature: Tool catalog (reasoning)
    #Scenario: Any IR query (PRD 7.2), budgeted
    #Complexity: Time per query
    """
    try:
        query = TypeAdapter(ir.Query).validate_python(args.query)
    except ValidationError as exc:
        raise Errors.HTTP.BadRequest(f"Invalid IR: {exc.errors()[:3]}") from exc
    return await ask(ctx, query, f"query {query.op}")


async def check_invariants(ctx: ToolContext, args: InvariantInput) -> ToolOutput:
    """
    #Feature: Tool catalog (invariants)
    #Scenario: Invariant violations on the base snapshot
    #Complexity: Time cost of the invariants
    """
    request = InvariantCheckRequest(repo_id=ctx.graph.repo_id, invariants=args.invariants)
    result = await ctx.services.impact.check_invariants(request)
    lines = [f"invariants {result.checked}: truth={result.truth}"]
    lines += [f"  {v.invariant} [{v.truth}] {node_line({'node': v.node.model_dump()})}: {v.message}" for v in result.violations]
    return ToolOutput("\n".join(lines), data={"truth": result.truth})


def _spec(name: str, group: str, phases: frozenset[str], model: type, handler, description: str,
          query: bool = False) -> ToolSpec:
    """
    #Feature: Tool catalog
    #Scenario: Read-only tool spec shorthand
    #Complexity: Time O(1) - constant
    """
    return ToolSpec(name, "1.0.0", group, a.SIDE_READ, phases, model, handler, description, counts_as_query=query)


GRAPH_TOOLS: list[ToolSpec] = [
    _spec("describe_ontology", a.GROUP_META, DISCOVERY, ToolInput, describe_ontology, "Node and edge types."),
    _spec("resolve_entity", a.GROUP_META, DISCOVERY, ResolveInput, resolve_entity,
          "Ranked candidate nodes for free text; returns exact keys to use with other tools."),
    _spec("get_node", a.GROUP_META, DISCOVERY, RefInput, get_node, "Properties, location and coverage holes of a node."),
    _spec("get_source", a.GROUP_META, ANY_PHASE, SourceInput, get_source,
          "Source lines of a node or file range at the snapshot commit."),
    _spec("get_evidence", a.GROUP_META, ANY_PHASE, EvidenceInput, get_evidence,
          "Derivation paths and source spans behind an answer handle."),
    _spec("get_neighbors", a.GROUP_STRUCTURAL, ANALYSIS, NeighborsInput, get_neighbors,
          "One hop along an edge (use the inverse name, e.g. CALLED_BY, for reverse)."),
    _spec("get_callers", a.GROUP_STRUCTURAL, VERIFYING, RefInput, get_callers,
          "Direct callers of a Function or Method (not a class)."),
    _spec("get_callees", a.GROUP_STRUCTURAL, VERIFYING, RefInput, get_callees,
          "Direct callees of a Function or Method (not a class)."),
    _spec("reachable_from", a.GROUP_STRUCTURAL, ANALYSIS, ReachInput, reachable_from,
          "Regular path query from a node, e.g. rpq='(CALLS|INJECTS)* . WRITES_TO'."),
    _spec("find_dependents", a.GROUP_STRUCTURAL, VERIFYING, DependentsInput, find_dependents,
          "Transitive callers/injectors of a node up to endpoints."),
    _spec("trace_paths", a.GROUP_STRUCTURAL, ANALYSIS, PathsInput, trace_paths, "Witness paths between two nodes."),
    _spec("find_cycles", a.GROUP_STRUCTURAL, ANALYSIS, ToolInput, find_cycles, "Import cycles."),
    _spec("inspect_table", a.GROUP_DOMAIN, ANALYSIS, RefInput, inspect_table,
          "Columns, nullability (ORM and database) and mapped classes of a table."),
    _spec("column_usage", a.GROUP_DOMAIN, ANALYSIS, RefInput, column_usage,
          "Query sites and callables that read, write, filter or assume a Column (ref like orders.status, not a class)."),
    _spec("get_endpoint", a.GROUP_DOMAIN, ANALYSIS, RefInput, get_endpoint, "Handler, DTOs and dependencies."),
    _spec("tests_for", a.GROUP_DOMAIN, VERIFYING | {a.PHASE_PLAN}, RefsInput, tests_for, "Tests reaching the given nodes."),
    _spec("untested", a.GROUP_DOMAIN, ANALYSIS, UntestedInput, untested,
          "Nodes no test reaches; UNKNOWN where coverage holes intervene."),
    _spec("run_query", a.GROUP_REASONING, ANALYSIS, QueryInput, run_query,
          "Run any typed IR query (select, reach, paths, not_exists, forall, aggregate, rank, scc).", query=True),
    _spec("check_invariants", a.GROUP_REASONING, VERIFYING, InvariantInput, check_invariants,
          "Invariant violations INV-002..INV-008 on the base snapshot."),
]
