import logging
import time
from pathlib import Path
from typing import Any

from tracegraph.agent.artifacts import Plan
from tracegraph.agent.plan_rules import validate_plan
from tracegraph.constants import agent as a
from tracegraph.errors import Errors
from tracegraph.interfaces.repositories.runs import IRunRepository
from tracegraph.interfaces.repositories.snapshots import ISnapshotRepository
from tracegraph.interfaces.services.agent import IAgentService
from tracegraph.schemas.common import Page
from tracegraph.schemas.runs import (
    ApprovalRequest,
    ClarifyRequest,
    RunCreateRequest,
    RunEventOut,
    RunResponse,
    RunSummary,
)

logger = logging.getLogger(__name__)
EVENT_PAGE = 200


class AgentService(IAgentService):
    """
    #Feature: Agent runs service
    #Scenario: Run lifecycle over the run repository; execution itself lives in AgentExecutor
    #Complexity: Time O(1) per call
    """

    def __init__(self, run_repository: IRunRepository, snapshot_repository: ISnapshotRepository) -> None:
        """
        #Feature: Agent runs service
        #Scenario: Constructor injection
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a dependency is None.
        """
        if run_repository is None or snapshot_repository is None:
            raise ValueError("[AgentService.__init__] 'run_repository' and 'snapshot_repository' are required.")
        self._runs, self._snapshots = run_repository, snapshot_repository

    async def start(self, request: RunCreateRequest) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Pin the run to a ready snapshot of the repo
        #Complexity: Time O(1) - constant

        Raises:
            Errors.HTTP.BadRequest: When no ready snapshot exists for the repo.
        """
        snapshot = (await self._snapshots.get(request.snapshot_id) if request.snapshot_id
                    else await self._snapshots.latest_ready(request.repo_id, None))
        if snapshot is None or snapshot["repo_id"] != request.repo_id or snapshot["status"] != "ready":
            raise Errors.HTTP.BadRequest(f"Repository {request.repo_id} has no ready snapshot to run on.")
        row = await self._runs.create(request.repo_id, snapshot["id"], request.mode, request.config, request.request)
        logger.info("Run created", extra={"run_id": row["id"], "repo_id": request.repo_id, "config": request.config})
        return RunResponse(**row)

    async def get(self, run_id: int, events_after: int = 0) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Run plus a page of events
        #Complexity: Time O(l) - events page
        """
        row = await self._runs.get(run_id)
        events = await self._runs.events(run_id, events_after, EVENT_PAGE)
        return RunResponse(**row, events=[RunEventOut(**e) for e in events])

    async def list_page(self, repo_id: int | None, page: int, limit: int) -> Page[RunSummary]:
        """
        #Feature: Agent runs service
        #Scenario: Paged runs, newest first
        #Complexity: Time O(l) - page size
        """
        rows, total = await self._runs.list_page(repo_id, limit, (page - 1) * limit)
        return Page[RunSummary](items=[RunSummary(**r) for r in rows], total=total, page=page, limit=limit)

    async def _requeue(self, row: dict[str, Any], state: dict[str, Any], kind: str, payload: dict[str, Any]
                       ) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Persist a human decision and put the run back in the queue
        #Complexity: Time O(s) - state size
        """
        await self._runs.save(row["id"], row["version"], a.STATUS_QUEUED, row["phase"], state)
        await self._runs.append_event(row["id"], kind, row["phase"], payload)
        return await self.get(row["id"])

    async def approve(self, run_id: int, request: ApprovalRequest) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Only a run awaiting approval accepts a decision; an edited plan must still pass plan rules
        #Complexity: Time O(s) - state size

        Raises:
            Errors.HTTP.Conflict: When the run is not awaiting approval.
            Errors.HTTP.BadRequest: When an edited plan is invalid.
        """
        row = await self._runs.get(run_id)
        if row["status"] != a.STATUS_AWAITING_APPROVAL:
            raise Errors.HTTP.Conflict(f"Run {run_id} is {row['status']}, not awaiting approval.")
        state = dict(row["state"])
        if request.plan is not None:
            plan = Plan.model_validate(request.plan)
            impact = state.get("impact") if row["config"] in a.PLAN_RULES_CONFIGS else None
            problems = validate_plan(plan, impact, Path(state["worktree"]) if state.get("worktree") else None)
            if problems:
                raise Errors.HTTP.BadRequest("Edited plan is invalid.", {"violations": problems})
            state["artifacts"] = {**state.get("artifacts", {}), a.PHASE_PLAN: plan.model_dump(mode="json")}
        state["approval"] = {"approved": request.approved, "by": "user", "comment": request.comment,
                             "edited": request.plan is not None}
        return await self._requeue(row, state, "approval", state["approval"])

    async def clarify(self, run_id: int, request: ClarifyRequest) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Attach the user's answer as feedback for the next phase
        #Complexity: Time O(s) - state size

        Raises:
            Errors.HTTP.Conflict: When the run is not awaiting input.
        """
        row = await self._runs.get(run_id)
        if row["status"] != a.STATUS_AWAITING_USER:
            raise Errors.HTTP.Conflict(f"Run {run_id} is {row['status']}, not awaiting input.")
        state = {**row["state"], "feedback": f"User clarification: {request.answer}"}
        return await self._requeue(row, state, "approval", {"clarification": request.answer})

    async def retry(self, run_id: int, extra_llm_calls: int) -> RunResponse:
        """
        #Feature: Agent runs service
        #Scenario: Clear the error, optionally extend the LLM call cap, and requeue at the phase that failed
        #Complexity: Time O(s) - state size

        Raises:
            Errors.HTTP.Conflict: When the run did not fail or exhaust its budget.
        """
        row = await self._runs.get(run_id)
        if row["status"] not in a.RETRYABLE_STATUSES:
            raise Errors.HTTP.Conflict(f"Run {run_id} is {row['status']}, only failed or exhausted runs can be retried.")
        budget = dict(row["state"].get("budget") or {})
        budget["max_llm_calls"] = budget.get("max_llm_calls", a.MAX_LLM_CALLS) + extra_llm_calls
        budget["started_at"] = time.time()  # the wall-clock budget restarts; call and token counts carry over
        state = {**row["state"], "error": None, "budget": budget, "call_counts": {}}
        return await self._requeue(row, state, "approval", {"retry": True, "extra_llm_calls": extra_llm_calls})

    async def load(self, run_id: int) -> dict[str, Any]:
        """
        #Feature: Agent runs service
        #Scenario: Raw run row
        #Complexity: Time O(1) - constant
        """
        return await self._runs.get(run_id)

    async def save(self, run_id: int, version: int, status: str, phase: str, state: dict[str, Any]) -> int:
        """
        #Feature: Agent runs service
        #Scenario: Versioned transition
        #Complexity: Time O(s) - state size
        """
        return await self._runs.save(run_id, version, status, phase, state)

    async def event(self, run_id: int, kind: str, phase: str, payload: dict[str, Any]) -> None:
        """
        #Feature: Agent runs service
        #Scenario: Audit event
        #Complexity: Time O(1) - constant
        """
        await self._runs.append_event(run_id, kind, phase, payload)
