import json
import uuid
from typing import Any

from tracegraph.interfaces.repositories.answers import IAnswerRepository
from tracegraph.repositories.base import UdfRepository

_INSERT = (
    "SELECT tg_answer_insert(:handle, :repo_id, :seq, :overlay_id, :query_hash, CAST(:query_ir AS jsonb), :truth, "
    "CAST(:result AS jsonb), CAST(:derivation AS jsonb), CAST(:min_tier AS tier), :latency_ms)"
)
_GET = "SELECT * FROM tg_answer_get(:handle)"


class AnswerRepository(UdfRepository, IAnswerRepository):
    """
    #Feature: Reasoning audit
    #Scenario: Answer store via tg_answer_insert / tg_answer_get
    #Complexity: Time O(1) per call excluding database work
    """

    async def insert(self, answer: dict[str, Any], query_ir: dict[str, Any], min_tier: str) -> str:
        """
        #Feature: Reasoning audit
        #Scenario: Persist the full answer JSON under a fresh handle
        #Complexity: Time O(s) - answer size

        Raises:
            ValueError: When answer or query_ir is missing.
        """
        if answer is None or query_ir is None or not min_tier:
            raise ValueError("[AnswerRepository.insert] 'answer', 'query_ir' and 'min_tier' are required.")
        handle = f"ans_{uuid.uuid4().hex}"
        stored = {**answer, "handle": handle}
        await self._execute(_INSERT, {
            "handle": handle, "repo_id": answer["snapshot"]["repo"], "seq": answer["snapshot"]["seq"],
            "overlay_id": answer.get("overlay"), "query_hash": answer["query_hash"], "query_ir": json.dumps(query_ir),
            "truth": answer["truth"], "result": json.dumps(stored), "derivation": json.dumps(answer["derivations"]),
            "min_tier": min_tier, "latency_ms": answer["latency_ms"]})
        return handle

    async def get(self, handle: str) -> dict[str, Any]:
        """
        #Feature: Reasoning audit
        #Scenario: Fetch a stored answer
        #Complexity: Time O(1) - unique index lookup
        """
        if not handle:
            raise ValueError("[AnswerRepository.get] 'handle' is required.")
        return await self._fetch_one(_GET, {"handle": handle})
