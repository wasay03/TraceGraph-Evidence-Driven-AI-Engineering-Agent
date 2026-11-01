import random
import re

import pytest
from pydantic import TypeAdapter

from tests.engine.helpers import REGISTRY
from tracegraph.engine import EdgeView, Evaluator, GraphSnapshot, NodeView, ir

QUERY = TypeAdapter(ir.Query)
# RPQ -> equivalent Python regex over one-letter labels (lower = forward, upper = reverse)
CASES = {
    "CALLS*": "a*",
    "(CALLS|INJECTS)* . CALLS": "[ab]*a",
    "CALLS . INJECTS+": "ab+",
    "CALLED_BY . CALLS?": "Aa?",
    "INJECTS^-1 . (CALLS | CALLED_BY)*": "B[aA]*",
}
LETTER = {("CALLS", "fwd"): "a", ("INJECTS", "fwd"): "b", ("CALLS", "rev"): "A", ("INJECTS", "rev"): "B"}
MAX_HOPS = 5


def random_graph(seed: int, n: int = 9, m: int = 16) -> GraphSnapshot:
    rng = random.Random(seed)
    graph = GraphSnapshot(REGISTRY, 1, 1, "x")
    for i in range(1, n + 1):
        graph.add_node(NodeView(i, "Function", f"f{i}", {"qualified_name": f"f{i}"}, "asserted"))
    for eid in range(100, 100 + m):
        kind = rng.choice(["CALLS", "INJECTS"])
        graph.add_edge(EdgeView(eid, kind, rng.randint(1, n), rng.randint(1, n), {}, "asserted"))
    return graph


def reference_reach(graph: GraphSnapshot, start: int, pattern: str) -> set[int]:
    regex, out = re.compile(pattern), set()
    stack = [(start, "")]
    while stack:
        node, word = stack.pop()
        if word and regex.fullmatch(word):
            out.add(node)
        if len(word) == MAX_HOPS:
            continue
        for edge in graph.edges.values():
            if edge.src == node:
                stack.append((edge.dst, word + LETTER[(edge.type, "fwd")]))
            if edge.dst == node:
                stack.append((edge.src, word + LETTER[(edge.type, "rev")]))
    return out


def reach(graph: GraphSnapshot, start: int, rpq: str) -> set[int]:
    query = QUERY.validate_python({"op": "reach", "rpq": rpq, "max_hops": MAX_HOPS,
                                   "input": {"op": "select", "type": "Function", "where": {"key": f"f{start}"}}})
    return set(Evaluator(graph).evaluate(query).nodes)


@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize("rpq", list(CASES))
def test_product_bfs_matches_reference(seed: int, rpq: str):
    graph = random_graph(seed)
    start = random.Random(seed).randint(1, 9)
    assert reach(graph, start, rpq) == reference_reach(graph, start, CASES[rpq])


@pytest.mark.parametrize("seed", range(25))
def test_adding_an_edge_never_removes_reach_results(seed: int):
    graph = random_graph(seed)
    before = reach(graph, 1, "(CALLS|INJECTS)*")
    rng = random.Random(seed + 1000)
    graph.add_edge(EdgeView(999, "CALLS", rng.randint(1, 9), rng.randint(1, 9), {}, "asserted"))
    assert before <= reach(graph, 1, "(CALLS|INJECTS)*")


@pytest.mark.parametrize("seed", range(25))
def test_holes_turn_true_into_unknown_never_false(seed: int):
    graph = random_graph(seed)
    query = QUERY.validate_python({"op": "not_exists", "scope": {"op": "select", "type": "Function"},
                                   "rpq": "CALLS+", "target_types": ["Test"], "max_hops": 16})
    before = {r["node"]: r["truth"] for r in Evaluator(graph).evaluate(query).rows}
    graph.holes[random.Random(seed).randint(1, 9)] = [{"kind": "untyped_receiver"}]
    after = {r["node"]: r["truth"] for r in Evaluator(graph).evaluate(query).rows}
    assert set(before) == set(after)
    assert all(after[n] in (before[n], "UNKNOWN") for n in before)
