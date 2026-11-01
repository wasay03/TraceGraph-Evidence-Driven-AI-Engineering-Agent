from abc import ABC, abstractmethod

from tracegraph.schemas.common import Page
from tracegraph.schemas.snapshots import (
    SnapshotCreateRequest,
    SnapshotDetailResponse,
    SnapshotJobResponse,
    SnapshotResponse,
    SourceResponse,
    ValidationResponse,
)


class ISnapshotService(ABC):
    """
    #Feature: Snapshots
    #Scenario: Contract for requesting indexing runs and reading snapshot state
    #Complexity: Time O(1) - constant per call excluding database work
    """

    @abstractmethod
    async def request_index(self, repo_id: int, request: SnapshotCreateRequest) -> SnapshotJobResponse:
        """
        #Feature: Snapshots
        #Scenario: Create a pending snapshot for a resolved commit and queue its indexing job
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def get(self, snapshot_id: int) -> SnapshotDetailResponse:
        """
        #Feature: Snapshots
        #Scenario: Snapshot with counts and coverage holes
        #Complexity: Time O(n + e) - database aggregate
        """

    @abstractmethod
    async def list_page(self, repo_id: int, page: int, limit: int) -> Page[SnapshotResponse]:
        """
        #Feature: Snapshots
        #Scenario: Paged snapshots of a repository
        #Complexity: Time O(l) - linear in page size
        """

    @abstractmethod
    async def source(self, snapshot_id: int, path: str, start: int, end: int | None) -> SourceResponse:
        """
        #Feature: Provenance
        #Scenario: File lines at the snapshot's commit
        #Complexity: Time O(s) - file size
        """

    @abstractmethod
    async def validate(self, snapshot_id: int) -> ValidationResponse:
        """
        #Feature: Graph validation
        #Scenario: Run the CI validation query on one snapshot
        #Complexity: Time O(e) - database scan of edges
        """
