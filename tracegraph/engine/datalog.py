from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tracegraph.constants.engine import DEFAULT_MAX_HOPS, TRUTH_ROWS, TRUTH_TRUE, TRUTH_UNKNOWN
from tracegraph.constants.graph import TIER_RANK
from tracegraph.engine import dsl
from tracegraph.engine.evaluator import Derivation, EvalResult
from tracegraph.engine.graph import EdgeView
from tracegraph.engine.rpq import Label, compile_rpq
from tracegraph.errors import Errors

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
_NUMERIC = (int, float)
Binding = dict[str, int]


@dataclass(frozen=True, slots=True)
class Fact:
    """
    #Feature: Rule evaluation (PRD 7.5)
    #Scenario: Why-provenance of one tuple: witness path, rules used and the coverage holes it rests on
    #Complexity: Time O(1) - constant
    """

    derivation: Derivation = Derivation()
    gaps: frozenset[tuple[int, str]] = frozenset()
    rules: tuple[str, ...] = ()

    def join(self, other: "Fact") -> "Fact":
        """
        #Feature: Rule evaluation
        #Scenario: Conjunction: paths concatenate, tier is the weakest and confidence multiplies
        #Complexity: Time O(p) - path lengths
        """
        a, b = self.derivation, other.derivation
        return Fact(Derivation(a.edges + b.edges, max(a.tier_rank, b.tier_rank), a.confidence * b.confidence),
                    self.gaps | other.gaps, tuple(dict.fromkeys(self.rules + other.rules)))


def load_rule_pack(name: str) -> str:
    """
    #Feature: Rule files
    #Scenario: Read rules/derive/<name>.tg from the package
    #Complexity: Time O(s) - file size

    Raises:
        Errors.Domain.QueryType: When the pack does not exist.
    """
    path = RULES_DIR / "derive" / f"{name}.tg"
    if not name.isidentifier() or not path.is_file():
        known = sorted(p.stem for p in (RULES_DIR / "derive").glob("*.tg"))
        raise Errors.Domain.QueryType(f"Unknown rule pack {name!r}; available: {known}.", {"rule_pack": name})
    return path.read_text(encoding="utf-8")


def _node_prop(node: Any, name: str) -> Any:
    """
    #Feature: Rule evaluation
    #Scenario: Node attribute by DSL name: key, file, line or an ontology prop
    #Complexity: Time O(1) - constant
    """
    if name == "key":
        return node.key
    if name == "file":
        return node.file
    if name == "line":
        return node.line_start
    return node.props.get(name)


def stratify(rules: list[dsl.Rule]) -> list[list[dsl.Rule]]:
    """
    #Feature: Rule evaluation
    #Scenario: Assign strata so a predicate only negates lower strata
    #Complexity: Time O(p * r * l) - predicates, rules and literals

    Raises:
        Errors.Domain.QueryType: On recursion through negation.
    """
    derived = {r.head.pred for r in rules}
    strata = dict.fromkeys(derived, 0)
    for _ in range(len(derived) + 1):
        changed = False
        for rule in rules:
            for literal in rule.body:
                atom = literal.atom if isinstance(literal, dsl.Negated) else literal
                if isinstance(atom, dsl.Atom) and atom.pred in derived:
                    need = strata[atom.pred] + (1 if isinstance(literal, dsl.Negated) else 0)
                    if need > strata[rule.head.pred]:
                        strata[rule.head.pred], changed = need, True
        if not changed:
            return [[r for r in rules if strata[r.head.pred] == s] for s in range(max(strata.values(), default=0) + 1)]
    raise Errors.Domain.QueryType("Rules recurse through negation, so they cannot be stratified.", {"rules": sorted(derived)})


@dataclass(slots=True)
class _Plan:
    """
    #Feature: Rule evaluation
    #Scenario: Body literals in the order they can be evaluated
    #Complexity: Time O(1) - constant
    """

    literals: list[dsl.Literal] = field(default_factory=list)


