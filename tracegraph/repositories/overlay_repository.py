import json
from typing import Any

from tracegraph.interfaces.repositories.overlays import IOverlayRepository
from tracegraph.repositories.base import UdfRepository

_CREATE = "SELECT tg_overlay_create(:repo_id, :base_seq, CAST(:change_spec AS jsonb), CAST(:ops AS jsonb))"
_GET = "SELECT * FROM tg_overlay_get(:id)"


class OverlayRepository(UdfRepository, IOverlayRepository):
    """
    #Feature: What-if overlays
    #Scenario: Overlay store via tg_overlay_create / tg_overlay_get
    #Complexity: Time O(1) per call excluding database work
    """

    async def create(self, repo_id: int, base_seq: int, change_spec: dict[str, Any], ops: list[dict[str, Any]]) -> int:
        """
        #Feature: What-if overlays
        #Scenario: Persist an overlay
        #Complexity: Time O(o) - linear in ops

        Raises:
            ValueError: When a required argument is missing.
        """
        if repo_id is None or base_seq is None or change_spec is None or ops is None:
            raise ValueError("[OverlayRepository.create] 'repo_id', 'base_seq', 'change_spec' and 'ops' are required.")
        params = {"repo_id": repo_id, "base_seq": base_seq, "change_spec": json.dumps(change_spec),
                  "ops": json.dumps(ops)}
        return await self._fetch_scalar(_CREATE, params)

    async def get(self, overlay_id: int) -> dict[str, Any]:
        """
        #Feature: What-if overlays
        #Scenario: Fetch an overlay with its ops
        #Complexity: Time O(o) - linear in ops
        """
        if overlay_id is None:
            raise ValueError("[OverlayRepository.get] 'overlay_id' is required.")
        return await self._fetch_one(_GET, {"id": overlay_id})
