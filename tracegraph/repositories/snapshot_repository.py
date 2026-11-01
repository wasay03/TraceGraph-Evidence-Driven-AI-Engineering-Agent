import json
from typing import Any

from tracegraph.interfaces.repositories.snapshots import ISnapshotRepository
from tracegraph.repositories.base import UdfRepository

_CREATE = "SELECT * FROM tg_snapshot_create(:repo_id, :commit_sha, :ontology_version_id)"
_GET = "SELECT * FROM tg_snapshot_get(:id)"
_LIST = "SELECT * FROM tg_snapshot_list(:repo_id, :limit, :offset)"
_LATEST_READY = "SELECT * FROM tg_snapshot_latest_ready(:repo_id, :before_seq)"
_SET_STATUS = (
    "SELECT tg_snapshot_set_status(:id, CAST(:status AS snapshot_status), CAST(:stats AS jsonb), "
    "CAST(:versions AS jsonb), :error)"
)
_STATS = "SELECT * FROM tg_graph_stats(:repo_id, :seq)"
_HOLES = "SELECT * FROM tg_coverage_hole_list(:repo_id, :seq)"
_VALIDATE = "SELECT * FROM tg_graph_validate(:repo_id, :seq)"


def _json_or_none(value: dict | None) -> str | None:
    """
    #Feature: Persistence
    #Scenario: Serialise an optional dict for a jsonb parameter
    #Complexity: Time O(n) - linear in dict size
    """
    return json.dumps(value) if value is not None else None


class SnapshotRepository(UdfRepository, ISnapshotRepository):
    """
    #Feature: Snapshots
    #Scenario: Snapshot lifecycle and graph summaries via tg_snapshot_* and tg_graph_* functions
    #Complexity: Time O(1) - constant per call excluding database work
    """

    async def create(self, repo_id: int, commit_sha: str, ontology_version_id: int | None) -> dict[str, Any]:
        """
        #Feature: Snapshots
        #Scenario: Allocate the next seq for a repo
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When repo_id or commit_sha is missing.
        """
        if repo_id is None or not commit_sha:
            raise ValueError("[SnapshotRepository.create] 'repo_id' and 'commit_sha' are required.")
        params = {"repo_id": repo_id, "commit_sha": commit_sha, "ontology_version_id": ontology_version_id}
        return await self._fetch_one(_CREATE, params)

    async def get(self, snapshot_id: int) -> dict[str, Any]:
        """
        #Feature: Snapshots
        #Scenario: Fetch one snapshot (TG404 when missing)
        #Complexity: Time O(1) - constant
        """
        if snapshot_id is None:
            raise ValueError("[SnapshotRepository.get] 'snapshot_id' is required.")
        return await self._fetch_one(_GET, {"id": snapshot_id})

    async def list_page(self, repo_id: int, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """
        #Feature: Snapshots
        #Scenario: Page of a repo's snapshots
        #Complexity: Time O(l) - linear in page size
        """
        rows = await self._fetch_all(_LIST, {"repo_id": repo_id, "limit": limit, "offset": offset})
        total = rows[0]["total"] if rows else 0
        return [{k: v for k, v in row.items() if k != "total"} for row in rows], total

    async def latest_ready(self, repo_id: int, before_seq: int | None) -> dict[str, Any] | None:
        """
        #Feature: Snapshots
        #Scenario: Latest ready snapshot, optionally before a seq
        #Complexity: Time O(1) - constant
        """
        return await self._fetch_one(_LATEST_READY, {"repo_id": repo_id, "before_seq": before_seq})

    async def set_status(
        self, snapshot_id: int, status: str, stats: dict | None, extractor_versions: dict | None, error: str | None
    ) -> None:
        """
        #Feature: Snapshots
        #Scenario: Transition status and merge stats
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When snapshot_id or status is missing.
        """
        if snapshot_id is None or not status:
            raise ValueError("[SnapshotRepository.set_status] 'snapshot_id' and 'status' are required.")
        await self._execute(_SET_STATUS, {"id": snapshot_id, "status": status, "stats": _json_or_none(stats),
                                          "versions": _json_or_none(extractor_versions), "error": error})

    async def stats(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Snapshots
        #Scenario: Counts per type at seq
        #Complexity: Time O(n + e) - database aggregate
        """
        return await self._fetch_all(_STATS, {"repo_id": repo_id, "seq": seq})

    async def coverage_holes(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Coverage map
        #Scenario: All holes at seq
        #Complexity: Time O(h) - linear in holes
        """
        return await self._fetch_all(_HOLES, {"repo_id": repo_id, "seq": seq})

    async def validate(self, repo_id: int, seq: int) -> list[dict[str, Any]]:
        """
        #Feature: Graph validation
        #Scenario: CI validation query at seq
        #Complexity: Time O(e) - database scan of edges
        """
        return await self._fetch_all(_VALIDATE, {"repo_id": repo_id, "seq": seq})
