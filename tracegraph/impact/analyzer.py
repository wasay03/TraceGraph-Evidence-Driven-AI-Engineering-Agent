from dataclasses import dataclass, field
from typing import Any

from tracegraph.constants import impact as c
from tracegraph.constants.extract import HOLE_DYNAMIC_ATTRIBUTE, HOLE_DYNAMIC_SQL, HOLE_UNTYPED_RECEIVER
from tracegraph.constants.graph import TIER_RANK
from tracegraph.engine.evaluator import Derivation, Evaluator
from tracegraph.engine.graph import GraphSnapshot
from tracegraph.engine.rpq import compile_rpq
from tracegraph.impact import changespec as cs
from tracegraph.impact.findings import Finding, Obligation, merge, score
from tracegraph.impact.invariants import Violation, check_all
from tracegraph.impact.overlay import Overlay, apply_drops, build_overlay, target_of
from tracegraph.impact.rules import RULE_PACKS

_SCHEMA_CHANGES = (cs.MakeColumnNullable, cs.DropColumn, cs.ChangeColumnType, cs.AddColumn)
_CALLABLE_CHANGES = (cs.ChangeReturnType, cs.ChangeSignature, cs.RemoveSymbol, cs.ModifyBody, cs.RenameSymbol, cs.AddRaise)


@dataclass(slots=True)
class TestPick:
    """
    #Feature: Test selection (PRD 8.2 step 6)
    #Scenario: Test reaching an impacted node, ranked by TESTS strength over distance
    #Complexity: Time O(1) - constant
    """

    node: int
    strength: float
    distance: int
    score: float
    derivation: Derivation


@dataclass(slots=True)
class InvariantDelta:
    """
    #Feature: Invariant diff (PRD 8.2 step 7)
    #Scenario: Violation that appears (new) or disappears (resolved) between base and overlay
    #Complexity: Time O(1) - constant
    """

    violation: Violation
    status: str


@dataclass(slots=True)
class ImpactResult:
    """
    #Feature: Impact analysis
    #Scenario: Everything the analyzer derived, before rendering
    #Complexity: Time O(1) - constant
    """

    overlay: Overlay
    findings: list[Finding] = field(default_factory=list)
    obligations: list[Obligation] = field(default_factory=list)
    tests: list[TestPick] = field(default_factory=list)
    invariants: list[InvariantDelta] = field(default_factory=list)
    gaps: set[tuple[int, str]] = field(default_factory=set)


def _violation_key(violation: Violation) -> tuple[str, int, str]:
    """
    #Feature: Invariant diff
    #Scenario: Identity of a violation across base and overlay
    #Complexity: Time O(1) - constant
    """
    return violation.invariant, violation.node, violation.message