class RuleEngine:
    """
    #Feature: Rule evaluation (PRD 7.2 Derive, 7.5)
    #Scenario: Stratified semi-naive evaluation over one graph, with why-provenance and three-valued negation
    #Complexity: Time O(strata * iterations * join cost)
    """

    def __init__(self, evaluator: Any, rules: list[dsl.Rule]) -> None:
        """
        #Feature: Rule evaluation
        #Scenario: Bind to the evaluator's graph; facts fill in when run() is called
        #Complexity: Time O(r) - rules
        """
        self.evaluator, self.graph, self.registry = evaluator, evaluator.graph, evaluator.graph.registry
        self.rules, self.derived = rules, {r.head.pred for r in rules}
        self.facts: dict[str, dict[tuple[int, ...], Fact]] = defaultdict(dict)
        self.max_rank = max(TIER_RANK["inferred"], evaluator.tier_floor)
        self.truncated = False

    # ---- planning -----------------------------------------------------------------------

    def _vars(self, literal: dsl.Literal) -> set[str]:
        """
        #Feature: Rule evaluation
        #Scenario: Variable names a literal mentions
        #Complexity: Time O(a) - arguments
        """
        if isinstance(literal, dsl.Atom):
            return {v.name for v in literal.args}
        if isinstance(literal, dsl.Negated):
            return {v.name for v in literal.atom.args}
        if isinstance(literal, dsl.ReachAtom):
            return {literal.src.name, literal.dst.name}
        return {literal.var.name}

    def _score(self, literal: dsl.Literal, bound: set[str]) -> int | None:
        """
        #Feature: Rule evaluation
        #Scenario: Cost rank of a literal given bound variables; None when it cannot run yet
        #Complexity: Time O(a) - arguments
        """
        names = self._vars(literal)
        if isinstance(literal, dsl.Equals):
            return 0
        if isinstance(literal, dsl.PropTest | dsl.Negated):
            return 1 if names <= bound else None
        if isinstance(literal, dsl.ReachAtom):
            return 2 if literal.src.name in bound else None
        if names <= bound:
            return 1
        if names & bound:
            return 3
        return 4 if literal.pred in self.derived else 5 if len(literal.args) == 2 else 6

    def _plan(self, body: tuple[dsl.Literal, ...]) -> list[dsl.Literal]:
        """
        #Feature: Rule evaluation
        #Scenario: Greedy join order: cheapest runnable literal next
        #Complexity: Time O(l^2 * a) - literals squared

        Raises:
            Errors.Domain.QueryType: When a literal's variables can never be bound.
        """
        pending, bound, ordered = list(body), set(), []
        while pending:
            scored = [(self._score(p, bound), i) for i, p in enumerate(pending)]
            runnable = [s for s in scored if s[0] is not None]
            if not runnable:
                raise Errors.Domain.QueryType(f"Unsafe rule: {pending[0]} needs a variable no other literal binds.", {})
            chosen = pending.pop(min(runnable)[1])
            ordered.append(chosen)
            bound |= self._vars(chosen)
        return ordered

    # ---- literal evaluation -------------------------------------------------------------

    def _label(self, name: str) -> Label:
        """
        #Feature: Rule evaluation
        #Scenario: Edge or inverse name to a label
        #Complexity: Time O(e) - edge types
        """
        return self.evaluator._edge_label(name)

    def _edge_rows(self, atom: dsl.Atom, env: Binding) -> Iterator[tuple[Binding, Fact]]:
        """
        #Feature: Rule evaluation
        #Scenario: Edge atom using whichever side is bound; both unbound scans the edge type
        #Complexity: Time O(deg) when a side is bound, O(e) otherwise

        Raises:
            Errors.Domain.QueryType: When the atom does not have two arguments.
        """
        if len(atom.args) != 2:
            raise Errors.Domain.QueryType(f"Edge {atom.pred} takes 2 arguments.", {"edge": atom.pred})
        (edge_type, direction), (left, right) = self._label(atom.pred), atom.args
        src, dst = (left, right) if direction == "fwd" else (right, left)
        if src.name in env:
            candidates = self.graph.neighbors(env[src.name], (edge_type, "fwd"), self.max_rank)
            edges: Any = (e for _, e in candidates)
        elif dst.name in env:
            edges = (e for _, e in self.graph.neighbors(env[dst.name], (edge_type, "rev"), self.max_rank))
        else:
            edges = (e for per in self.graph.fwd.get(edge_type, {}).values() for e in per if e.tier_rank <= self.max_rank)
        for edge in edges:
            if env.get(dst.name, edge.dst) == edge.dst and env.get(src.name, edge.src) == edge.src:
                yield {**env, src.name: edge.src, dst.name: edge.dst}, self._edge_fact(edge)

    def _edge_fact(self, edge: EdgeView) -> Fact:
        """
        #Feature: Rule evaluation
        #Scenario: Provenance of one edge
        #Complexity: Time O(1) - constant
        """
        return Fact(Derivation().extend(edge))

    def _atom_rows(self, atom: dsl.Atom, env: Binding, source: dict[tuple[int, ...], Fact] | None) -> Iterator[tuple[Binding, Fact]]:
        """
        #Feature: Rule evaluation
        #Scenario: Derived predicate, node type or edge atom
        #Complexity: Time O(facts), O(n) or per edge
        """
        if atom.pred in self.derived:
            for values, fact in (self.facts[atom.pred] if source is None else source).items():
                if all(env.get(v.name, x) == x for v, x in zip(atom.args, values, strict=True)):
                    yield {**env, **{v.name: x for v, x in zip(atom.args, values, strict=True)}}, fact
        elif self.registry.has_node_type(atom.pred):
            name = atom.args[0].name
            if name in env:
                if self.graph.type_matches(env[name], [atom.pred]):
                    yield env, Fact()
            else:
                for node in self.graph.of_type(atom.pred):
                    yield {**env, name: node.id}, Fact()
        else:
            yield from self._edge_rows(atom, env)

    def _reach_rows(self, atom: dsl.ReachAtom, env: Binding) -> Iterator[tuple[Binding, Fact]]:
        """
        #Feature: Rule evaluation
        #Scenario: RPQ walk from the bound source; truncation is recorded on the answer
        #Complexity: Time O((n + e) * q)
        """
        walk = self.evaluator.walk({env[atom.src.name]: Derivation()}, compile_rpq(atom.rpq, self.registry),
                                   atom.max_hops, "inferred", [], include_start=True)
        self.truncated = self.truncated or walk.truncated
        for node, derivation in walk.reached.items():
            if env.get(atom.dst.name, node) == node:
                yield {**env, atom.dst.name: node}, Fact(derivation)

    def _equals_rows(self, literal: dsl.Equals, env: Binding) -> Iterator[tuple[Binding, Fact]]:
        """
        #Feature: Rule evaluation
        #Scenario: Var == type("key"), where type "key" means any node type
        #Complexity: Time O(n) - scan of the type

        Raises:
            Errors.Domain.QueryType: On an unknown node type.
        """
        names = {t.name.lower(): t.name for t in self.registry.node_types}
        type_name = "Entity" if literal.type == "key" else names.get(literal.type.lower())
        if type_name is None:
            raise Errors.Domain.QueryType(f"Unknown node type {literal.type!r} in the DSL.", {"type": literal.type})
        for node in self.graph.of_type(type_name):
            if node.key == literal.key and env.get(literal.var.name, node.id) == node.id:
                yield {**env, literal.var.name: node.id}, Fact()

    def _used_labels(self, pred: str, seen: set[str] | None = None) -> set[Label]:
        """
        #Feature: Three-valued negation
        #Scenario: Edge labels a predicate depends on, through its rules
        #Complexity: Time O(r * l) - rules and literals
        """
        seen = seen if seen is not None else set()
        seen.add(pred)
        labels: set[Label] = set()
        for rule in (r for r in self.rules if r.head.pred == pred):
            for literal in rule.body:
                atom = literal.atom if isinstance(literal, dsl.Negated) else literal
                if isinstance(atom, dsl.ReachAtom):
                    labels |= compile_rpq(atom.rpq, self.registry).labels
                elif isinstance(atom, dsl.Atom) and atom.pred in self.derived:
                    labels |= self._used_labels(atom.pred, seen) if atom.pred not in seen else set()
                elif isinstance(atom, dsl.Atom) and not self.registry.has_node_type(atom.pred):
                    labels.add(self._label(atom.pred))
        return labels

    def _region_gaps(self, pred: str, start: list[int]) -> frozenset[tuple[int, str]]:
        """
        #Feature: Three-valued negation
        #Scenario: Holes on any node a derivation of the predicate could pass through, in either direction
        #Complexity: Time O(n + e) - bounded BFS
        """
        labels = self._used_labels(pred) if pred in self.derived else {self._label(pred)}
        both = {(t, d) for t, _ in labels for d in ("fwd", "rev")}
        seen, frontier = set(start), list(start)
        for _ in range(DEFAULT_MAX_HOPS):
            frontier = [other for node in frontier for label in both
                        for other, _ in self.graph.neighbors(node, label, self.max_rank) if other not in seen]
            if not frontier:
                break
            seen.update(frontier)
        return frozenset(self.evaluator._gaps(seen))

    def _negated_rows(self, literal: dsl.Negated, env: Binding) -> Iterator[tuple[Binding, Fact]]:
        """
        #Feature: Three-valued negation (PRD 7.5)
        #Scenario: Bindings outside the scope are dropped. Absent facts pass, carrying the holes of their region, so a
                   row with holes is UNKNOWN. A fact resting on holes itself also passes as UNKNOWN.
        #Complexity: Time O(n + e) per binding
        """
        values = tuple(env[v.name] for v in literal.atom.args)
        if not self.graph.type_matches(values[0], [literal.scope]):
            return
        found = self.facts[literal.atom.pred].get(values) if literal.atom.pred in self.derived else next(
            (fact for _, fact in self._atom_rows(literal.atom, env, None)), None)
        if found is None:
            yield env, Fact(gaps=self._region_gaps(literal.atom.pred, list(values)))
        elif found.gaps:
            yield env, Fact(gaps=found.gaps)

    def _rows(self, literal: dsl.Literal, env: Binding, source: dict[tuple[int, ...], Fact] | None) -> Iterator[tuple[Binding, Fact]]:
        """
        #Feature: Rule evaluation
        #Scenario: Dispatch one literal under the current bindings
        #Complexity: Time per literal kind
        """
        if isinstance(literal, dsl.Atom):
            yield from self._atom_rows(literal, env, source)
        elif isinstance(literal, dsl.ReachAtom):
            yield from self._reach_rows(literal, env)
        elif isinstance(literal, dsl.Equals):
            yield from self._equals_rows(literal, env)
        elif isinstance(literal, dsl.Negated):
            yield from self._negated_rows(literal, env)
        else:
            actual = _node_prop(self.graph.nodes[env[literal.var.name]], literal.prop)
            if (actual == literal.value) != literal.negate:
                yield env, Fact()

    def solve(self, plan: list[dsl.Literal], delta_at: int | None = None,
              delta: dict[tuple[int, ...], Fact] | None = None) -> Iterator[tuple[Binding, Fact]]:
        """
        #Feature: Rule evaluation
        #Scenario: Backtracking join over the planned literals; one position may read the delta only
        #Complexity: Time O(product of literal fan-outs)
        """
        def step(index: int, env: Binding, fact: Fact) -> Iterator[tuple[Binding, Fact]]:
            if index == len(plan):
                yield env, fact
                return
            source = delta if index == delta_at else None
            for next_env, next_fact in self._rows(plan[index], env, source):
                yield from step(index + 1, next_env, fact.join(next_fact))

        yield from step(0, {}, Fact())

    # ---- fixpoint -----------------------------------------------------------------------

    def _fire(self, rule: dsl.Rule, plan: list[dsl.Literal], delta_at: int | None,
              delta: dict[tuple[int, ...], Fact] | None, out: dict[str, dict[tuple[int, ...], Fact]]) -> None:
        """
        #Feature: Rule evaluation
        #Scenario: Collect the head tuples of one rule that are not known yet; the first derivation is kept
        #Complexity: Time per join
        """
        for env, fact in self.solve(plan, delta_at, delta):
            values = tuple(env[v.name] for v in rule.head.args)
            if values not in self.facts[rule.head.pred] and values not in out[rule.head.pred]:
                out[rule.head.pred][values] = Fact(fact.derivation, fact.gaps, (*fact.rules, rule.head.pred))

    def _stratum(self, rules: list[dsl.Rule]) -> None:
        """
        #Feature: Rule evaluation
        #Scenario: Semi-naive fixpoint of one stratum: after the first pass each rule joins on a delta
        #Complexity: Time O(iterations * join cost)
        """
        plans = [(rule, self._plan(rule.body)) for rule in rules]
        heads = {r.head.pred for r in rules}
        delta: dict[str, dict[tuple[int, ...], Fact]] = defaultdict(dict)
        for rule, plan in plans:
            self._fire(rule, plan, None, None, delta)
        while any(delta.values()):
            for pred, rows in delta.items():
                self.facts[pred].update(rows)
            fresh: dict[str, dict[tuple[int, ...], Fact]] = defaultdict(dict)
            for rule, plan in plans:
                for at, literal in enumerate(plan):
                    if isinstance(literal, dsl.Atom) and literal.pred in heads and delta.get(literal.pred):
                        self._fire(rule, plan, at, delta[literal.pred], fresh)
            delta = fresh

    def run(self) -> "RuleEngine":
        """
        #Feature: Rule evaluation
        #Scenario: Evaluate every stratum in order
        #Complexity: Time per stratum
        """
        for rules in stratify(self.rules):
            self._stratum(rules)
        return self

    # ---- queries ------------------------------------------------------------------------

    def query_rows(self, query: dsl.QueryClause) -> list[dict[str, Any]]:
        """
        #Feature: Rule evaluation
        #Scenario: Distinct bindings of a query; rows are TRUE or UNKNOWN when the query uses negation
        #Complexity: Time per join
        """
        negated = any(isinstance(l, dsl.Negated) for l in query.body) or any(
            self.facts[l.pred] and any(f.gaps for f in self.facts[l.pred].values())
            for l in query.body if isinstance(l, dsl.Atom) and l.pred in self.derived)
        seen: dict[tuple, dict[str, Any]] = {}
        for env, fact in self.solve(self._plan(query.body)):
            names = {k: v for k, v in env.items() if not k.startswith("_")}
            row = {"bindings": names, "derivation": fact.derivation, "gaps": sorted(fact.gaps), "rules": list(fact.rules)}
            if len(names) == 1:
                row["node"] = next(iter(names.values()))
            if negated:
                row["truth"] = TRUTH_UNKNOWN if fact.gaps else TRUTH_TRUE
            seen.setdefault(tuple(sorted(names.items())), row)
        rows = list(seen.values())
        if query.order_by is not None:
            names = sorted({k for r in rows for k in r["bindings"]})
            column = names[query.order_by - 1] if 0 < query.order_by <= len(names) else None
            rows.sort(key=lambda r: self.graph.nodes[r["bindings"][column]].key if column else "", reverse=query.descending)
        return rows[: query.limit]

    def _aggregate_value(self, spec: dsl.AggregateSpec, envs: list[Binding]) -> tuple[Any, int | None]:
        """
        #Feature: Rule evaluation
        #Scenario: count, count_distinct, or min, max, sum, argmax over a numeric node prop
        #Complexity: Time O(b) - bindings in the group
        """
        ids = [env[spec.var.name] for env in envs]
        if spec.fn == "count":
            return len(ids), None
        if spec.fn == "count_distinct":
            return len(set(ids)), None
        pairs = [(v, n) for n in set(ids) if isinstance(v := _node_prop(self.graph.nodes[n], spec.prop or ""), _NUMERIC)]
        if not pairs:
            return None, None
        if spec.fn == "sum":
            return sum(v for v, _ in pairs), None
        chosen = min(pairs) if spec.fn == "min" else max(pairs)
        return chosen[0], chosen[1] if spec.fn == "argmax" else None

    def aggregate_rows(self, query: dsl.QueryClause) -> list[dict[str, Any]]:
        """
        #Feature: Rule evaluation (PRD 7.5 aggregates)
        #Scenario: Group bindings; a value is a lower bound when the contributing region has holes or a walk truncated
        #Complexity: Time per join plus O(b log b)
        """
        spec = query.aggregate
        groups: dict[int | None, list[tuple[Binding, Fact]]] = defaultdict(list)
        for env, fact in self.solve(self._plan(query.body)):
            groups[env[spec.group.name] if spec.group else None].append((env, fact))
        rows = []
        for group, members in groups.items():
            envs = [env for env, _ in members]
            gaps = self.evaluator._gaps({n for env in envs for n in env.values()}) | {g for _, f in members for g in f.gaps}
            value, arg = self._aggregate_value(spec, envs)
            row = {"value": value, "lower_bound": bool(gaps) or self.truncated, "gaps": sorted(gaps)}
            row |= {"node": arg} if arg is not None else {"node": group} if group is not None else {}
            rows.append(row)
        return _order(rows, query, spec)[: query.limit]


