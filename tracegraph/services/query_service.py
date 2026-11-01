import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from tracegraph.constants.engine import MAX_EVIDENCE_EDGES
from tracegraph.constants.graph import SNAPSHOT_READY, TIERS
from tracegraph.engine import Answer, Evaluator, GraphSnapshot, SnapshotCache, build_answer, derivation_edge_ids
from tracegraph.errors import Errors
from tracegraph.interfaces.repositories.answers import IAnswerRepository
from tracegraph.interfaces.repositories.graph import IGraphRepository
from tracegraph.interfaces.repositories.snapshots import ISnapshotRepository
from tracegraph.interfaces.services.query import IQueryService
from tracegraph.ontology import Registry
from tracegraph.schemas.query import QueryRequest

logger = logging.getLogger(__name__)


def query_hash(query_ir: dict[str, Any]) -> str:
    """
    #Feature: Reasoning audit
    #Scenario: Stable hash of a query's canonical JSON
    #Complexity: Time O(s) - query size
    """
    return hashlib.sha256(json.dumps(query_ir, sort_keys=True).encode()).hexdigest()[:16]


class QueryService(IQueryService):
    """
    #Feature: Reasoning engine service (PRD 7.1)
    #Scenario: Load the snapshot (cached), evaluate the IR off the event loop, expand evidence, persist the answer
    #Complexity: Time per query plus O(n + e) on a cache miss
    """

    def __init__(self, graph_repository: IGraphRepository, snapshot_repository: ISnapshotRepository,
                 answer_repository: IAnswerRepository, cache: SnapshotCache, registry: Registry) -> None:
        """
        #Feature: Reasoning engine service
        #Scenario: Constructor injection
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a dependency is None.
        """
        deps = (graph_repository, snapshot_repository, answer_repository, cache, registry)
        if any(d is None for d in deps):
            raise ValueError("[QueryService.__init__] All dependencies are required.")
        self._graph, self._snapshots, self._answers, self._cache, self._registry = deps

    async def _snapshot(self, repo_id: int, snapshot_id: int | None) -> dict[str, Any]:
        """
        #Feature: Reasoning engine service
        #Scenario: Requested snapshot (must belong to the repo and be ready) or the latest ready one
        #Complexity: Time O(1) - constant

        Raises:
            Errors.HTTP.BadRequest: When no ready snapshot is available or it belongs to another repo.
        """
        snapshot = (await self._snapshots.get(snapshot_id) if snapshot_id
                    else await self._snapshots.latest_ready(repo_id, None))
        if snapshot is None or snapshot["repo_id"] != repo_id or snapshot["status"] != SNAPSHOT_READY:
            raise Errors.HTTP.BadRequest(f"No ready snapshot {snapshot_id or '(latest)'} for repository {repo_id}.",
                                         {"repo_id": repo_id, "snapshot_id": snapshot_id})
        return snapshot

    async def load_graph(self, repo_id: int, snapshot_id: int | None) -> GraphSnapshot:
        """
        #Feature: Reasoning engine service
        #Scenario: Serve from the LRU cache or load via tg_node_list_at / tg_edge_list_at / holes
        #Complexity: Time O(n + e) on cache miss
        """
        snapshot = await self._snapshot(repo_id, snapshot_id)
        graph = self._cache.get(repo_id, snapshot["seq"])
        if graph is not None:
            return graph
        nodes = await self._graph.nodes_at(repo_id, snapshot["seq"])
        edges = await self._graph.edges_at(repo_id, snapshot["seq"])
        holes = await self._snapshots.coverage_holes(repo_id, snapshot["seq"])
        graph = GraphSnapshot.from_rows(self._registry, repo_id, snapshot["seq"], snapshot["commit_sha"],
                                        nodes, edges, holes)
        self._cache.put(graph)
        logger.info("Snapshot loaded", extra={"repo_id": repo_id, "snapshot_seq": snapshot["seq"],
                                              "nodes": len(graph.nodes), "edges": len(graph.edges)})
        return graph

    async def _evidence(self, repo_id: int, edge_ids: set[int]) -> dict[int, list[dict[str, Any]]]:
        """
        #Feature: Provenance
        #Scenario: Evidence rows for witness edges, grouped by edge
        #Complexity: Time O(k) - edges requested
        """
        if not edge_ids:
            return {}
        rows = await self._graph.evidence_for_edges(repo_id, sorted(edge_ids)[:MAX_EVIDENCE_EDGES])
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["edge_id"], []).append(row)
        return grouped

    async def answer_for(self, graph: GraphSnapshot, query: object, query_ir: dict, max_rows: int) -> Answer:
        """
        #Feature: Reasoning engine service
        #Scenario: Evaluate, attach evidence and persist; latency covers evaluation and evidence lookup
        #Complexity: Time per query
        """
        started = time.perf_counter()
        result = await asyncio.to_thread(Evaluator(graph).evaluate, query)
        evidence = await self._evidence(graph.repo_id, derivation_edge_ids(result, max_rows))
        answer = build_answer(graph, result, query_hash(query_ir), max_rows, evidence)
        answer.latency_ms = int((time.perf_counter() - started) * 1000)
        weakest = max((TIERS.index(d.weakest_tier) for d in answer.derivations), default=0)
        answer.handle = await self._answers.insert(answer.model_dump(mode="json"), query_ir, TIERS[weakest])
        logger.info("Query answered", extra={"repo_id": graph.repo_id, "snapshot_seq": graph.seq,
                                             "answer_handle": answer.handle, "latency_ms": answer.latency_ms,
                                             "truth": answer.truth, "rows": len(answer.rows)})
        return answer

    async def run(self, request: QueryRequest) -> Answer:
        """
        #Feature: Reasoning engine service
        #Scenario: POST /query
        #Complexity: Time per query

        Raises:
            Errors.Domain.QueryType: When the query does not type-check against the registry.
        """
        if request is None:
            raise ValueError("[QueryService.run] 'request' is required.")
        graph = await self.load_graph(request.repo_id, request.snapshot_id)
        query_ir = request.model_dump(mode="json")["query"]
        return await self.answer_for(graph, request.query, query_ir, request.max_rows)

    async def get_answer(self, handle: str) -> Answer:
        """
        #Feature: Reasoning engine service
        #Scenario: GET /answers/{handle}
        #Complexity: Time O(1) - unique index lookup
        """
        row = await self._answers.get(handle)
        return Answer(**row["result"])
