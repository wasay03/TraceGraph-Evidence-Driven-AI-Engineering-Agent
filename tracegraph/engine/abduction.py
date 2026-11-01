from collections import deque
from typing import Any

from tracegraph.constants.engine import MAX_HOPS_LIMIT, TRUTH_FALSE, TRUTH_TRUE, TRUTH_UNKNOWN
from tracegraph.constants.graph import TIER_RANK
from tracegraph.engine import ir
from tracegraph.engine.evaluator import Derivation, EvalResult, Evaluator
from tracegraph.engine.rpq import Label, Nfa, compile_rpq

MAX_CANDIDATES = 10
_STATE_BUDGET = 50_000


def _source_and_rpq(q: Any) -> tuple[Any, str, list[str], int, str] | None:
    """
    #Feature: Abduction (PRD 7.2 WhyNot)
    #Scenario: (anchor query, RPQ, target types, max hops, min tier) for the path operators WhyNot can explain
    #Complexity: Time O(1) - constant
    """
    if isinstance(q, ir.Reach):
        return q.input, q.rpq, q.target_types, q.max_hops, q.min_tier
    if isinstance(q, ir.Expand):
        return q.input, q.edge, q.target_types, 1, q.min_tier
    if isinstance(q, ir.Paths):
        return q.source, q.rpq, [], q.max_hops, q.min_tier
    return None


def _flip(label: Label) -> Label:
    """
    #Feature: Abduction
    #Scenario: Same edge type, opposite direction
    #Complexity: Time O(1) - constant
    """
    return label[0], "rev" if label[1] == "fwd" else "fwd"


def _product(evaluator: Evaluator, starts: list[int], nfa: Nfa, begin: int, backward: bool) -> dict[tuple[int, int], int]:
    """
    #Feature: Abduction
    #Scenario: Hops to every (node, NFA state) pair reachable from the starts, forward from the NFA start or
               backward from accept, on every tier and up to the hop limit
    #Complexity: Time O((n + e) * q), capped by a state budget
    """
    moves: dict[int, list[tuple[Label | None, int]]] = {}
    for s, outs in nfa.transitions.items():
        for label, t in outs:
            src, dst = (t, s) if backward else (s, t)
            moves.setdefault(src, []).append((label, dst))
    seen = {(n, begin): 0 for n in starts}
    queue = deque(seen)
    while queue and len(seen) < _STATE_BUDGET:
        node, state = queue.popleft()
        hops = seen[(node, state)]
        for label, nxt in moves.get(state, []):
            if label is None:
                targets = [node]
            elif hops >= MAX_HOPS_LIMIT:
                continue
            else:
                look = _flip(label) if backward else label
                targets = [o for o, _ in evaluator.graph.neighbors(node, look, TIER_RANK["hypothesized"])]
            for other in targets:
                if (other, nxt) not in seen:
                    seen[(other, nxt)] = hops + (label is not None)
                    queue.append((other, nxt))
    return seen


def _missing_links(evaluator: Evaluator, sources: list[int], expected: int, nfa: Nfa) -> list[dict[str, Any]]:
    """
    #Feature: Abduction
    #Scenario: Single absent edges that would complete a path: u reachable in state s, v co-reachable in state t,
               s -L-> t in the NFA, the ontology permits L between their types, and no such edge exists yet.
               Closest candidates first.
    #Complexity: Time O(|F| * |B| per transition), capped at MAX_CANDIDATES per transition
    """
    graph, registry = evaluator.graph, evaluator.registry
    forward = _product(evaluator, sources, nfa, nfa.start, backward=False)
    backward = _product(evaluator, [expected], nfa, nfa.accept, backward=True)
    by_state_f: dict[int, list[tuple[int, int]]] = {}
    for (n, s), h in forward.items():
        by_state_f.setdefault(s, []).append((h, n))
    by_state_b: dict[int, list[tuple[int, int]]] = {}
    for (n, t), h in backward.items():
        by_state_b.setdefault(t, []).append((h, n))
    found: dict[tuple, int] = {}
    for s, outs in nfa.transitions.items():
        for label, t in outs:
            if label is None:
                continue
            pairs = sorted((hf + hb, u, v) for hf, u in by_state_f.get(s, []) for hb, v in by_state_b.get(t, []))
            kept = 0
            for cost, u, v in pairs:
                src, dst = (u, v) if label[1] == "fwd" else (v, u)
                if kept >= MAX_CANDIDATES or u == v or (label[0], src, dst) in found:
                    continue
                if not registry.edge_permits(label[0], graph.nodes[src].type, graph.nodes[dst].type):
                    continue
                if any(o == v for o, _ in graph.neighbors(u, label, TIER_RANK["hypothesized"])):
                    continue
                found[(label[0], src, dst)] = cost + 1
                kept += 1
    ranked = sorted(found.items(), key=lambda kv: kv[1])[:MAX_CANDIDATES]
    return [{"reason": "missing_edge", "edge": e, "source": s, "node": d, "path_length": c} for (e, s, d), c in ranked]


