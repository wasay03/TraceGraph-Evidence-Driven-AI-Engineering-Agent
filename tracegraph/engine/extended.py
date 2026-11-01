from typing import Any

from pydantic import TypeAdapter

from tracegraph.constants.engine import TRUTH_FALSE, TRUTH_TRUE, TRUTH_UNKNOWN
from tracegraph.constants.graph import TIER_RANK
from tracegraph.engine import dsl, ir
from tracegraph.engine.datalog import RuleEngine, derived_result, evaluate_program, load_rule_pack
from tracegraph.engine.evaluator import EvalResult, Evaluator
from tracegraph.engine.graph import GraphSnapshot
from tracegraph.errors import Errors


def _pattern_literals(q: ir.Match) -> list[dsl.Literal]:
    """
    #Feature: Pattern matching (PRD 7.2 Match)
    #Scenario: Compile pattern nodes and edges to rule-body literals
    #Complexity: Time O(p) - pattern size
    """
    out: list[dsl.Literal] = []
    for node in q.nodes:
        var = dsl.Var(node.var)
        if node.type:
            out.append(dsl.Atom(node.type, (var,)))
        if node.key:
            out.append(dsl.Equals(var, "key", node.key))
        out += [dsl.PropTest(var, prop, value) for prop, value in node.where.items()]
    out += [dsl.ReachAtom(dsl.Var(e.src), dsl.Var(e.dst), e.rpq, e.max_hops) for e in q.edges]
    return out


def match(evaluator: Evaluator, q: ir.Match) -> EvalResult:
    """
    #Feature: Pattern matching
    #Scenario: Distinct bindings of a conjunctive pattern, with the joined witness paths
    #Complexity: Time O(product of literal fan-outs)

    Raises:
        Errors.Domain.QueryType: On an unknown type or a variable used by an edge but not declared.
    """
    declared = {n.var for n in q.nodes}
    evaluator._check_types([n.type for n in q.nodes if n.type])
    loose = {v for e in q.edges for v in (e.src, e.dst)} - declared
    if loose:
        raise Errors.Domain.QueryType(f"Pattern edges use undeclared variables {sorted(loose)}.", {"vars": sorted(loose)})
    engine = RuleEngine(evaluator, [])
    rows = engine.query_rows(dsl.QueryClause(tuple(_pattern_literals(q)), limit=q.limit))
    return EvalResult(rows=rows, truth=TRUTH_TRUE if rows else TRUTH_FALSE, truncated=engine.truncated)


def dsl_query(evaluator: Evaluator, q: ir.Dsl) -> EvalResult:
    """
    #Feature: Textual DSL (PRD 7.4)
    #Scenario: Rules from the optional pack, then the text's own rules and last query
    #Complexity: Time per stratum and join
    """
    pack = load_rule_pack(q.rule_pack) + "\n" if q.rule_pack else ""
    return evaluate_program(evaluator, pack + q.text)


def derive(evaluator: Evaluator, q: ir.Derive) -> EvalResult:
    """
    #Feature: Rule evaluation (PRD 7.2 Derive)
    #Scenario: Derived tuples of a rule pack and inline rules, optionally only some predicates
    #Complexity: Time per stratum

    Raises:
        Errors.Domain.QueryType: When neither a pack nor rules are given, or the text holds a query.
    """
    if not q.rule_pack and not q.rules:
        raise Errors.Domain.QueryType("Derive needs a rule_pack or rules.", {})
    program = dsl.parse_program((load_rule_pack(q.rule_pack) if q.rule_pack else "") + "\n" + (q.rules or ""))
    if program.queries:
        raise Errors.Domain.QueryType("Derive takes rules only; use a dsl query to ask a question.", {})
    return derived_result(RuleEngine(evaluator, program.rules).run(), q.predicates)


def check(evaluator: Evaluator, q: ir.Check) -> EvalResult:
    """
    #Feature: Invariant checks (PRD 7.2 Check)
    #Scenario: Counterexample rows; FALSE with any definite violation, UNKNOWN when only holes stand in the way
    #Complexity: Time cost of the invariants

    Raises:
        Errors.Domain.QueryType: On an unknown invariant id.
    """
    from tracegraph.impact import check_all

    try:
        violations = check_all(evaluator.graph, q.invariants or None)
    except ValueError as exc:
        raise Errors.Domain.QueryType(str(exc).split("] ", 1)[-1], {"invariants": q.invariants}) from exc
    rows = [{"node": v.node, "invariant": v.invariant, "severity": v.severity, "message": v.message, "truth": v.truth}
            for v in violations]
    truth = TRUTH_FALSE if any(v.truth == TRUTH_TRUE for v in violations) else TRUTH_UNKNOWN if rows else TRUTH_TRUE
    gaps = {(v.node, "coverage_hole") for v in violations if v.truth == TRUTH_UNKNOWN}
    return EvalResult(nodes={}, rows=rows, truth=truth, gaps=gaps)


