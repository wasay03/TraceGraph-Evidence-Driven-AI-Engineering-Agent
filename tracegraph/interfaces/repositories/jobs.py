from abc import ABC, abstractmethod
from typing import Any


class IIndexJobRepository(ABC):
    """
    #Feature: Background indexing
    #Scenario: Contract for the Postgres-backed job queue
    #Complexity: Time O(1) - constant per call
    """

    @abstractmethod
    async def enqueue(self, repo_id: int, snapshot_id: int, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        #Feature: Background indexing
        #Scenario: Queue an indexing job
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def claim(self, worker_id: str) -> dict[str, Any] | None:
        """
        #Feature: Background indexing
        #Scenario: Claim the oldest queued job with SKIP LOCKED, or None
        #Complexity: Time O(log q) - index lookup
        """

    @abstractmethod
    async def finish(self, job_id: int, status: str, error: str | None) -> None:
        """
        #Feature: Background indexing
        #Scenario: Mark a job succeeded or failed
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def get(self, job_id: int) -> dict[str, Any]:
        """
        #Feature: Background indexing
        #Scenario: Fetch one job; missing raises Errors.HTTP.NotFound
        #Complexity: Time O(1) - constant
        """