def _order(rows: list[dict[str, Any]], query: dsl.QueryClause, spec: dsl.AggregateSpec) -> list[dict[str, Any]]:
    """
    #Feature: Rule evaluation
    #Scenario: Order aggregate rows by output column: with a group, column 1 is the group and column 2 the value
    #Complexity: Time O(r log r) - rows
    """
    if query.order_by is None or (query.order_by == 1 and spec.group is not None):
        return rows
    rows.sort(key=lambda r: (r["value"] is not None, r["value"] or 0), reverse=query.descending)
    return rows


def evaluate_program(evaluator: Any, text: str) -> EvalResult:
    """
    #Feature: Textual DSL (PRD 7.4)
    #Scenario: Run the rules, then answer the last query; with no query, list every derived tuple
    #Complexity: Time per stratum and join

    Raises:
        ValueError: When text is None.
        Errors.Domain.QueryType: On a syntax, typing or stratification error.
    """
    if text is None:
        raise ValueError("[evaluate_program] 'text' is required.")
    program = dsl.parse_program(text)
    engine = RuleEngine(evaluator, program.rules).run()
    if not program.queries:
        return derived_result(engine)
    query = program.queries[-1]
    rows = engine.aggregate_rows(query) if query.aggregate else engine.query_rows(query)
    gaps = {tuple(g) for row in rows for g in row.get("gaps", [])}
    return EvalResult(rows=rows, truth=TRUTH_ROWS, truncated=engine.truncated, gaps=gaps)


def derived_result(engine: RuleEngine, predicates: list[str] | None = None) -> EvalResult:
    """
    #Feature: Rule evaluation (PRD 7.2 Derive)
    #Scenario: Derived relations as rows: predicate, argument nodes, provenance and truth
    #Complexity: Time O(f) - facts
    """
    rows, gaps = [], set()
    for pred, facts in sorted(engine.facts.items()):
        if predicates and pred not in predicates:
            continue
        for values, fact in facts.items():
            gaps |= fact.gaps
            rows.append({"predicate": pred, "nodes": list(values), "derivation": fact.derivation, "rules": list(fact.rules),
                         "gaps": sorted(fact.gaps), "truth": TRUTH_UNKNOWN if fact.gaps else TRUTH_TRUE})
    return EvalResult(rows=rows, truncated=engine.truncated, gaps=gaps)
