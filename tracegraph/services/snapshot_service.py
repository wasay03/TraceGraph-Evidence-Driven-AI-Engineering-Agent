import asyncio
import logging

from tracegraph.interfaces.repositories.jobs import IIndexJobRepository
from tracegraph.interfaces.repositories.repos import IRepoRepository
from tracegraph.interfaces.repositories.snapshots import ISnapshotRepository
from tracegraph.interfaces.services.ontology import IOntologyService
from tracegraph.interfaces.services.snapshots import ISnapshotService
from tracegraph.interfaces.workspace import IWorkspace
from tracegraph.sandbox.run_sandbox import read_at_commit
from tracegraph.schemas.common import Page
from tracegraph.schemas.snapshots import (
    CoverageHoleSchema,
    SnapshotCreateRequest,
    SnapshotDetailResponse,
    SnapshotJobResponse,
    SnapshotResponse,
    SourceResponse,
    TypeCount,
    ValidationResponse,
    ValidationViolation,
)

logger = logging.getLogger(__name__)


class SnapshotService(ISnapshotService):
    """
    #Feature: Snapshots
    #Scenario: Accept indexing requests and report snapshot state
    #Complexity: Time O(1) - constant per call excluding database work
    """

    def __init__(
        self,
        snapshot_repository: ISnapshotRepository,
        job_repository: IIndexJobRepository,
        repo_repository: IRepoRepository,
        ontology_service: IOntologyService,
        workspace: IWorkspace,
    ) -> None:
        """
        #Feature: Snapshots
        #Scenario: Constructor injection
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When an argument is None.
        """
        deps = (snapshot_repository, job_repository, repo_repository, ontology_service, workspace)
        if any(d is None for d in deps):
            raise ValueError("[SnapshotService.__init__] All dependencies are required.")
        self._snapshots, self._jobs, self._repos, self._ontology, self._workspace = deps

    async def request_index(self, repo_id: int, request: SnapshotCreateRequest) -> SnapshotJobResponse:
        """
        #Feature: Snapshots
        #Scenario: Resolve the ref now so the snapshot is pinned to an exact commit, then queue the job
        #Complexity: Time O(1) - constant

        Raises:
            Errors.HTTP.NotFound: When the repository is unknown.
            Errors.HTTP.BadRequest: When the ref cannot be resolved.
        """
        repo = await self._repos.get(repo_id)
        path = self._workspace.local_path(repo["url"])
        commit = await asyncio.to_thread(self._workspace.resolve_ref, path, request.ref)
        version_id = await self._ontology.ensure_catalog()
        snapshot = await self._snapshots.create(repo_id, commit, version_id)
        job = await self._jobs.enqueue(repo_id, snapshot["id"], request.kind, {"ref": request.ref})
        logger.info("Index job queued", extra={"repo_id": repo_id, "snapshot_seq": snapshot["seq"],
                                                "job_id": job["id"], "commit": commit})
        return SnapshotJobResponse(snapshot=SnapshotResponse(**snapshot), job_id=job["id"])

    async def get(self, snapshot_id: int) -> SnapshotDetailResponse:
        """
        #Feature: Snapshots
        #Scenario: Snapshot with per-type counts and coverage holes
        #Complexity: Time O(n + e) - database aggregate
        """
        snapshot = await self._snapshots.get(snapshot_id)
        counts = await self._snapshots.stats(snapshot["repo_id"], snapshot["seq"])
        holes = await self._snapshots.coverage_holes(snapshot["repo_id"], snapshot["seq"])
        return SnapshotDetailResponse(**snapshot, counts=[TypeCount(**c) for c in counts],
                                      coverage_holes=[CoverageHoleSchema(**h) for h in holes])

    async def list_page(self, repo_id: int, page: int, limit: int) -> Page[SnapshotResponse]:
        """
        #Feature: Snapshots
        #Scenario: Paged snapshots of a repository
        #Complexity: Time O(l) - linear in page size
        """
        await self._repos.get(repo_id)
        rows, total = await self._snapshots.list_page(repo_id, limit=limit, offset=(page - 1) * limit)
        return Page[SnapshotResponse](items=[SnapshotResponse(**r) for r in rows], total=total, page=page, limit=limit)

    async def source(self, snapshot_id: int, path: str, start: int, end: int | None) -> SourceResponse:
        """
        #Feature: Provenance
        #Scenario: Evidence expansion: file lines at the snapshot's commit, capped at 400 lines
        #Complexity: Time O(s) - file size

        Raises:
            Errors.HTTP.BadRequest: When the path escapes the repository.
            Errors.HTTP.NotFound: When the file is absent at that commit.
        """
        snapshot = await self._snapshots.get(snapshot_id)
        repo = await self._repos.get(snapshot["repo_id"])
        root = self._workspace.local_path(repo["url"])
        lines = await asyncio.to_thread(read_at_commit, root, snapshot["commit_sha"], path)
        stop = min(end or len(lines), len(lines), start + 399)
        return SourceResponse(path=path, start=start, end=stop, lines=lines[start - 1:stop])

    async def validate(self, snapshot_id: int) -> ValidationResponse:
        """
        #Feature: Graph validation
        #Scenario: CI validation query for one snapshot
        #Complexity: Time O(e) - database scan of edges
        """
        snapshot = await self._snapshots.get(snapshot_id)
        rows = await self._snapshots.validate(snapshot["repo_id"], snapshot["seq"])
        return ValidationResponse(snapshot_id=snapshot_id, valid=not rows,
                                  violations=[ValidationViolation(**r) for r in rows])
