import difflib
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import rustworkx

from tracegraph.constants.engine import TRUTH_FALSE, TRUTH_ROWS, TRUTH_TRUE, TRUTH_UNKNOWN
from tracegraph.constants.graph import TIER_RANK
from tracegraph.engine import ir
from tracegraph.engine.graph import EdgeView, GraphSnapshot
from tracegraph.engine.rpq import Nfa, compile_rpq
from tracegraph.errors import Errors

_PATH_EXPANSION_BUDGET = 200_000


@dataclass(frozen=True, slots=True)
class Derivation:
    """
    #Feature: Provenance (PRD 7.5)
    #Scenario: Witness path as edge ids with semiring annotations: weakest tier (max rank), confidence (product)
    #Complexity: Time O(1) - constant
    """

    edges: tuple[int, ...] = ()
    tier_rank: int = 0
    confidence: float = 1.0

    def extend(self, edge: EdgeView) -> "Derivation":
        """
        #Feature: Provenance
        #Scenario: Append one hop; tier is the weakest so far, confidence multiplies
        #Complexity: Time O(p) - copies the path tuple
        """
        return Derivation(self.edges + (edge.id,), max(self.tier_rank, edge.tier_rank),
                          self.confidence * (edge.confidence if edge.confidence is not None else 1.0))


NodeSet = dict[int, Derivation]


@dataclass(slots=True)
class EvalResult:
    """
    #Feature: Reasoning engine
    #Scenario: Operator output: a node set or explicit rows, a truth value, truncation and coverage gaps
    #Complexity: Time O(1) - constant
    """

    nodes: NodeSet = field(default_factory=dict)
    rows: list[dict[str, Any]] | None = None
    truth: str = TRUTH_ROWS
    truncated: bool = False
    gaps: set[tuple[int, str]] = field(default_factory=set)


@dataclass(slots=True)
class _Walk:
    """
    #Feature: Reasoning engine
    #Scenario: Result of one product BFS: reached nodes, visited region and truncation
    #Complexity: Time O(1) - constant
    """

    reached: NodeSet
    visited: set[int]
    truncated: bool


