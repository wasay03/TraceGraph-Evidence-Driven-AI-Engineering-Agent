from typing import Any, Literal

from pydantic import Field, TypeAdapter, ValidationError

from tracegraph.constants import agent as a
from tracegraph.engine import ir
from tracegraph.errors import Errors
from tracegraph.tools.common import ToolInput, ask, resolve_ref, select_key
from tracegraph.tools.registry import ToolContext, ToolOutput, ToolSpec

_QUERY = TypeAdapter(ir.Query)
_DISCOVER = frozenset({a.PHASE_DISCOVER})
_ANALYSIS = frozenset({a.PHASE_DISCOVER, a.PHASE_ANALYZE})
_ANALYZE = frozenset({a.PHASE_ANALYZE})
_VERIFYING = frozenset({a.PHASE_ANALYZE, a.PHASE_IMPLEMENT})
# A caller's dependents up to the endpoints that handle them (handlers lifted to their Endpoint).
_TO_ENDPOINTS = "(CALLED_BY|INJECTED_BY)* . HANDLED_BY^-1"
_DATA_TO_CODE = "(MAPS_TO^-1)? . (ATTR_READ_BY|ATTR_WRITTEN_BY|ASSUMES_NOT_NULL^-1|READ_BY|WRITTEN_BY)"


class RefInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Single node reference by exact natural key
    #Complexity: Time O(1) - constant
    """

    ref: str = Field(min_length=1, description="Exact natural key, e.g. app.models.Order")


class RefsInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Several exact natural keys
    #Complexity: Time O(1) - constant
    """

    refs: list[str] = Field(min_length=1, max_length=20, description="Exact natural keys of callables, attributes or columns")


class NoInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Tool without arguments
    #Complexity: Time O(1) - constant
    """


class AggregateInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Count nodes reached along an RPQ per group node
    #Complexity: Time O(1) - constant
    """

    group_type: str = Field(description="Node type of the groups, e.g. Table")
    rpq: str = Field(description="Path from each group, e.g. WRITTEN_BY")
    target_types: list[str] = Field(default_factory=list)
    fn: Literal["count", "count_distinct"] = "count_distinct"
    limit: int = Field(default=20, ge=1, le=200)


class ForAllInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Does every node of a type (optionally with a key prefix) reach a target along an RPQ
    #Complexity: Time O(1) - constant
    """

    scope_type: str = Field(description="e.g. Endpoint")
    rpq: str = Field(description="e.g. HANDLED_BY . CALLED_BY* . TESTED_BY")
    target_types: list[str] = Field(default_factory=list)
    key_prefix: str | None = None


class WhyNotInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: A reach, expand or paths query in IR and the key that was expected in its result
    #Complexity: Time O(1) - constant
    """

    query: dict[str, Any] = Field(description='IR, e.g. {"op": "reach", "input": {"op": "select", "type": "Endpoint", '
                                  '"where": {"key": "POST /orders"}}, "rpq": "HANDLED_BY . CALLS*"}')
    expected: str = Field(min_length=1)


class CompareInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: One IR query on two snapshots, or on the current snapshot and an overlay of ChangeSpecs
    #Complexity: Time O(1) - constant
    """

    query: dict[str, Any]
    snapshot_a: int | None = Field(default=None, ge=1, description="Omit for the run's snapshot")
    snapshot_b: int | None = Field(default=None, ge=1, description="Omit for the run's snapshot")
    changes: list[dict[str, Any]] = Field(default_factory=list, description="ChangeSpecs applied on top of snapshot_b")


class DeriveInput(ToolInput):
    """
    #Feature: Tool catalog
    #Scenario: Rule pack and or inline DSL rules
    #Complexity: Time O(1) - constant
    """

    rule_pack: str | None = Field(default="core", description="rules/derive/<name>.tg; core has endpoint_writes, "
                                  "endpoint_reads, tested_callable, tested_endpoint, untested_writer")
    rules: str | None = Field(default=None, description='Extra rules, e.g. p(E) :- Endpoint(E), HANDLED_BY(E, H).')
    predicates: list[str] = Field(default_factory=list)


def _ir(raw: dict[str, Any]) -> Any:
    """
    #Feature: Tool catalog
    #Scenario: Validate IR given by the model
    #Complexity: Time O(s) - query size

    Raises:
        Errors.HTTP.BadRequest: On invalid IR.
    """
    try:
        return _QUERY.validate_python(raw)
    except ValidationError as exc:
        raise Errors.HTTP.BadRequest(f"Invalid IR: {exc.errors()[:3]}") from exc


async def get_type_hierarchy(ctx: ToolContext, args: RefInput) -> ToolOutput:
    """
    #Feature: Tool catalog (structural)
    #Scenario: Ancestors, descendants and the methods of the class that override another
    #Complexity: Time O((n + e) * q)
    """
    node = resolve_ref(ctx, args.ref, ("Class",))
    anchor = select_key(node)
    query = ir.Union_(inputs=[ir.Reach(input=anchor, rpq="INHERITS+"), ir.Reach(input=anchor, rpq="INHERITED_BY+"),
                              ir.Reach(input=anchor, rpq="CONTAINS . OVERRIDES", target_types=["Method"])])
    return await ask(ctx, query, f"type hierarchy of {node.key} (ancestors, descendants, overridden methods)")


async def get_module_api(ctx: ToolContext, args: RefInput) -> ToolOutput:
    """
    #Feature: Tool catalog (structural)
    #Scenario: Public symbols a module defines, with signatures when the graph has them
    #Complexity: Time O(deg) - module members
    """
    node = resolve_ref(ctx, args.ref, ("Module",))
    out = await ask(ctx, ir.Expand(input=select_key(node), edge="CONTAINS"), f"public API of {node.key}")
    lines = out.text.splitlines()
    public = [line for line in lines[1:] if not line.split(" ", 2)[1].rsplit(".", 1)[-1].startswith("_")]
    by_key = {n.key: n for n in ctx.graph.nodes.values() if n.file == node.file}
    for i, line in enumerate(public):
        sig = by_key.get(line.split(" ", 2)[1]) if len(line.split(" ")) > 1 else None
        if sig is not None and sig.props.get("signature"):
            public[i] = f"{line} {sig.props['signature']}"
    return ToolOutput("\n".join([lines[0], *public]), out.handle, out.data)


async def migration_chain(ctx: ToolContext, args: NoInput) -> ToolOutput:
    """
    #Feature: Tool catalog (data)
    #Scenario: Migrations in PRECEDES order, the head, and any branch points (more than one successor)
    #Complexity: Time O(m) - migrations
    """
    out = await ask(ctx, ir.Select(type="Migration"), "migrations")
    migrations = {n.id: n for n in ctx.graph.of_type("Migration")}
    nxt = {m: [o for o, _ in ctx.graph.neighbors(m, ("PRECEDES", "fwd"), 4)] for m in migrations}
    has_parent = {o for outs in nxt.values() for o in outs}
    order, frontier = [], sorted((m for m in migrations if m not in has_parent), key=lambda m: migrations[m].key)
    while frontier:
        current = frontier.pop(0)
        order.append(current)
        frontier += [o for o in nxt[current] if o not in order]
    heads = [migrations[m].key for m in migrations if not nxt[m]]
    branches = [migrations[m].key for m in migrations if len(nxt[m]) > 1]
    lines = [f"migration chain ({len(order)}): " + " -> ".join(migrations[m].key for m in order),
             f"  head: {', '.join(heads) or 'none'}" + (" (multiple heads)" if len(heads) > 1 else "")]
    lines += [f"  branch point: {b}" for b in branches]
    return ToolOutput("\n".join(lines), out.handle, {"heads": heads})


async def check_schema_drift(ctx: ToolContext, args: NoInput) -> ToolOutput:
    """
    #Feature: Tool catalog (data)
    #Scenario: ORM vs migrated-schema mismatches (INV-004)
    #Complexity: Time O(columns)
    """
    return await ask(ctx, ir.Check(invariants=["INV-004"]), "schema drift (INV-004)")


async def endpoints_affected_by(ctx: ToolContext, args: RefsInput) -> ToolOutput:
    """
    #Feature: Tool catalog (interface)
    #Scenario: Endpoints whose handlers reach any of the refs; columns and attributes go through their accessors
    #Complexity: Time O((n + e) * q)
    """
    queries = []
    for ref in args.refs:
        node = resolve_ref(ctx, ref)
        is_data = any(ctx.graph.registry.is_subtype(node.type, t) for t in ("Column", "Table", "Attribute"))
        rpq = f"{_DATA_TO_CODE} . {_TO_ENDPOINTS}" if is_data else _TO_ENDPOINTS
        queries.append(ir.Reach(input=select_key(node), rpq=rpq, target_types=["Endpoint"]))
    query = queries[0] if len(queries) == 1 else ir.Union_(inputs=queries)
    return await ask(ctx, query, "endpoints affected")


async def aggregate(ctx: ToolContext, args: AggregateInput) -> ToolOutput:
    """
    #Feature: Tool catalog (reasoning)
    #Scenario: Per-group counts, ranked; lower_bound=True where coverage holes may hide more
    #Complexity: Time O(|groups| * (n + e) * q)
    """
    query = ir.Aggregate(groups=ir.Select(type=args.group_type), rpq=args.rpq, fn=args.fn,
                         target_types=args.target_types, limit=args.limit)
    return await ask(ctx, query, f"{args.fn} per {args.group_type} along {args.rpq}")


async def check_forall(ctx: ToolContext, args: ForAllInput) -> ToolOutput:
    """
    #Feature: Tool catalog (reasoning)
    #Scenario: TRUE, FALSE with counterexamples, or UNKNOWN where holes stand in the way
    #Complexity: Time O(|scope| * (n + e) * q)
    """
    scope: Any = ir.Select(type=args.scope_type)
    if args.key_prefix:
        keys = [n.key for n in ctx.graph.of_type(args.scope_type) if n.key.startswith(args.key_prefix)]
        if not keys:
            raise Errors.HTTP.BadRequest(f"No {args.scope_type} key starts with {args.key_prefix!r}.")
        selects = [ir.Select(type=args.scope_type, where={"key": k}) for k in keys]
        scope = selects[0] if len(selects) == 1 else ir.Union_(inputs=selects)
    query = ir.ForAll(scope=scope, rpq=args.rpq, target_types=args.target_types)
    return await ask(ctx, query, f"for all {args.scope_type}: {args.rpq}")


async def why_not(ctx: ToolContext, args: WhyNotInput) -> ToolOutput:
    """
    #Feature: Tool catalog (reasoning)
    #Scenario: Why an expected node is missing: filters, hop limit, coverage holes or candidate missing edges
    #Complexity: Time O(product graph size), capped
    """
    return await ask(ctx, ir.WhyNot(query=_ir(args.query), expected=args.expected), f"why not {args.expected}")


async def compare_snapshots(ctx: ToolContext, args: CompareInput) -> ToolOutput:
    """
    #Feature: Tool catalog (reasoning)
    #Scenario: Rows added and removed between two snapshots, or after hypothesized changes
    #Complexity: Time cost of two evaluations
    """
    query = ir.Diff(query=_ir(args.query), snapshot_a=args.snapshot_a, snapshot_b=args.snapshot_b, changes=args.changes)
    return await ask(ctx, query, "diff")


async def derive_relations(ctx: ToolContext, args: DeriveInput) -> ToolOutput:
    """
    #Feature: Tool catalog (reasoning)
    #Scenario: Derived tuples of a rule pack; rows with holes are UNKNOWN
    #Complexity: Time per stratum
    """
    query = ir.Derive(rule_pack=args.rule_pack, rules=args.rules, predicates=args.predicates)
    return await ask(ctx, query, f"derived {', '.join(args.predicates) or 'relations'}")


async def list_obligations(ctx: ToolContext, args: NoInput) -> ToolOutput:
    """
    #Feature: Tool catalog (impact)
    #Scenario: Obligations of the last simulate_change on this run
    #Complexity: Time O(o) - obligations

    Raises:
        Errors.HTTP.Conflict: When nothing was simulated yet.
    """
    impact = ctx.state.impact
    if not impact:
        raise Errors.HTTP.Conflict("No simulated change on this run yet; call simulate_change first.")
    lines = [f"obligations ({len(impact['obligations'])}):"]
    lines += [f"  {o['kind']}: {o['target']} - {o['detail']}" for o in impact["obligations"]]
    return ToolOutput("\n".join(lines), impact.get("handle"))


def _spec(name: str, group: str, phases: frozenset[str], model: type, handler, description: str) -> ToolSpec:
    """
    #Feature: Tool catalog
    #Scenario: Read-only tool spec shorthand
    #Complexity: Time O(1) - constant
    """
    return ToolSpec(name, "1.0.0", group, a.SIDE_READ, phases, model, handler, description)


REASONING_TOOLS: list[ToolSpec] = [
    _spec("get_type_hierarchy", a.GROUP_STRUCTURAL, _ANALYSIS, RefInput, get_type_hierarchy,
          "Ancestors, descendants and overriding methods of a class."),
    _spec("get_module_api", a.GROUP_STRUCTURAL, _DISCOVER, RefInput, get_module_api,
          "Public symbols of a module (key like app.services)."),
    _spec("migration_chain", a.GROUP_DOMAIN, _VERIFYING, NoInput, migration_chain,
          "Migrations in order, the head revision and branch points. Use the head as down_revision."),
    _spec("check_schema_drift", a.GROUP_DOMAIN, _VERIFYING, NoInput, check_schema_drift,
          "Columns whose ORM nullability differs from the migrated schema."),
    _spec("endpoints_affected_by", a.GROUP_DOMAIN, _ANALYZE, RefsInput, endpoints_affected_by,
          "HTTP endpoints whose handlers reach any of the given callables, attributes or columns."),
    _spec("aggregate", a.GROUP_REASONING, _ANALYZE, AggregateInput, aggregate,
          "Count nodes reached along an RPQ per group node, ranked. lower_bound=True means holes may hide more."),
    _spec("check_forall", a.GROUP_REASONING, _VERIFYING, ForAllInput, check_forall,
          "Whether every node of a type reaches a target: TRUE, FALSE with counterexamples, or UNKNOWN."),
    _spec("why_not", a.GROUP_REASONING, _ANALYZE, WhyNotInput, why_not,
          "Explain why an expected key is missing from a reach, expand or paths query."),
    _spec("compare_snapshots", a.GROUP_REASONING, _ANALYZE, CompareInput, compare_snapshots,
          "Rows a query gains or loses between snapshots, or after hypothesized ChangeSpecs."),
    _spec("derive_relations", a.GROUP_REASONING, _ANALYZE, DeriveInput, derive_relations,
          "Evaluate Datalog-style rules (rule pack core by default) and list the derived tuples."),
    _spec("list_obligations", a.GROUP_IMPACT, _ANALYZE, NoInput, list_obligations,
          "Obligations (migrations, annotations, tests) of the last simulate_change."),
]
