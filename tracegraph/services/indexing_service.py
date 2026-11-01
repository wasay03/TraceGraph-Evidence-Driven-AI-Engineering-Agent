import asyncio
import logging
from pathlib import Path
from typing import Any

from tracegraph.constants.extract import EXTRACTOR_VERSIONS
from tracegraph.constants.graph import (
    JOB_FAILED,
    JOB_KIND_INCREMENTAL,
    JOB_SUCCEEDED,
    SNAPSHOT_FAILED,
    SNAPSHOT_INDEXING,
    SNAPSHOT_READY,
)
from tracegraph.extract import (
    ExtractionResult,
    GraphPayload,
    ModuleFingerprint,
    dirty_scope,
    filter_payload,
    run_extraction,
)
from tracegraph.interfaces.repositories.graph import IGraphRepository
from tracegraph.interfaces.repositories.jobs import IIndexJobRepository
from tracegraph.interfaces.repositories.repos import IRepoRepository
from tracegraph.interfaces.repositories.snapshots import ISnapshotRepository
from tracegraph.interfaces.services.indexing import IIndexingService
from tracegraph.interfaces.workspace import IWorkspace
from tracegraph.ontology import Registry
from tracegraph.schemas.snapshots import SnapshotResponse

logger = logging.getLogger(__name__)


class IndexingService(IIndexingService):
    """
    #Feature: Indexing (PRD 5.1 steps 1-9, 5.4)
    #Scenario: Turn a claimed job into a committed, validated snapshot; full or incremental
    #Complexity: Time O(N * r) - dominated by extraction
    """

    def __init__(
        self,
        graph_repository: IGraphRepository,
        snapshot_repository: ISnapshotRepository,
        job_repository: IIndexJobRepository,
        repo_repository: IRepoRepository,
        workspace: IWorkspace,
        registry: Registry,
    ) -> None:
        """
        #Feature: Indexing
        #Scenario: Constructor injection
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a dependency is None.
        """
        deps = (graph_repository, snapshot_repository, job_repository, repo_repository, workspace, registry)
        if any(d is None for d in deps):
            raise ValueError("[IndexingService.__init__] All dependencies are required.")
        self._graph, self._snapshots, self._jobs, self._repos, self._workspace, self._registry = deps

    def _extract(self, path: Path, repo: dict[str, Any], commit: str) -> ExtractionResult:
        """
        #Feature: Indexing
        #Scenario: Materialise the commit and run the pipeline (CPU-bound; called in a worker thread)
        #Complexity: Time O(N * r) - extraction cost
        """
        with self._workspace.checkout(path, commit) as root:
            return run_extraction(self._registry, root, repo["id"], repo["url"], commit)

    async def _scope(self, job: dict[str, Any], snapshot: dict[str, Any],
                     result: ExtractionResult) -> tuple[list[str] | None, int | None]:
        """
        #Feature: Incremental indexing
        #Scenario: Dirty scope against the latest ready snapshot; full scope when none exists
        #Complexity: Time O(f) - linear in module files
        """
        if job["kind"] != JOB_KIND_INCREMENTAL:
            return None, None
        base = await self._snapshots.latest_ready(snapshot["repo_id"], snapshot["seq"])
        if base is None:
            return None, None
        rows = await self._graph.nodes_by_type(snapshot["repo_id"], base["seq"],
                                               [self._registry.node_type("Module").id])
        previous = {r["file_path"]: ModuleFingerprint(r["props"].get("content_hash", ""),
                                                      r["props"].get("signature_hash", "")) for r in rows}
        return dirty_scope(previous, result.modules, result.importers), base["seq"]

    async def _commit(self, repo_id: int, seq: int, payload: GraphPayload, scope: list[str] | None,
                      prev_seq: int | None) -> dict[str, Any]:
        """
        #Feature: Indexing (PRD 5.1 step 9)
        #Scenario: Write nodes, edges, evidence and holes in the job's transaction
        #Complexity: Time O(n + e + v + h) - database writes
        """
        nodes = await self._graph.commit_nodes(repo_id, seq, payload.nodes, scope)
        edges = await self._graph.commit_edges(repo_id, seq, payload.edges, scope)
        evidence = await self._graph.commit_evidence(repo_id, payload.evidence, payload.links, scope)
        holes = await self._graph.commit_holes(repo_id, seq, payload.holes, scope, prev_seq)
        return {"nodes_written": nodes, "edges_written": edges, "evidence_written": evidence,
                "coverage_holes_total": holes}

    async def claim(self, worker_id: str) -> dict[str, Any] | None:
        """
        #Feature: Indexing
        #Scenario: Claim with SKIP LOCKED; the snapshot becomes visible as indexing when this commits
        #Complexity: Time O(log q) - queue index lookup
        """
        if not worker_id:
            raise ValueError("[IndexingService.claim] 'worker_id' is required.")
        job = await self._jobs.claim(worker_id)
        if job is not None:
            await self._snapshots.set_status(job["snapshot_id"], SNAPSHOT_INDEXING, None, None, None)
        return job

    async def run(self, job: dict[str, Any]) -> SnapshotResponse:
        """
        #Feature: Indexing
        #Scenario: Extract -> scope -> commit -> mark ready; any error propagates so the caller rolls back
        #Complexity: Time O(N * r) - extraction cost

        Raises:
            Errors.Domain.*: When extraction violates the registry.
            Errors.HTTP.BadRequest: When the repository or commit cannot be materialised.
        """
        if job is None:
            raise ValueError("[IndexingService.run] 'job' is required.")
        snapshot = await self._snapshots.get(job["snapshot_id"])
        repo = await self._repos.get(snapshot["repo_id"])
        path = self._workspace.local_path(repo["url"])
        result = await asyncio.to_thread(self._extract, path, repo, snapshot["commit_sha"])
        scope, prev_seq = await self._scope(job, snapshot, result)
        payload = filter_payload(result.payload, scope) if scope is not None else result.payload
        written = await self._commit(repo["id"], snapshot["seq"], payload, scope, prev_seq)
        stats = {**payload.stats, **written, "timings_ms": result.timings_ms, "base_seq": prev_seq}
        await self._snapshots.set_status(snapshot["id"], SNAPSHOT_READY, stats, EXTRACTOR_VERSIONS, None)
        await self._jobs.finish(job["id"], JOB_SUCCEEDED, None)
        logger.info("Snapshot ready", extra={"repo_id": repo["id"], "snapshot_seq": snapshot["seq"],
                                             "job_id": job["id"], "scope_files": len(scope) if scope else None})
        return SnapshotResponse(**await self._snapshots.get(snapshot["id"]))

    async def fail(self, job: dict[str, Any], error: str) -> None:
        """
        #Feature: Indexing
        #Scenario: Record the failure on snapshot and job
        #Complexity: Time O(1) - constant
        """
        if job is None:
            raise ValueError("[IndexingService.fail] 'job' is required.")
        await self._snapshots.set_status(job["snapshot_id"], SNAPSHOT_FAILED, None, None, error[:4000])
        await self._jobs.finish(job["id"], JOB_FAILED, error[:4000])
