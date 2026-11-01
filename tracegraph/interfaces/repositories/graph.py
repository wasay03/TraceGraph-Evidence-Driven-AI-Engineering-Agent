from abc import ABC, abstractmethod
from typing import Any


class IGraphRepository(ABC):
    """
    #Feature: Graph store
    #Scenario: Contract for versioned graph writes and snapshot reads
    #Complexity: Time O(1) per call excluding database work
    """

    @abstractmethod
    async def commit_nodes(self, repo_id: int, seq: int, nodes: list[dict], scope: list[str] | None) -> dict[str, int]:
        """
        #Feature: Graph store
        #Scenario: Version nodes into seq; returns inserted/closed counts
        #Complexity: Time O(n) - linear in nodes
        """

    @abstractmethod
    async def commit_edges(self, repo_id: int, seq: int, edges: list[dict], scope: list[str] | None) -> dict[str, int]:
        """
        #Feature: Graph store
        #Scenario: Version edges into seq; returns inserted/closed counts
        #Complexity: Time O(e) - linear in edges
        """

    @abstractmethod
    async def commit_evidence(
        self, repo_id: int, evidence: list[dict], links: list[dict], scope: list[str] | None
    ) -> dict[str, int]:
        """
        #Feature: Provenance
        #Scenario: Store evidence and replace links of edges in scope
        #Complexity: Time O(v) - linear in evidence
        """

    @abstractmethod
    async def commit_holes(
        self, repo_id: int, seq: int, holes: list[dict], scope: list[str] | None, prev_seq: int | None
    ) -> int:
        """
        #Feature: Coverage map
        #Scenario: Write the coverage map of seq; returns total holes
        #Complexity: Time O(h) - linear in holes
        """

    @abstractmethod
    async def nodes_by_type(self, repo_id: int, seq: int, type_ids: list[int]) -> list[dict[str, Any]]:
        """
        #Feature: Graph store
        #Scenario: Nodes of given types at seq
        #Complexity: Time O(n) - linear in matching nodes
        """

    @abstractmethod
    async def nodes_at(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Graph store
        #Scenario: All nodes at seq (in-memory snapshot loader)
        #Complexity: Time O(n) - linear in nodes
        """

    @abstractmethod
    async def edges_at(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Graph store
        #Scenario: All edges at seq (in-memory snapshot loader)
        #Complexity: Time O(e) - linear in edges
        """

    @abstractmethod
    async def search_nodes(
        self, repo_id: int, seq: int, text: str, type_ids: list[int] | None, limit: int
    ) -> list[dict[str, Any]]:
        """
        #Feature: Entity resolution
        #Scenario: Ranked fuzzy candidates for free text
        #Complexity: Time O(log n) - trigram index
        """

    @abstractmethod
    async def evidence_for_edges(self, repo_id: int, edge_ids: list[int]) -> list[dict[str, Any]]:
        """
        #Feature: Provenance
        #Scenario: Evidence rows linked to edges
        #Complexity: Time O(k) - linear in edges requested
        """