class ImpactAnalyzer:
    """
    #Feature: Impact analysis (PRD 8.2)
    #Scenario: Normalize -> overlay -> classify with rule packs -> propagate -> obligations -> tests ->
               invariant diff -> rank
    #Complexity: Time O(|findings| * (n + e) * q) - dominated by propagation walks
    """

    def __init__(self, base: GraphSnapshot) -> None:
        """
        #Feature: Impact analysis
        #Scenario: Bind to the base snapshot
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When base is None.
        """
        if base is None:
            raise ValueError("[ImpactAnalyzer.__init__] 'base' is required.")
        self.base = base
        self._evaluator = Evaluator(base)

    def _holes_as_unknown(self, specs: list[Any], findings: dict[int, Finding]) -> set[tuple[int, str]]:
        """
        #Feature: Impact analysis
        #Scenario: Coverage holes that could hide impact become UNKNOWN: untyped receivers calling a method of the
                   changed name, and dynamic SQL for schema changes
        #Complexity: Time O(h * s) - holes times specs
        """
        gaps = set()
        targets = {target_of(self.base, s).id for s in specs}
        callables = {target_of(self.base, s).key: s for s in specs if isinstance(s, _CALLABLE_CHANGES)}
        names = {key.rsplit(".", 1)[-1]: s for key, s in callables.items()}
        schema = next((s for s in specs if isinstance(s, _SCHEMA_CHANGES)), None)
        for node, holes in self.base.holes.items():
            for hole in holes if node not in targets else []:
                detail = hole.get("detail") or {}
                spec = names.get(detail.get("method")) if hole["kind"] == HOLE_UNTYPED_RECEIVER else (
                    schema if hole["kind"] == HOLE_DYNAMIC_SQL else None)
                if hole["kind"] == HOLE_DYNAMIC_ATTRIBUTE and detail.get("module"):
                    spec = next((s for key, s in callables.items() if key.startswith(detail["module"] + ".")), None)
                if spec is not None:
                    gaps.add((node, hole["kind"]))
                    merge(findings, Finding(node, c.UNKNOWN, f"coverage_hole:{hole['kind']}", spec.kind, "coverage"))
        return gaps

    @staticmethod
    def _add_propagated(findings: dict[int, Finding], finding: Finding) -> None:
        """
        #Feature: Impact analysis
        #Scenario: Propagation only fills nodes no rule classified (a GUARDED caller stays GUARDED)
        #Complexity: Time O(1) - constant
        """
        existing = findings.get(finding.node)
        if existing is None or (existing.rule == "propagation" and finding.distance < existing.distance):
            findings[finding.node] = finding

    def _propagate(self, findings: dict[int, Finding]) -> None:
        """
        #Feature: Impact analysis (PRD 8.2 step 4)
        #Scenario: Transitive callers/injectors of affected callables are AT_RISK; endpoints handling any affected
                   callable are AT_RISK
        #Complexity: Time O(|affected| * (n + e) * q)
        """
        nfa = compile_rpq(c.PROPAGATION_RPQ, self.base.registry)
        for finding in [f for f in findings.values() if f.cls != c.GUARDED]:
            if not self.base.type_matches(finding.node, ["Callable"]):
                continue
            walk = self._evaluator.walk({finding.node: finding.derivation}, nfa, c.PROPAGATION_MAX_HOPS,
                                        "hypothesized", ["Callable"], include_start=True)
            for node, deriv in walk.reached.items():
                hops = len(deriv.edges) - len(finding.derivation.edges)
                if node != finding.node:
                    self._add_propagated(findings, Finding(node, c.AT_RISK, "transitive_dependent", finding.change,
                                                           "propagation", deriv, finding.distance + hops))
                for endpoint, edge in self.base.neighbors(node, ("HANDLED_BY", "rev"), TIER_RANK["hypothesized"]):
                    self._add_propagated(findings, Finding(endpoint, c.AT_RISK, "endpoint_reaches_impact",
                                                           finding.change, "propagation", deriv.extend(edge),
                                                           finding.distance + hops + 1))

    def _select_tests(self, findings: dict[int, Finding], seeds: dict[int, str]) -> list[TestPick]:
        """
        #Feature: Test selection
        #Scenario: Tests whose TESTS edges (directly or through callers) reach any impacted node or seed
        #Complexity: Time O((n + e) * q) - one multi-source walk
        """
        starts = {f.node: Derivation() for f in findings.values() if f.cls != c.GUARDED}
        starts.update({s: Derivation() for s in seeds if s in self.base.nodes})
        walk = self._evaluator.walk(starts, compile_rpq(c.TEST_SELECTION_RPQ, self.base.registry),
                                    c.PROPAGATION_MAX_HOPS, "hypothesized", ["Test"])
        picks = []
        for test, deriv in walk.reached.items():
            strength = self.base.edges[deriv.edges[-1]].props.get("strength") or 0.5
            distance = len(deriv.edges)
            picks.append(TestPick(test, strength, distance, round(strength / distance, 4), deriv))
        return sorted(picks, key=lambda p: (-p.score, self.base.nodes[p.node].key))[: c.MAX_TESTS]

    def _invariant_diff(self, overlay: Overlay, specs: list[Any]) -> list[InvariantDelta]:
        """
        #Feature: Invariant diff
        #Scenario: Violations new in the overlay or resolved by it; schema changes without a migration add INV-001
        #Complexity: Time O(cost of the invariant pack, twice)
        """
        base = {_violation_key(v): v for v in check_all(self.base)}
        after = {_violation_key(v): v for v in check_all(overlay.graph)}
        deltas = [InvariantDelta(v, "new") for k, v in after.items() if k not in base]
        deltas += [InvariantDelta(v, "resolved") for k, v in base.items() if k not in after]
        for spec in (s for s in specs if isinstance(s, _SCHEMA_CHANGES)):
            column = target_of(self.base, spec)
            deltas.append(InvariantDelta(Violation("INV-001", "error", column.id,
                                                   f"{spec.kind} on {column.key} has no migration yet"), "new"))
        return deltas

    def _finalize(self, findings: dict[int, Finding]) -> list[Finding]:
        """
        #Feature: Impact ranking
        #Scenario: Derivations through inferred/hypothesized edges are UNKNOWN; then score and sort
        #Complexity: Time O(f log f) - sort
        """
        out = []
        for finding in findings.values():
            if finding.derivation.tier_rank >= TIER_RANK["inferred"] and finding.cls in (c.BREAKS, c.AT_RISK):
                finding.cls, finding.reason = c.UNKNOWN, f"{finding.reason}:weak_tier"
            finding.score = score(finding, self.base.degree(finding.node, ["CALLS", "INJECTS"], "rev"))
            out.append(finding)
        return sorted(out, key=lambda f: (c.CLASS_PRIORITY[f.cls], -f.score, self.base.nodes[f.node].key))

    def analyze(self, specs: list[Any]) -> ImpactResult:
        """
        #Feature: Impact analysis
        #Scenario: Full algorithm for a list of ChangeSpecs on the base snapshot
        #Complexity: Time O(|findings| * (n + e) * q)

        Raises:
            ValueError: When specs is empty.
            Errors.Domain.ChangeSpec: When a target cannot be resolved.
        """
        if not specs:
            raise ValueError("[ImpactAnalyzer.analyze] At least one ChangeSpec is required.")
        overlay = build_overlay(self.base, specs)
        findings: dict[int, Finding] = {}
        obligations: list[Obligation] = []
        for spec in specs:
            found, required = RULE_PACKS[type(spec)](self.base, spec, target_of(self.base, spec))
            for finding in found:
                merge(findings, finding)
            obligations += required
        gaps = self._holes_as_unknown(specs, findings)
        self._propagate(findings)
        tests = self._select_tests(findings, overlay.seeds)
        apply_drops(overlay)
        return ImpactResult(overlay, self._finalize(findings), obligations, tests,
                            self._invariant_diff(overlay, specs), gaps)
