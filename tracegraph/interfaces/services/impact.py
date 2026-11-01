from abc import ABC, abstractmethod

from tracegraph.schemas.impact import ImpactReport, ImpactRequest, InvariantCheckRequest, InvariantCheckResponse


class IImpactService(ABC):
    """
    #Feature: Impact analysis service
    #Scenario: Contract for what-if impact reports and invariant checks
    #Complexity: Time per analysis
    """

    @abstractmethod
    async def analyze(self, request: ImpactRequest) -> ImpactReport:
        """
        #Feature: Impact analysis service
        #Scenario: ChangeSpecs -> persisted overlay + impact report with a handle
        #Complexity: Time per analysis
        """

    @abstractmethod
    async def get_report(self, handle: str) -> ImpactReport:
        """
        #Feature: Impact analysis service
        #Scenario: Stored report by handle
        #Complexity: Time O(1) - unique index lookup
        """

    @abstractmethod
    async def check_invariants(self, request: InvariantCheckRequest) -> InvariantCheckResponse:
        """
        #Feature: Impact analysis service
        #Scenario: Run invariant packs on a snapshot
        #Complexity: Time cost of the selected invariants
        """
