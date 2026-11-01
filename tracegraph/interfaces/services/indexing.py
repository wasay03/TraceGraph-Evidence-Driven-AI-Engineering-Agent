from abc import ABC, abstractmethod
from typing import Any

from tracegraph.schemas.snapshots import SnapshotResponse


class IIndexingService(ABC):
    """
    #Feature: Indexing
    #Scenario: Contract for executing one claimed index job
    #Complexity: Time O(1) per call excluding extraction
    """

    @abstractmethod
    async def claim(self, worker_id: str) -> dict[str, Any] | None:
        """
        #Feature: Indexing
        #Scenario: Claim the next queued job and mark its snapshot indexing; None when the queue is empty
        #Complexity: Time O(log q) - queue index lookup
        """

    @abstractmethod
    async def run(self, job: dict[str, Any]) -> SnapshotResponse:
        """
        #Feature: Indexing
        #Scenario: Extract, validate and commit the snapshot; mark it ready and the job succeeded
        #Complexity: Time O(N * r) - extraction cost
        """

    @abstractmethod
    async def fail(self, job: dict[str, Any], error: str) -> None:
        """
        #Feature: Indexing
        #Scenario: Mark snapshot and job failed after a rolled-back run
        #Complexity: Time O(1) - constant
        """
