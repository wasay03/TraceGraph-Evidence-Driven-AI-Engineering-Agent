import json
from typing import Any

from tracegraph.interfaces.repositories.graph import IGraphRepository
from tracegraph.repositories.base import UdfRepository

_COMMIT_NODES = "SELECT * FROM tg_node_commit(:repo_id, :seq, CAST(:rows AS jsonb), CAST(:scope AS text[]))"
_COMMIT_EDGES = "SELECT * FROM tg_edge_commit(:repo_id, :seq, CAST(:rows AS jsonb), CAST(:scope AS text[]))"
_COMMIT_EVIDENCE = (
    "SELECT * FROM tg_evidence_commit(:repo_id, CAST(:evidence AS jsonb), CAST(:links AS jsonb), "
    "CAST(:scope AS text[]))"
)
_COMMIT_HOLES = (
    "SELECT tg_coverage_hole_commit(:repo_id, :seq, CAST(:rows AS jsonb), CAST(:scope AS text[]), :prev_seq)"
)
_NODES_BY_TYPE = "SELECT * FROM tg_node_list_by_type_at(:repo_id, :seq, CAST(:type_ids AS smallint[]))"
_NODES_AT = "SELECT * FROM tg_node_list_at(:repo_id, :seq)"
_EDGES_AT = "SELECT * FROM tg_edge_list_at(:repo_id, :seq)"
_SEARCH = "SELECT * FROM tg_node_search(:repo_id, :seq, :text, CAST(:type_ids AS smallint[]), :limit)"
_EVIDENCE = "SELECT * FROM tg_evidence_for_edges(:repo_id, CAST(:edge_ids AS bigint[]))"


def _require(method: str, **values: object) -> None:
    """
    #Feature: Persistence
    #Scenario: None-check required repository arguments
    #Complexity: Time O(k) - linear in arguments

    Raises:
        ValueError: Naming the first missing argument.
    """
    for name, value in values.items():
        if value is None:
            raise ValueError(f"[GraphRepository.{method}] '{name}' is required and must not be None.")


class GraphRepository(UdfRepository, IGraphRepository):
    """
    #Feature: Graph store
    #Scenario: Versioned graph writes and snapshot reads via tg_node_*/tg_edge_*/tg_evidence_* functions
    #Complexity: Time O(1) per call excluding database work
    """

    async def commit_nodes(self, repo_id: int, seq: int, nodes: list[dict], scope: list[str] | None) -> dict[str, int]:
        """
        #Feature: Graph store
        #Scenario: Version nodes into seq
        #Complexity: Time O(n) - linear in nodes
        """
        _require("commit_nodes", repo_id=repo_id, seq=seq, nodes=nodes)
        params = {"repo_id": repo_id, "seq": seq, "rows": json.dumps(nodes), "scope": scope}
        return await self._fetch_one(_COMMIT_NODES, params)

    async def commit_edges(self, repo_id: int, seq: int, edges: list[dict], scope: list[str] | None) -> dict[str, int]:
        """
        #Feature: Graph store
        #Scenario: Version edges into seq
        #Complexity: Time O(e) - linear in edges
        """
        _require("commit_edges", repo_id=repo_id, seq=seq, edges=edges)
        params = {"repo_id": repo_id, "seq": seq, "rows": json.dumps(edges), "scope": scope}
        return await self._fetch_one(_COMMIT_EDGES, params)

    async def commit_evidence(
        self, repo_id: int, evidence: list[dict], links: list[dict], scope: list[str] | None
    ) -> dict[str, int]:
        """
        #Feature: Provenance
        #Scenario: Store evidence and replace links of edges in scope
        #Complexity: Time O(v) - linear in evidence
        """
        _require("commit_evidence", repo_id=repo_id, evidence=evidence, links=links)
        params = {"repo_id": repo_id, "evidence": json.dumps(evidence), "links": json.dumps(links), "scope": scope}
        return await self._fetch_one(_COMMIT_EVIDENCE, params)

    async def commit_holes(
        self, repo_id: int, seq: int, holes: list[dict], scope: list[str] | None, prev_seq: int | None
    ) -> int:
        """
        #Feature: Coverage map
        #Scenario: Write the coverage map of seq
        #Complexity: Time O(h) - linear in holes
        """
        _require("commit_holes", repo_id=repo_id, seq=seq, holes=holes)
        params = {"repo_id": repo_id, "seq": seq, "rows": json.dumps(holes), "scope": scope, "prev_seq": prev_seq}
        return await self._fetch_scalar(_COMMIT_HOLES, params)

    async def nodes_by_type(self, repo_id: int, seq: int, type_ids: list[int]) -> list[dict[str, Any]]:
        """
        #Feature: Graph store
        #Scenario: Nodes of given types at seq
        #Complexity: Time O(n) - linear in matching nodes
        """
        _require("nodes_by_type", repo_id=repo_id, seq=seq, type_ids=type_ids)
        return await self._fetch_all(_NODES_BY_TYPE, {"repo_id": repo_id, "seq": seq, "type_ids": type_ids})

    async def nodes_at(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Graph store
        #Scenario: All nodes at seq
        #Complexity: Time O(n) - linear in nodes
        """
        _require("nodes_at", repo_id=repo_id, seq=seq)
        return await self._fetch_all(_NODES_AT, {"repo_id": repo_id, "seq": seq})

    async def edges_at(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Graph store
        #Scenario: All edges at seq
        #Complexity: Time O(e) - linear in edges
        """
        _require("edges_at", repo_id=repo_id, seq=seq)
        return await self._fetch_all(_EDGES_AT, {"repo_id": repo_id, "seq": seq})

    async def search_nodes(
        self, repo_id: int, seq: int, text: str, type_ids: list[int] | None, limit: int
    ) -> list[dict[str, Any]]:
        """
        #Feature: Entity resolution
        #Scenario: Ranked fuzzy candidates
        #Complexity: Time O(log n) - trigram index
        """
        _require("search_nodes", repo_id=repo_id, seq=seq, text=text, limit=limit)
        params = {"repo_id": repo_id, "seq": seq, "text": text, "type_ids": type_ids, "limit": limit}
        return await self._fetch_all(_SEARCH, params)

    async def evidence_for_edges(self, repo_id: int, edge_ids: list[int]) -> list[dict[str, Any]]:
        """
        #Feature: Provenance
        #Scenario: Evidence rows linked to edges
        #Complexity: Time O(k) - linear in edges requested
        """
        _require("evidence_for_edges", repo_id=repo_id, edge_ids=edge_ids)
        return await self._fetch_all(_EVIDENCE, {"repo_id": repo_id, "edge_ids": edge_ids})
