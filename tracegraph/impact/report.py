from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from tracegraph.constants.graph import TIERS
from tracegraph.engine.answer import EvidenceOut, NodeOut, PathStep, SnapshotRef, derivation_out, node_out
from tracegraph.engine.graph import GraphSnapshot
from tracegraph.impact.analyzer import ImpactResult


class FindingOut(BaseModel):
    """
    #Feature: Impact report
    #Scenario: One classified finding with its witness path and evidence
    #Complexity: Time O(1) - constant
    """

    node: NodeOut
    cls: str
    reason: str
    change: str
    rule: str
    distance: int
    score: float
    weakest_tier: str
    path: list[PathStep]
    evidence: list[EvidenceOut]


class ObligationOut(BaseModel):
    """
    #Feature: Impact report
    #Scenario: Required follow-up independent of code edits
    #Complexity: Time O(1) - constant
    """

    kind: str
    target: NodeOut
    detail: str


class TestOut(BaseModel):
    """
    #Feature: Impact report
    #Scenario: Selected test with rank inputs
    #Complexity: Time O(1) - constant
    """

    node: NodeOut
    strength: float
    distance: int
    score: float


class InvariantChangeOut(BaseModel):
    """
    #Feature: Impact report
    #Scenario: Invariant violation introduced or resolved by the change
    #Complexity: Time O(1) - constant
    """

    invariant: str
    severity: str
    status: str
    truth: str
    node: NodeOut
    message: str


class ImpactReport(BaseModel):
    """
    #Feature: Impact report (PRD 8)
    #Scenario: Findings by class, obligations, ranked tests, invariant diff and coverage gaps; stored under a handle
    #Complexity: Time O(1) - constant
    """

    handle: str | None = None
    query_hash: str
    snapshot: SnapshotRef
    overlay: int | None = None
    truth: str = "ROWS"
    changes: list[dict[str, Any]]
    summary: dict[str, int]
    findings: list[FindingOut]
    obligations: list[ObligationOut]
    tests: list[TestOut]
    invariants: list[InvariantChangeOut]
    coverage_gaps: list[dict[str, str]]
    derivations: list[Any] = Field(default_factory=list)
    latency_ms: int = 0


def _render(base: GraphSnapshot, overlay: GraphSnapshot, node_id: int) -> NodeOut:
    """
    #Feature: Impact report
    #Scenario: Render from the overlay (hypothesized nodes) and fall back to the base (dropped nodes)
    #Complexity: Time O(1) - constant
    """
    return node_out(overlay if node_id in overlay.nodes else base, node_id)


def finding_edge_ids(result: ImpactResult) -> set[int]:
    """
    #Feature: Impact report
    #Scenario: Witness edges whose evidence the report renders
    #Complexity: Time O(f * p) - findings times path length
    """
    return {e for f in result.findings for e in f.derivation.edges}


def build_report(base: GraphSnapshot, result: ImpactResult, changes: list[dict[str, Any]], query_hash: str,
                 evidence: dict[int, list[dict[str, Any]]]) -> ImpactReport:
    """
    #Feature: Impact report
    #Scenario: Render an ImpactResult; nodes resolve against the overlay so hypothesized members render too
    #Complexity: Time O(f * p) - findings times path length
    """
    graph = result.overlay.graph
    findings = []
    for f in result.findings:
        rendered = derivation_out(graph, 0, f.derivation, evidence)
        findings.append(FindingOut(node=_render(base, graph, f.node), cls=f.cls, reason=f.reason, change=f.change,
                                   rule=f.rule, distance=f.distance, score=f.score,
                                   weakest_tier=TIERS[f.derivation.tier_rank], path=rendered.path,
                                   evidence=rendered.evidence))
    obligations = [ObligationOut(kind=o.kind, target=_render(base, graph, o.target), detail=o.detail) for o in result.obligations]
    tests = [TestOut(node=node_out(base, t.node), strength=t.strength, distance=t.distance, score=t.score)
             for t in result.tests]
    invariants = [InvariantChangeOut(invariant=d.violation.invariant, severity=d.violation.severity, status=d.status,
                                     truth=d.violation.truth, node=_render(base, graph, d.violation.node),
                                     message=d.violation.message) for d in result.invariants]
    gaps = [{"node": node_out(base, n).key, "kind": k} for n, k in sorted(result.gaps)]
    summary = dict(Counter(f.cls for f in findings))
    summary.update({"obligations": len(obligations), "tests": len(tests),
                    "new_violations": sum(1 for d in result.invariants if d.status == "new")})
    return ImpactReport(query_hash=query_hash, snapshot={"repo": base.repo_id, "seq": base.seq, "commit": base.commit},
                        overlay=graph.overlay_id, changes=changes, summary=summary, findings=findings,
                        obligations=obligations, tests=tests, invariants=invariants, coverage_gaps=gaps)
