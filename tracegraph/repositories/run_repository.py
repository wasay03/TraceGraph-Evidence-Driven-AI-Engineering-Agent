import json
from typing import Any

from tracegraph.interfaces.repositories.runs import IRunRepository
from tracegraph.repositories.base import UdfRepository

_CREATE = "SELECT * FROM tg_run_create(:repo_id, :snapshot_id, :mode, :config, :request)"
_GET = "SELECT * FROM tg_run_get(:id)"
_LIST = "SELECT * FROM tg_run_list(:repo_id, :limit, :offset)"
_SAVE = "SELECT tg_run_save(:id, :version, :status, :phase, CAST(:state AS jsonb))"
_APPEND = "SELECT tg_run_event_append(:id, :kind, :phase, CAST(:payload AS jsonb))"
_EVENTS = "SELECT * FROM tg_run_event_list(:id, :after, :limit)"


class RunRepository(UdfRepository, IRunRepository):
    """
    #Feature: Agent runs
    #Scenario: Run state and audit log via tg_run_* functions
    #Complexity: Time O(1) per call excluding database work
    """

    async def create(self, repo_id: int, snapshot_id: int, mode: str, config: str, request: str) -> dict[str, Any]:
        """
        #Feature: Agent runs
        #Scenario: Insert a queued run
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a required argument is missing.
        """
        if repo_id is None or snapshot_id is None or not mode or not config or not request:
            raise ValueError("[RunRepository.create] all arguments are required.")
        params = {"repo_id": repo_id, "snapshot_id": snapshot_id, "mode": mode, "config": config, "request": request}
        return await self._fetch_one(_CREATE, params)

    async def get(self, run_id: int) -> dict[str, Any]:
        """
        #Feature: Agent runs
        #Scenario: Fetch one run
        #Complexity: Time O(1) - constant
        """
        if run_id is None:
            raise ValueError("[RunRepository.get] 'run_id' is required.")
        return await self._fetch_one(_GET, {"id": run_id})

    async def list_page(self, repo_id: int | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """
        #Feature: Agent runs
        #Scenario: Page of runs with total from the window count
        #Complexity: Time O(l) - page size
        """
        rows = await self._fetch_all(_LIST, {"repo_id": repo_id, "limit": limit, "offset": offset})
        total = rows[0]["total"] if rows else 0
        return [{k: v for k, v in row.items() if k != "total"} for row in rows], total

    async def save(self, run_id: int, expected_version: int, status: str, phase: str, state: dict[str, Any]) -> int:
        """
        #Feature: Agent runs
        #Scenario: Versioned transition
        #Complexity: Time O(s) - state size
        """
        if run_id is None or expected_version is None or not status or not phase or state is None:
            raise ValueError("[RunRepository.save] all arguments are required.")
        params = {"id": run_id, "version": expected_version, "status": status, "phase": phase,
                  "state": json.dumps(state, default=str)}
        return await self._fetch_scalar(_SAVE, params)

    async def append_event(self, run_id: int, kind: str, phase: str, payload: dict[str, Any]) -> int:
        """
        #Feature: Agent runs
        #Scenario: Append an audit event
        #Complexity: Time O(1) - constant
        """
        if run_id is None or not kind or not phase:
            raise ValueError("[RunRepository.append_event] 'run_id', 'kind' and 'phase' are required.")
        params = {"id": run_id, "kind": kind, "phase": phase, "payload": json.dumps(payload or {}, default=str)}
        return await self._fetch_scalar(_APPEND, params)

    async def events(self, run_id: int, after_seq: int, limit: int) -> list[dict[str, Any]]:
        """
        #Feature: Agent runs
        #Scenario: Page of audit events
        #Complexity: Time O(l) - page size
        """
        if run_id is None:
            raise ValueError("[RunRepository.events] 'run_id' is required.")
        return await self._fetch_all(_EVENTS, {"id": run_id, "after": after_seq, "limit": limit})
