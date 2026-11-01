import json
from typing import Any

from tracegraph.interfaces.repositories.jobs import IIndexJobRepository
from tracegraph.repositories.base import UdfRepository

_ENQUEUE = (
    "SELECT * FROM tg_index_job_enqueue(:repo_id, :snapshot_id, CAST(:kind AS job_kind), CAST(:payload AS jsonb))"
)
_CLAIM = "SELECT * FROM tg_index_job_claim(:worker)"
_FINISH = "SELECT tg_index_job_finish(:id, CAST(:status AS job_status), :error)"
_GET = "SELECT * FROM tg_index_job_get(:id)"


class IndexJobRepository(UdfRepository, IIndexJobRepository):
    """
    #Feature: Background indexing
    #Scenario: Job queue via tg_index_job_* functions
    #Complexity: Time O(1) - constant per call excluding database work
    """

    async def enqueue(self, repo_id: int, snapshot_id: int, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        #Feature: Background indexing
        #Scenario: Queue a job
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a required argument is missing.
        """
        if repo_id is None or snapshot_id is None or not kind:
            raise ValueError("[IndexJobRepository.enqueue] 'repo_id', 'snapshot_id' and 'kind' are required.")
        params = {"repo_id": repo_id, "snapshot_id": snapshot_id, "kind": kind, "payload": json.dumps(payload or {})}
        return await self._fetch_one(_ENQUEUE, params)

    async def claim(self, worker_id: str) -> dict[str, Any] | None:
        """
        #Feature: Background indexing
        #Scenario: Claim the oldest queued job
        #Complexity: Time O(log q) - index lookup
        """
        if not worker_id:
            raise ValueError("[IndexJobRepository.claim] 'worker_id' is required.")
        return await self._fetch_one(_CLAIM, {"worker": worker_id})

    async def finish(self, job_id: int, status: str, error: str | None) -> None:
        """
        #Feature: Background indexing
        #Scenario: Mark a job finished
        #Complexity: Time O(1) - constant
        """
        if job_id is None or not status:
            raise ValueError("[IndexJobRepository.finish] 'job_id' and 'status' are required.")
        await self._execute(_FINISH, {"id": job_id, "status": status, "error": error})

    async def get(self, job_id: int) -> dict[str, Any]:
        """
        #Feature: Background indexing
        #Scenario: Fetch one job
        #Complexity: Time O(1) - constant
        """
        if job_id is None:
            raise ValueError("[IndexJobRepository.get] 'job_id' is required.")
        return await self._fetch_one(_GET, {"id": job_id})
