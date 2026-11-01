from abc import ABC, abstractmethod
from typing import Any

from tracegraph.schemas.runs import ApprovalRequest, ClarifyRequest, RunCreateRequest, RunResponse


class IAgentService(ABC):
    """
    #Feature: Agent runs service
    #Scenario: Contract for run lifecycle (create, read, approve, clarify) and the executor's persistence ports
    #Complexity: Time O(1) per call
    """

    @abstractmethod
    async def start(self, request: RunCreateRequest) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Validate repo and snapshot, create a queued run
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def get(self, run_id: int, events_after: int = 0) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Run with its recent audit events
        #Complexity: Time O(l) - events page
        """

    @abstractmethod
    async def approve(self, run_id: int, request: ApprovalRequest) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Human gate: approve, edit or reject a plan awaiting approval
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def clarify(self, run_id: int, request: ClarifyRequest) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Answer an ambiguity and requeue the run
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def retry(self, run_id: int, extra_llm_calls: int) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Requeue a failed or budget-exhausted run from its saved phase, without repeating finished phases
        #Complexity: Time O(s) - state size
        """

    @abstractmethod
    async def load(self, run_id: int) -> dict[str, Any]:
        """
        #Feature: Agent runs service
        #Scenario: Raw run row for the executor
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def save(self, run_id: int, version: int, status: str, phase: str, state: dict[str, Any]) -> int:
        """
        #Feature: Agent runs service
        #Scenario: Versioned transition for the executor; returns the new version
        #Complexity: Time O(s) - state size
        """

    @abstractmethod
    async def event(self, run_id: int, kind: str, phase: str, payload: dict[str, Any]) -> None:
        """
        #Feature: Agent runs service
        #Scenario: Audit event for the executor
        #Complexity: Time O(1) - constant
        """