def _reasons(evaluator: Evaluator, q: Any, expected: int, sources: list[int]) -> list[dict[str, Any]]:
    """
    #Feature: Abduction
    #Scenario: Cheapest explanations first: type filter, hop limit, tier filter, then holes and missing edges
    #Complexity: Time O((n + e) * q) per relaxed walk
    """
    anchor, rpq, types, hops, tier = _source_and_rpq(q)
    graph, nfa = evaluator.graph, compile_rpq(rpq, evaluator.registry)
    out: list[dict[str, Any]] = []
    if types and not graph.type_matches(expected, types):
        out.append({"reason": "type_filter", "node": expected, "detail": f"{graph.nodes[expected].type} is not in {types}"})
    starts = {s: Derivation() for s in sources}
    relaxed = evaluator.walk(starts, nfa, MAX_HOPS_LIMIT, "hypothesized", [])
    if expected in relaxed.reached:
        needed = len(relaxed.reached[expected].edges)
        if needed > hops:
            out.append({"reason": "hop_limit", "node": expected, "detail": f"needs {needed} hops, max_hops is {hops}",
                        "derivation": relaxed.reached[expected]})
        elif not out:
            out.append({"reason": "tier_filter", "node": expected, "detail": f"the only path has an edge weaker than {tier}",
                        "derivation": relaxed.reached[expected]})
        return out
    holes = evaluator._gaps(relaxed.visited)
    out += [{"reason": "coverage_hole", "node": n, "detail": kind} for n, kind in sorted(holes)]
    return out + _missing_links(evaluator, sources, expected, nfa)


def why_not(evaluator: Evaluator, q: ir.WhyNot) -> EvalResult:
    """
    #Feature: Abduction (PRD 7.2 WhyNot)
    #Scenario: Explain why the node with the expected natural key is missing from the query's result. TRUE means
               it is present; UNKNOWN means coverage holes may hide the link; FALSE lists the blocking reasons.
    #Complexity: Time O(product graph size), capped

    Raises:
        Errors.Domain.QueryType: When the expected key matches no node.
    """
    from tracegraph.errors import Errors

    matches = [n.id for n in evaluator.graph.nodes.values() if n.key == q.expected]
    if not matches:
        raise Errors.Domain.QueryType(f"No node has the key {q.expected!r}.", {"expected": q.expected})
    result = evaluator.evaluate(q.query)
    present = [m for m in matches if m in result.nodes or any(r.get("node") == m for r in result.rows or [])]
    if present:
        return EvalResult(rows=[{"reason": "present", "node": present[0]}], truth=TRUTH_TRUE)
    if _source_and_rpq(q.query) is None:
        return EvalResult(rows=[{"reason": "unsupported", "node": matches[0], "detail":
                                 f"why_not explains reach, expand and paths, not {q.query.op}"}], truth=TRUTH_UNKNOWN)
    sources = list(evaluator.evaluate(_source_and_rpq(q.query)[0]).nodes)
    if not sources:
        return EvalResult(rows=[{"reason": "empty_anchor", "node": matches[0], "detail": "the anchor query matched nothing"}],
                          truth=TRUTH_FALSE)
    rows = [r for m in matches for r in _reasons(evaluator, q.query, m, sources)]
    gaps = {(r["node"], r["detail"]) for r in rows if r["reason"] == "coverage_hole"}
    return EvalResult(rows=rows, truth=TRUTH_UNKNOWN if gaps else TRUTH_FALSE, gaps=gaps)
