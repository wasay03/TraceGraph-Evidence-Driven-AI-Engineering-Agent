from abc import ABC, abstractmethod
from typing import Any


class IRunRepository(ABC):
    """
    #Feature: Agent runs
    #Scenario: Contract for versioned run state and the append-only audit log
    #Complexity: Time O(1) per call
    """

    @abstractmethod
    async def create(self, repo_id: int, snapshot_id: int, mode: str, config: str, request: str) -> dict[str, Any]:
        """
        #Feature: Agent runs
        #Scenario: Create a queued run
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def get(self, run_id: int) -> dict[str, Any]:
        """
        #Feature: Agent runs
        #Scenario: Fetch a run (TG404 when missing)
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def list_page(self, repo_id: int | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """
        #Feature: Agent runs
        #Scenario: Page of runs, newest first, optionally for one repository
        #Complexity: Time O(l) - page size
        """

    @abstractmethod
    async def save(self, run_id: int, expected_version: int, status: str, phase: str, state: dict[str, Any]) -> int:
        """
        #Feature: Agent runs
        #Scenario: Persist a transition with optimistic concurrency; returns the new version (TG409 on conflict)
        #Complexity: Time O(s) - state size
        """

    @abstractmethod
    async def append_event(self, run_id: int, kind: str, phase: str, payload: dict[str, Any]) -> int:
        """
        #Feature: Agent runs
        #Scenario: Append one audit event; returns its sequence number
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def events(self, run_id: int, after_seq: int, limit: int) -> list[dict[str, Any]]:
        """
        #Feature: Agent runs
        #Scenario: Audit events after a sequence number
        #Complexity: Time O(l) - page size
        """