class Evaluator:
    """
    #Feature: Reasoning engine (PRD 7)
    #Scenario: Evaluate typed IR over an in-memory snapshot with provenance and three-valued negation
    #Complexity: Time per operator as documented on the IR models
    """

    def __init__(self, graph: GraphSnapshot) -> None:
        """
        #Feature: Reasoning engine
        #Scenario: Bind to a snapshot (or an overlay copy)
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When graph is None.
        """
        if graph is None:
            raise ValueError("[Evaluator.__init__] 'graph' is required.")
        self.graph = graph
        self.registry = graph.registry

    # ---- type checking ------------------------------------------------------------------

    def _check_types(self, names: list[str]) -> None:
        """
        #Feature: Query type checking
        #Scenario: Every referenced node type must be registered
        #Complexity: Time O(t) - linear in names

        Raises:
            Errors.Domain.QueryType: When a type is unknown.
        """
        unknown = [n for n in names if not self.registry.has_node_type(n)]
        if unknown:
            raise Errors.Domain.QueryType(f"Unknown node types {unknown}.", {"types": unknown})

    def _edge_label(self, name: str) -> tuple[str, str]:
        """
        #Feature: Query type checking
        #Scenario: Edge name -> forward label, inverse name -> reverse label
        #Complexity: Time O(e) - linear in edge types

        Raises:
            Errors.Domain.QueryType: When the name is neither.
        """
        nfa = compile_rpq(name, self.registry)
        labels = list(nfa.labels)
        if len(labels) != 1:
            raise Errors.Domain.QueryType(f"Expected a single edge label, got {name!r}.", {"edge": name})
        return labels[0]

    # ---- traversal kernels --------------------------------------------------------------

    def _walk(self, starts: NodeSet, nfa: Nfa, max_hops: int, min_tier: str, target_types: list[str],
              include_start: bool = False) -> _Walk:
        """
        #Feature: Reachability
        #Scenario: BFS over graph x NFA from the anchors only (demand-driven); first hit per node is shortest
        #Complexity: Time O((n + e) * q) - product size
        """
        max_rank, init = TIER_RANK[min_tier], nfa.closure(frozenset({nfa.start}))
        moves_cache: dict[frozenset[int], dict] = {}
        reached: NodeSet = {}
        visited, seen, truncated = set(starts), set(), False
        frontier = deque((n, init, d, 0) for n, d in starts.items())
        if include_start and nfa.accept in init:
            reached.update({n: d for n, d in starts.items() if self.graph.type_matches(n, target_types)})
        while frontier:
            node, states, deriv, hops = frontier.popleft()
            moves = moves_cache.setdefault(states, nfa.labels_from(states))
            for label, next_states in moves.items():
                for other, edge in self.graph.neighbors(node, label, max_rank):
                    if hops >= max_hops:
                        truncated = True
                        break
                    if (other, next_states) in seen:
                        continue
                    seen.add((other, next_states))
                    visited.add(other)
                    step = deriv.extend(edge)
                    if nfa.accept in next_states and other not in reached and self.graph.type_matches(other, target_types):
                        reached[other] = step
                    frontier.append((other, next_states, step, hops + 1))
        return _Walk(reached, visited, truncated)

    def _gaps(self, nodes: set[int]) -> set[tuple[int, str]]:
        """
        #Feature: Coverage map
        #Scenario: Coverage holes recorded on any node of a region
        #Complexity: Time O(r) - region size
        """
        return {(n, h["kind"]) for n in nodes for h in self.graph.holes.get(n, [])}

    # ---- operators ----------------------------------------------------------------------

    def _select(self, q: ir.Select) -> EvalResult:
        """
        #Feature: Reasoning engine
        #Scenario: Hierarchy-aware typed anchor with equality predicates ("key" = natural key)
        #Complexity: Time O(n) - scan of the type
        """
        self._check_types([q.type])
        nodes = [n for n in self.graph.of_type(q.type)
                 if all((n.key if k == "key" else n.props.get(k)) == v for k, v in q.where.items())]
        return EvalResult(nodes={n.id: Derivation() for n in nodes})

    def _resolve(self, q: ir.Resolve) -> EvalResult:
        """
        #Feature: Entity resolution
        #Scenario: Rank candidates by substring match then sequence similarity on the natural key
        #Complexity: Time O(n * k) - nodes times key length
        """
        self._check_types(q.types)
        text = q.text.lower()
        scored = []
        for node in self.graph.nodes.values():
            if q.types and not self.graph.type_matches(node.id, q.types):
                continue
            key = node.key.lower()
            score = max(0.5 + 0.5 * len(text) / len(key) if text in key else 0.0,
                        difflib.SequenceMatcher(None, text, key.rsplit(".", 1)[-1]).ratio())
            if score >= 0.4:
                scored.append((score, node.id))
        scored.sort(key=lambda s: (-s[0], len(self.graph.nodes[s[1]].key)))
        rows = [{"node": nid, "score": round(score, 3)} for score, nid in scored[: q.limit]]
        return EvalResult(nodes={r["node"]: Derivation() for r in rows}, rows=rows)

    def _expand(self, q: ir.Expand) -> EvalResult:
        """
        #Feature: Reasoning engine
        #Scenario: One labelled hop from each input node
        #Complexity: Time O(sum of degrees)
        """
        self._check_types(q.target_types)
        source, label = self.evaluate(q.input), self._edge_label(q.edge)
        out: NodeSet = {}
        for node, deriv in source.nodes.items():
            for other, edge in self.graph.neighbors(node, label, TIER_RANK[q.min_tier]):
                if self.graph.type_matches(other, q.target_types):
                    out.setdefault(other, deriv.extend(edge))
        return EvalResult(nodes=out, truncated=source.truncated, gaps=source.gaps)

    def _reach(self, q: ir.Reach) -> EvalResult:
        """
        #Feature: Reachability
        #Scenario: RPQ from the input set; reports holes in the explored region
        #Complexity: Time O((n + e) * q) - product size
        """
        self._check_types(q.target_types)
        source = self.evaluate(q.input)
        walk = self._walk(source.nodes, compile_rpq(q.rpq, self.registry), q.max_hops, q.min_tier,
                          q.target_types, q.include_start)
        return EvalResult(nodes=walk.reached, truncated=source.truncated or walk.truncated,
                          gaps=source.gaps | self._gaps(walk.visited))

    def _set_op(self, q: ir.Union_ | ir.Intersect | ir.Minus) -> EvalResult:
        """
        #Feature: Composition
        #Scenario: Union, intersection and difference of node sets (shortest derivation kept)
        #Complexity: Time O(sum of inputs)
        """
        parts = [self.evaluate(p) for p in ([q.left, q.right] if isinstance(q, ir.Minus) else q.inputs)]
        if isinstance(q, ir.Union_):
            ids = set().union(*(p.nodes for p in parts))
        elif isinstance(q, ir.Intersect):
            ids = set(parts[0].nodes).intersection(*(p.nodes for p in parts[1:]))
        else:
            ids = set(parts[0].nodes) - set(parts[1].nodes)
        best = {n: min((p.nodes[n] for p in parts if n in p.nodes), key=lambda d: len(d.edges)) for n in ids}
        return EvalResult(nodes=best, truncated=any(p.truncated for p in parts),
                          gaps=set().union(*(p.gaps for p in parts)))

    def _absence(self, scope: ir.Query, rpq: str, target_types: list[str], max_hops: int,
                 min_tier: str) -> tuple[EvalResult, list[dict[str, Any]], list[dict[str, Any]]]:
        """
        #Feature: Three-valued negation (PRD 7.5, D6)
        #Scenario: Split scope nodes into those that reach a target and those that do not; an absence is TRUE
                   only when the explored region has no coverage holes and the walk was not truncated
        #Complexity: Time O(|scope| * (n + e) * q)
        """
        self._check_types(target_types)
        source, nfa = self.evaluate(scope), compile_rpq(rpq, self.registry)
        present, absent = [], []
        for node, deriv in source.nodes.items():
            walk = self._walk({node: deriv}, nfa, max_hops, min_tier, target_types)
            if walk.reached:
                witness = min(walk.reached.items(), key=lambda kv: len(kv[1].edges))
                present.append({"node": node, "witness": witness[0], "derivation": witness[1]})
                continue
            gaps = self._gaps(walk.visited)
            truth = TRUTH_UNKNOWN if gaps or walk.truncated else TRUTH_TRUE
            absent.append({"node": node, "truth": truth, "gaps": sorted(gaps), "derivation": deriv})
        return source, present, absent

    def _not_exists(self, q: ir.NotExists) -> EvalResult:
        """
        #Feature: Three-valued negation
        #Scenario: Rows are scope nodes with no witness; each row is TRUE or UNKNOWN
        #Complexity: Time O(|scope| * (n + e) * q)
        """
        source, _, absent = self._absence(q.scope, q.rpq, q.target_types, q.max_hops, q.min_tier)
        rows = [{"node": a["node"], "truth": a["truth"], "gaps": a["gaps"]} for a in absent]
        return EvalResult(nodes={a["node"]: a["derivation"] for a in absent}, rows=rows, truncated=source.truncated,
                          gaps=source.gaps | {g for a in absent for g in a["gaps"]})

    def _forall(self, q: ir.ForAll) -> EvalResult:
        """
        #Feature: Universal quantification
        #Scenario: TRUE if every scope node has a witness; FALSE with definite counterexamples; else UNKNOWN
        #Complexity: Time O(|scope| * (n + e) * q)
        """
        source, present, absent = self._absence(q.scope, q.rpq, q.target_types, q.max_hops, q.min_tier)
        definite = [a for a in absent if a["truth"] == TRUTH_TRUE]
        truth = TRUTH_FALSE if definite else TRUTH_UNKNOWN if absent else TRUTH_TRUE
        rows = [{"node": a["node"], "counterexample": True, "truth": a["truth"], "gaps": a["gaps"]} for a in absent]
        nodes = {p["node"]: p["derivation"] for p in present} if truth == TRUTH_TRUE else {
            a["node"]: a["derivation"] for a in absent}
        return EvalResult(nodes=nodes, rows=rows, truth=truth, truncated=source.truncated,
                          gaps=source.gaps | {g for a in absent for g in a["gaps"]})

    def _aggregate(self, q: ir.Aggregate) -> EvalResult:
        """
        #Feature: Aggregation
        #Scenario: Distinct nodes reached per group; lower_bound when the region has holes or was truncated
        #Complexity: Time O(|groups| * (n + e) * q)
        """
        self._check_types(q.target_types)
        groups, nfa = self.evaluate(q.groups), compile_rpq(q.rpq, self.registry)
        rows, gaps = [], set(groups.gaps)
        for node, deriv in groups.nodes.items():
            walk = self._walk({node: deriv}, nfa, q.max_hops, "inferred", q.target_types)
            region_gaps = self._gaps(walk.visited)
            gaps |= region_gaps
            if len(walk.reached) >= q.having_min:
                rows.append({"node": node, "value": len(walk.reached),
                             "lower_bound": bool(region_gaps) or walk.truncated})
        rows.sort(key=lambda r: (r["value"], -r["node"]), reverse=q.order == "desc")
        rows = rows[: q.limit]
        return EvalResult(nodes={r["node"]: groups.nodes[r["node"]] for r in rows}, rows=rows, gaps=gaps)

    def _rank(self, q: ir.Rank) -> EvalResult:
        """
        #Feature: Ranking
        #Scenario: Top-k by fan-in, fan-out or blast radius (nodes reachable along the RPQ)
        #Complexity: Time O(|input| * score cost)

        Raises:
            Errors.Domain.QueryType: When blast_radius has no RPQ.
        """
        source = self.evaluate(q.input)
        if q.score == "blast_radius" and not q.rpq:
            raise Errors.Domain.QueryType("Rank by blast_radius requires an rpq.", {})
        nfa = compile_rpq(q.rpq, self.registry) if q.score == "blast_radius" else None
        types = [self._edge_label(e)[0] for e in q.edges]
        scored = []
        for node in source.nodes:
            if nfa is not None:
                value = len(self._walk({node: Derivation()}, nfa, 16, "inferred", []).reached)
            else:
                value = self.graph.degree(node, types, "rev" if q.score == "fan_in" else "fwd")
            scored.append({"node": node, "value": value})
        scored.sort(key=lambda r: (-r["value"], r["node"]))
        rows = scored[: q.k]
        return EvalResult(nodes={r["node"]: source.nodes[r["node"]] for r in rows}, rows=rows, gaps=source.gaps)

    def _scc(self, q: ir.SCC) -> EvalResult:
        """
        #Feature: Structural analysis
        #Scenario: Cycles (SCCs of size > 1) among input nodes over one edge type, via rustworkx Tarjan
        #Complexity: Time O(n + e) - linear in the induced subgraph
        """
        source, (edge_type, _) = self.evaluate(q.input), self._edge_label(q.edge)
        ids = list(source.nodes)
        graph, index = rustworkx.PyDiGraph(), {}
        for node in ids:
            index[node] = graph.add_node(node)
        for node in ids:
            for edge in self.graph.fwd.get(edge_type, {}).get(node, []):
                if edge.dst in index:
                    graph.add_edge(index[node], index[edge.dst], edge.id)
        components = [sorted(graph[i] for i in comp) for comp in rustworkx.strongly_connected_components(graph)]
        rows = [{"component": i, "nodes": comp} for i, comp in enumerate(sorted(c for c in components if len(c) > 1))]
        members = {n for r in rows for n in r["nodes"]}
        return EvalResult(nodes={n: Derivation() for n in members}, rows=rows,
                          truth=TRUTH_TRUE if rows else TRUTH_FALSE)

    def _paths(self, q: ir.Paths) -> EvalResult:
        """
        #Feature: Explanation
        #Scenario: Up to k shortest simple witness paths per (source, target) pair, bounded by an expansion budget
        #Complexity: Time O(min(budget, paths explored))
        """
        sources, targets = self.evaluate(q.source), self.evaluate(q.target)
        nfa, max_rank = compile_rpq(q.rpq, self.registry), TIER_RANK[q.min_tier]
        init = nfa.closure(frozenset({nfa.start}))
        frontier = deque((s, init, Derivation(), (s,)) for s in sources.nodes)
        found: dict[tuple[int, int], list[Derivation]] = {}
        budget, truncated = _PATH_EXPANSION_BUDGET, False
        while frontier and budget > 0:
            node, states, deriv, trail = frontier.popleft()
            for label, next_states in nfa.labels_from(states).items():
                for other, edge in self.graph.neighbors(node, label, max_rank):
                    budget -= 1
                    if other in trail or len(deriv.edges) >= q.max_hops:
                        truncated = truncated or len(deriv.edges) >= q.max_hops
                        continue
                    step = deriv.extend(edge)
                    pair = (trail[0], other)
                    if nfa.accept in next_states and other in targets.nodes and len(found.get(pair, [])) < q.k:
                        found.setdefault(pair, []).append(step)
                    frontier.append((other, next_states, step, trail + (other,)))
        rows = [{"source": s, "node": t, "rank": i, "derivation": d}
                for (s, t), ds in sorted(found.items()) for i, d in enumerate(ds)]
        return EvalResult(nodes={r["node"]: r["derivation"] for r in rows if r["rank"] == 0}, rows=rows,
                          truth=TRUTH_TRUE if rows else TRUTH_FALSE, truncated=truncated or budget <= 0)

    _DISPATCH = {
        ir.Select: _select, ir.Resolve: _resolve, ir.Expand: _expand, ir.Reach: _reach, ir.Union_: _set_op,
        ir.Intersect: _set_op, ir.Minus: _set_op, ir.NotExists: _not_exists, ir.ForAll: _forall,
        ir.Aggregate: _aggregate, ir.Rank: _rank, ir.SCC: _scc, ir.Paths: _paths,
    }

    def evaluate(self, query: Any) -> EvalResult:
        """
        #Feature: Reasoning engine
        #Scenario: Dispatch one IR node to its operator
        #Complexity: Time per operator

        Raises:
            ValueError: When query is None.
            Errors.Domain.QueryType: On unknown operators or ill-typed arguments.
        """
        if query is None:
            raise ValueError("[Evaluator.evaluate] 'query' is required.")
        handler = self._DISPATCH.get(type(query))
        if handler is None:
            raise Errors.Domain.QueryType(f"Unsupported operator {type(query).__name__}.", {})
        return handler(self, query)
