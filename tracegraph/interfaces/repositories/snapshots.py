from abc import ABC, abstractmethod
from typing import Any


class ISnapshotRepository(ABC):
    """
    #Feature: Snapshots
    #Scenario: Contract for snapshot lifecycle and per-snapshot graph summaries
    #Complexity: Time O(1) - constant per call excluding database work
    """

    @abstractmethod
    async def create(self, repo_id: int, commit_sha: str, ontology_version_id: int | None) -> dict[str, Any]:
        """
        #Feature: Snapshots
        #Scenario: Allocate the next seq for a repo
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def get(self, snapshot_id: int) -> dict[str, Any]:
        """
        #Feature: Snapshots
        #Scenario: Fetch one snapshot; missing raises Errors.HTTP.NotFound
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def list_page(self, repo_id: int, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """
        #Feature: Snapshots
        #Scenario: Page of a repo's snapshots, newest first
        #Complexity: Time O(l) - linear in page size
        """

    @abstractmethod
    async def latest_ready(self, repo_id: int, before_seq: int | None) -> dict[str, Any] | None:
        """
        #Feature: Snapshots
        #Scenario: Latest ready snapshot, optionally strictly before a seq
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def set_status(
        self, snapshot_id: int, status: str, stats: dict | None, extractor_versions: dict | None, error: str | None
    ) -> None:
        """
        #Feature: Snapshots
        #Scenario: Transition status and merge stats
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def stats(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Snapshots
        #Scenario: Node, edge and hole counts per type at seq
        #Complexity: Time O(n + e) - database aggregate
        """

    @abstractmethod
    async def coverage_holes(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Coverage map
        #Scenario: All coverage holes at seq
        #Complexity: Time O(h) - linear in holes
        """

    @abstractmethod
    async def validate(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Graph validation
        #Scenario: Run the CI validation query at seq
        #Complexity: Time O(e) - database scan of edges
        """
