from typing import Any

from pydantic import BaseModel, Field

from tracegraph.constants.engine import MAX_DERIVATIONS
from tracegraph.constants.graph import TIERS
from tracegraph.engine.evaluator import Derivation, EvalResult
from tracegraph.engine.graph import GraphSnapshot


class NodeOut(BaseModel):
    """
    #Feature: Answer contract (PRD 7.7)
    #Scenario: Compact node reference in rows and gaps
    #Complexity: Time O(1) - constant
    """

    id: int
    type: str
    key: str
    file: str | None = None
    line: int | None = None


class PathStep(BaseModel):
    """
    #Feature: Answer contract
    #Scenario: One hop of a witness path
    #Complexity: Time O(1) - constant
    """

    edge: int
    type: str
    src: str
    dst: str
    tier: str


class EvidenceOut(BaseModel):
    """
    #Feature: Answer contract
    #Scenario: Source lines justifying a hop
    #Complexity: Time O(1) - constant
    """

    edge: int
    file: str | None
    lines: list[int | None]
    method: str
    extractor: str


class DerivationOut(BaseModel):
    """
    #Feature: Answer contract
    #Scenario: Why a row holds: path, rules, evidence, weakest tier and confidence
    #Complexity: Time O(1) - constant
    """

    row: int
    path: list[PathStep]
    rules: list[str] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list)
    weakest_tier: str
    confidence: float


class CoverageGap(BaseModel):
    """
    #Feature: Answer contract
    #Scenario: Coverage hole that limits the answer
    #Complexity: Time O(1) - constant
    """

    node: str
    kind: str


class SnapshotRef(BaseModel):
    """
    #Feature: Answer contract
    #Scenario: Snapshot an answer was computed on
    #Complexity: Time O(1) - constant
    """

    repo: int
    seq: int
    commit: str


class Answer(BaseModel):
    """
    #Feature: Answer contract
    #Scenario: Every engine answer carries its snapshot, truth, rows, derivations and coverage gaps
    #Complexity: Time O(1) - constant
    """

    handle: str | None = None
    query_hash: str
    snapshot: SnapshotRef
    overlay: int | None = None
    truth: str
    rows: list[dict[str, Any]]
    derivations: list[DerivationOut]
    coverage_gaps: list[CoverageGap]
    truncated: bool
    latency_ms: int = 0


def node_out(graph: GraphSnapshot, node_id: int) -> NodeOut:
    """
    #Feature: Answer contract
    #Scenario: NodeOut for an id (unknown ids render with type "?")
    #Complexity: Time O(1) - constant
    """
    n = graph.nodes.get(node_id)
    if n is None:
        return NodeOut(id=node_id, type="?", key=str(node_id))
    return NodeOut(id=n.id, type=n.type, key=n.key, file=n.file, line=n.line_start)


def _rows(graph: GraphSnapshot, result: EvalResult, max_rows: int) -> list[tuple[dict[str, Any], Derivation | None]]:
    """
    #Feature: Answer contract
    #Scenario: Render operator rows (or the node set) with their derivations
    #Complexity: Time O(r log r) - sort by key
    """
    if result.rows is None:
        ordered = sorted(result.nodes.items(), key=lambda kv: (graph.nodes[kv[0]].type, graph.nodes[kv[0]].key)
                         if kv[0] in graph.nodes else ("", ""))
        return [({"node": node_out(graph, n).model_dump()}, d) for n, d in ordered[:max_rows]]
    out = []
    for row in result.rows[:max_rows]:
        rendered = {k: v for k, v in row.items() if k not in ("derivation", "gaps")}
        for key in ("node", "source"):
            if key in row:
                rendered[key] = node_out(graph, row[key]).model_dump()
        if "nodes" in row:
            rendered["nodes"] = [node_out(graph, n).model_dump() for n in row["nodes"]]
        if row.get("gaps"):
            rendered["gaps"] = [{"node": node_out(graph, n).key, "kind": k} for n, k in row["gaps"]]
        out.append((rendered, row.get("derivation") or result.nodes.get(row.get("node"))))
    return out


def derivation_edge_ids(result: EvalResult, max_rows: int) -> set[int]:
    """
    #Feature: Answer contract
    #Scenario: Edge ids on the derivations that will be rendered, for evidence lookup
    #Complexity: Time O(r * p) - rows times path length
    """
    derivs = list(result.nodes.values()) + [r["derivation"] for r in result.rows or [] if r.get("derivation")]
    return {e for d in derivs[: max(max_rows, MAX_DERIVATIONS)] for e in d.edges}


def derivation_out(graph: GraphSnapshot, index: int, deriv: Derivation,
                evidence: dict[int, list[dict[str, Any]]]) -> DerivationOut:
    """
    #Feature: Answer contract
    #Scenario: Render one derivation with its evidence spans
    #Complexity: Time O(p) - path length
    """
    steps, spans = [], []
    for edge_id in deriv.edges:
        edge = graph.edges.get(edge_id)
        if edge is None:
            continue
        steps.append(PathStep(edge=edge.id, type=edge.type, src=node_out(graph, edge.src).key,
                              dst=node_out(graph, edge.dst).key, tier=edge.tier))
        spans += [EvidenceOut(edge=edge.id, file=ev["file_path"], lines=[ev["line_start"], ev["line_end"]],
                              method=ev["method"], extractor=ev["extractor"]) for ev in evidence.get(edge.id, [])]
    return DerivationOut(row=index, path=steps, evidence=spans, weakest_tier=TIERS[deriv.tier_rank],
                         confidence=round(deriv.confidence, 4))


def build_answer(graph: GraphSnapshot, result: EvalResult, query_hash: str, max_rows: int,
                 evidence: dict[int, list[dict[str, Any]]]) -> Answer:
    """
    #Feature: Answer contract
    #Scenario: Assemble the Answer from an evaluation result and the evidence of its witness edges
    #Complexity: Time O(r * p) - rows times path length
    """
    rendered = _rows(graph, result, max_rows)
    derivations = [derivation_out(graph, i, d, evidence) for i, (_, d) in enumerate(rendered[:MAX_DERIVATIONS])
                   if d is not None and d.edges]
    gaps = [CoverageGap(node=node_out(graph, n).key, kind=k) for n, k in sorted(result.gaps)][:MAX_DERIVATIONS]
    return Answer(query_hash=query_hash, overlay=graph.overlay_id,
                  snapshot={"repo": graph.repo_id, "seq": graph.seq, "commit": graph.commit},
                  truth=result.truth, rows=[r for r, _ in rendered], derivations=derivations, coverage_gaps=gaps,
                  truncated=result.truncated or len(result.rows or result.nodes) > max_rows)