def overlay_graph(base: GraphSnapshot, changes: list[dict[str, Any]]) -> GraphSnapshot:
    """
    #Feature: What-if overlays
    #Scenario: Base snapshot plus hypothesized ChangeSpecs, drops applied
    #Complexity: Time O(n + e) clone plus the specs

    Raises:
        Errors.Domain.ChangeSpec: On an invalid spec or unresolved target.
    """
    from tracegraph.impact import ChangeSpec
    from tracegraph.impact.overlay import apply_drops, build_overlay

    try:
        specs = TypeAdapter(list[ChangeSpec]).validate_python(changes)
    except ValueError as exc:
        raise Errors.Domain.ChangeSpec(f"Invalid ChangeSpec: {str(exc)[:300]}", {}) from exc
    overlay = build_overlay(base, specs)
    apply_drops(overlay)
    return overlay.graph


def with_overlay(evaluator: Evaluator, q: ir.WithOverlay) -> EvalResult:
    """
    #Feature: What-if overlays (PRD 7.2 WithOverlay)
    #Scenario: Evaluate the query on the overlay; hypothesized edges are visible to it whatever its min_tier
    #Complexity: Time O(n + e) plus the query
    """
    graph = overlay_graph(evaluator.graph, q.changes)
    result = Evaluator(graph, evaluator.snapshots, TIER_RANK["hypothesized"]).evaluate(q.query)
    result.graph = result.graph or graph
    return result


def _row_keys(graph: GraphSnapshot, result: EvalResult) -> dict[tuple, dict[str, Any]]:
    """
    #Feature: Snapshot diff
    #Scenario: Rows keyed by natural keys (ids differ across snapshots), with the printable row
    #Complexity: Time O(r) - rows
    """
    def key(n: int) -> tuple[str, str]:
        node = graph.nodes.get(n)
        return (node.type, node.key) if node else ("?", str(n))

    out = {}
    if result.rows is None:
        for n in result.nodes:
            out[(key(n),)] = {"type": key(n)[0], "key": key(n)[1]}
        return out
    for row in result.rows:
        ids = [row[k] for k in ("source", "node") if k in row] + list(row.get("nodes", [])) + sorted(
            row.get("bindings", {}).values())
        extra = tuple((k, str(v)) for k, v in sorted(row.items()) if k in ("invariant", "message", "predicate", "value"))
        printable = {"type": key(ids[-1])[0], "key": " -> ".join(key(i)[1] for i in ids)} if ids else {}
        out[tuple(key(i) for i in ids) + extra] = printable | {k: v for k, v in extra}
    return out


def diff(evaluator: Evaluator, q: ir.Diff) -> EvalResult:
    """
    #Feature: Snapshot diff (PRD 7.2 Diff)
    #Scenario: Rows only in b are added, only in a removed; b is an overlay of the changes when they are given
    #Complexity: Time cost of two evaluations

    Raises:
        Errors.Domain.QueryType: When a snapshot was not loaded for the query.
    """
    def graph_for(snapshot_id: int | None) -> GraphSnapshot:
        if snapshot_id is None:
            return evaluator.graph
        if snapshot_id not in evaluator.snapshots:
            raise Errors.Domain.QueryType(f"Snapshot {snapshot_id} is not available to this query.", {"snapshot": snapshot_id})
        return evaluator.snapshots[snapshot_id]

    a = graph_for(q.snapshot_a)
    b = overlay_graph(graph_for(q.snapshot_b), q.changes) if q.changes else graph_for(q.snapshot_b)
    floor = TIER_RANK["hypothesized"] if q.changes else 0
    rows_a = _row_keys(a, Evaluator(a, evaluator.snapshots).evaluate(q.query))
    rows_b = _row_keys(b, Evaluator(b, evaluator.snapshots, floor).evaluate(q.query))
    rows = [{"change": "added", **rows_b[k]} for k in rows_b if k not in rows_a]
    rows += [{"change": "removed", **rows_a[k]} for k in rows_a if k not in rows_b]
    rows.sort(key=lambda r: (r["change"], r.get("key", "")))
    return EvalResult(rows=rows, truth=TRUTH_TRUE if not rows else TRUTH_FALSE)


def snapshot_ids(query: Any) -> set[int]:
    """
    #Feature: Snapshot diff
    #Scenario: Snapshot ids a query refers to, so the service can load them before evaluation
    #Complexity: Time O(s) - query size
    """
    found: set[int] = set()
    if isinstance(query, ir.Diff):
        found |= {s for s in (query.snapshot_a, query.snapshot_b) if s is not None}
    if isinstance(query, ir._Op):
        for name in type(query).model_fields:
            value = getattr(query, name)
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, ir._Op):
                    found |= snapshot_ids(item)
    return found
