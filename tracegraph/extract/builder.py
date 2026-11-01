from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from tracegraph.extract.records import EdgeRecord, EvidenceRecord, HoleRecord, NodeRecord, NodeRef, Span
from tracegraph.ontology import Registry, natural_key_of, validate_edge, validate_node
from tracegraph.utilities.ids import stable_id


@dataclass(slots=True)
class GraphPayload:
    """
    #Feature: Typed writer
    #Scenario: Validated rows ready for the tg_*_commit stored functions
    #Complexity: Time O(1) - constant
    """

    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    holes: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def _span_cols(span: Span | None) -> dict[str, int | None]:
    """
    #Feature: Typed writer
    #Scenario: Flatten an optional span into span_lo/span_hi columns
    #Complexity: Time O(1) - constant
    """
    return {"span_lo": span.start if span else None, "span_hi": span.end if span else None}


class GraphBuilder:
    """
    #Feature: Typed writer
    #Scenario: Collect records from all passes, merge duplicates, validate against the registry, emit rows
    #Complexity: Time O(n + e) - linear in records

    Later passes may enrich a node by adding it again; non-None props from the later record win.
    """

    def __init__(self, registry: Registry, repo_id: int, commit_sha: str, extractor_versions: dict[str, str]) -> None:
        """
        #Feature: Typed writer
        #Scenario: Bind the builder to a repo, commit and extractor version map
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a required argument is missing.
        """
        if registry is None or repo_id is None or not commit_sha:
            raise ValueError("[GraphBuilder.__init__] 'registry', 'repo_id' and 'commit_sha' are required.")
        self._registry = registry
        self._repo_id = repo_id
        self._commit = commit_sha
        self._versions = extractor_versions or {}
        self._nodes: dict[NodeRef, NodeRecord] = {}
        self._edges: dict[int, EdgeRecord] = {}
        self._holes: list[HoleRecord] = []

    def node_id(self, ref: NodeRef) -> int:
        """
        #Feature: Graph identity
        #Scenario: Stable id hash(repo_id, node type, natural key)
        #Complexity: Time O(k) - linear in key length
        """
        return stable_id(self._repo_id, "node", ref.type, ref.key)

    def ref_for(self, type_name: str, props: dict[str, Any]) -> NodeRef:
        """
        #Feature: Typed writer
        #Scenario: Build a NodeRef from a type and the props holding its key fields
        #Complexity: Time O(k) - linear in key fields
        """
        return NodeRef(type_name, natural_key_of(self._registry, type_name, props))

    def add_node(self, record: NodeRecord) -> NodeRef:
        """
        #Feature: Typed writer
        #Scenario: Add or enrich a node; returns its ref
        #Complexity: Time O(p) - linear in props
        """
        ref = self.ref_for(record.type, record.props)
        existing = self._nodes.get(ref)
        if existing is None:
            self._nodes[ref] = record
        else:
            existing.props.update({k: v for k, v in record.props.items() if v is not None})
            existing.file_path = existing.file_path or record.file_path
            existing.span = existing.span or record.span
        return ref

    def has_node(self, ref: NodeRef) -> bool:
        """
        #Feature: Typed writer
        #Scenario: Whether a node was produced by any pass so far
        #Complexity: Time O(1) - constant
        """
        return ref in self._nodes

    def node_props(self, ref: NodeRef) -> dict[str, Any]:
        """
        #Feature: Typed writer
        #Scenario: Read the merged props of a node produced earlier
        #Complexity: Time O(1) - constant

        Raises:
            KeyError: When the node was never added.
        """
        return self._nodes[ref].props

    def node_record(self, ref: NodeRef) -> NodeRecord:
        """
        #Feature: Typed writer
        #Scenario: The merged record of a node produced earlier
        #Complexity: Time O(1) - constant

        Raises:
            KeyError: When the node was never added.
        """
        return self._nodes[ref]

    def refs_of_type(self, type_name: str) -> list[NodeRef]:
        """
        #Feature: Typed writer
        #Scenario: Nodes of one concrete type, for passes that join on earlier output
        #Complexity: Time O(n) - linear in nodes
        """
        return [ref for ref in self._nodes if ref.type == type_name]

    def add_edge(self, record: EdgeRecord) -> None:
        """
        #Feature: Typed writer
        #Scenario: Add an edge; duplicates (same type, src, dst) merge their evidence
        #Complexity: Time O(v) - linear in evidence
        """
        record.owner_file = record.owner_file or next((e.file_path for e in record.evidence if e.file_path), None)
        edge_id = stable_id(self._repo_id, "edge", record.type, self.node_id(record.src), self.node_id(record.dst))
        existing = self._edges.get(edge_id)
        if existing is None:
            self._edges[edge_id] = record
            return
        existing.evidence.extend(e for e in record.evidence if e not in existing.evidence)
        for key, value in record.props.items():
            existing.props.setdefault(key, value)

    def add_hole(self, record: HoleRecord) -> None:
        """
        #Feature: Coverage map
        #Scenario: Record a coverage hole
        #Complexity: Time O(1) - constant
        """
        self._holes.append(record)

    def _evidence_row(self, ev: EvidenceRecord) -> dict[str, Any]:
        """
        #Feature: Provenance
        #Scenario: Content-addressed evidence row
        #Complexity: Time O(1) - constant
        """
        span = (ev.span.start, ev.span.end) if ev.span else (None, None)
        ev_id = stable_id(self._repo_id, "evidence", ev.extractor, ev.method, ev.file_path, *span,
                          ev.snippet_hash, ev.rationale)
        return {"id": ev_id, "extractor": ev.extractor, "extractor_version": self._versions.get(ev.extractor, "0"),
                "method": ev.method, "file_path": ev.file_path, **_span_cols(ev.span),
                "snippet_hash": ev.snippet_hash, "commit_sha": self._commit, "confidence": ev.confidence,
                "rationale": ev.rationale}

    def _node_rows(self) -> list[dict[str, Any]]:
        """
        #Feature: Typed writer
        #Scenario: Validate every node and emit tg_node_commit rows
        #Complexity: Time O(n * p) - nodes times props

        Raises:
            Errors.Domain.*: On the first registry violation.
        """
        rows = []
        for ref, rec in self._nodes.items():
            validate_node(self._registry, rec.type, rec.props, rec.tier)
            rows.append({"id": self.node_id(ref), "type_id": self._registry.node_type(rec.type).id,
                         "natural_key": ref.key, "props": rec.props, "tier": rec.tier,
                         "file_path": rec.file_path, **_span_cols(rec.span)})
        return rows

    def _edge_rows(self, payload: GraphPayload, known: set[NodeRef] | None) -> Counter:
        """
        #Feature: Typed writer
        #Scenario: Validate edges, drop dangling ones, emit edge, evidence and link rows
        #Complexity: Time O(e * v) - edges times evidence

        Args:
            payload: Payload to append rows to.
            known: Refs that exist outside this batch (incremental); None means full index.

        Returns:
            Counter of dropped dangling edges per edge type.
        """
        dropped: Counter = Counter()
        evidence: dict[int, dict[str, Any]] = {}
        for edge_id, rec in self._edges.items():
            if not all(r in self._nodes or (known is not None and r in known) for r in (rec.src, rec.dst)):
                dropped[rec.type] += 1
                continue
            validate_edge(self._registry, rec.type, rec.src.type, rec.dst.type, rec.props, rec.tier,
                          len(rec.evidence), any(e.span for e in rec.evidence))
            payload.edges.append({"id": edge_id, "type_id": self._registry.edge_type(rec.type).id,
                                  "src": self.node_id(rec.src), "dst": self.node_id(rec.dst), "props": rec.props,
                                  "tier": rec.tier, "confidence": rec.confidence, "owner_file": rec.owner_file})
            for ev in rec.evidence:
                row = self._evidence_row(ev)
                evidence[row["id"]] = row
                payload.links.append({"edge_id": edge_id, "evidence_id": row["id"]})
        payload.evidence = list(evidence.values())
        return dropped

    def _hole_rows(self) -> list[dict[str, Any]]:
        """
        #Feature: Coverage map
        #Scenario: Emit tg_coverage_hole_commit rows
        #Complexity: Time O(h) - linear in holes
        """
        return [{"node_id": self.node_id(h.node) if h.node else None, "kind": h.kind, "file_path": h.file_path,
                 **_span_cols(h.span), "detail": dict(h.detail)} for h in self._holes]

    def finalize(self, known: set[NodeRef] | None = None) -> GraphPayload:
        """
        #Feature: Typed writer
        #Scenario: Validate the whole batch and produce commit payloads plus stats
        #Complexity: Time O(n + e + h) - linear in records

        Args:
            known: Refs that exist outside this batch (incremental); None for a full index.

        Returns:
            GraphPayload.

        Raises:
            Errors.Domain.*: On the first registry violation; the batch must not be committed.
        """
        payload = GraphPayload(nodes=self._node_rows(), holes=self._hole_rows())
        dropped = self._edge_rows(payload, known)
        payload.stats = {"nodes": len(payload.nodes), "edges": len(payload.edges),
                         "evidence": len(payload.evidence), "coverage_holes": len(payload.holes),
                         "dangling_edges_dropped": dict(dropped)}
        return payload
