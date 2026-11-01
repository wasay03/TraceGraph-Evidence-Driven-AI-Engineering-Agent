import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from tracegraph.agent.artifacts import Analysis, Intake, PatchSet, Plan, Report
from tracegraph.agent.claim_checker import check_claims
from tracegraph.agent.context_compiler import compile_context, repo_layout, scope_sources
from tracegraph.agent.partial_report import partial_report
from tracegraph.agent.phase_runner import PhaseRunner, ServicesFactory
from tracegraph.agent.plan_rules import validate_plan
from tracegraph.agent.state import RunState
from tracegraph.agent.verification import run_ladder
from tracegraph.constants import agent as a
from tracegraph.constants.agent_prompts import REANALYZE_FEEDBACK, VERIFY_FEEDBACK
from tracegraph.engine.graph import GraphSnapshot
from tracegraph.errors import AppError, Errors
from tracegraph.sandbox.run_sandbox import SandboxWorkspace
from tracegraph.tools.registry import ToolContext

logger = logging.getLogger(__name__)


class RunStore(Protocol):
    """
    #Feature: Agent state machine
    #Scenario: Persistence port: versioned transitions and audit events, each in its own transaction
    #Complexity: Time O(1) per call
    """

    async def save(self, status: str, phase: str, state: RunState) -> None: ...

    async def event(self, kind: str, phase: str, payload: dict[str, Any]) -> None: ...


@dataclass(slots=True)
class RunEnvironment:
    """
    #Feature: Agent state machine
    #Scenario: Immutable inputs of a run: identity, mode, ablation config, request, snapshot and repository
    #Complexity: Time O(1) - constant
    """

    run_id: int
    mode: str
    config: str
    request: str
    graph: GraphSnapshot
    repo_url: str
    sandbox: SandboxWorkspace


class AgentRunner:
    """
    #Feature: Agent state machine (PRD 10)
    #Scenario: Intake -> Discover -> Analyze -> Plan -> Approval -> Implement -> Verify -> Report with persisted
               transitions; questions skip Plan..Verify; Verify loops to Implement or back to Analyze
    #Complexity: Time O(phases * steps * tool cost)
    """

    def __init__(self, env: RunEnvironment, phases: PhaseRunner, services: ServicesFactory, store: RunStore) -> None:
        """
        #Feature: Agent state machine
        #Scenario: Constructor injection
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a dependency is None.
        """
        if env is None or phases is None or services is None or store is None:
            raise ValueError("[AgentRunner.__init__] 'env', 'phases', 'services' and 'store' are required.")
        self.env, self._phases, self._services, self._store = env, phases, services, store

    def _context(self, phase: str, state: RunState) -> ToolContext:
        """
        #Feature: Agent state machine
        #Scenario: Tool context for a phase; the scope set comes from the approved plan
        #Complexity: Time O(1) - constant
        """
        plan = state.artifacts.get(a.PHASE_PLAN)
        scope = frozenset(plan["scope_files"]) if plan and state.approval and state.approval.get("approved") else frozenset()
        return ToolContext(self.env.run_id, phase, self.env.config, state, self.env.graph, None,
                           self.env.sandbox.repo_path, self.env.sandbox, scope)

    async def _truth_of(self, handle: str) -> str | None:
        """
        #Feature: Claim binding
        #Scenario: Stored truth of an impact report or answer handle; each lookup in its own transaction because a
                   missing handle aborts the transaction it was looked up in
        #Complexity: Time O(1) - two lookups at most
        """
        try:
            async with self._services() as services:
                return (await services.impact.get_report(handle)).truth
        except Errors.HTTP.NotFound:
            pass
        try:
            async with self._services() as services:
                return (await services.query.get_answer(handle)).truth
        except AppError:
            return None

    def _check_for(self, phase: str, state: RunState):
        """
        #Feature: Agent state machine
        #Scenario: Code-level artifact checks per phase (plan rules, claim binding, simulation and patch presence)
        #Complexity: Time O(1) - builds a closure
        """
        async def check(artifact: Any) -> list[str]:
            if isinstance(artifact, Plan):
                use_rules = self.env.config in a.PLAN_RULES_CONFIGS
                return validate_plan(artifact, state.impact if use_rules else None, self.env.sandbox.root)
            if isinstance(artifact, Analysis) and self.env.config in a.PLAN_RULES_CONFIGS and self._is_change(state):
                ok = state.impact and artifact.impact_handle == state.impact["handle"]
                return [] if ok else ["call simulate_change and cite its report handle as impact_handle"]
            if isinstance(artifact, PatchSet):
                applied = {p["patch_id"] for p in state.patches}
                missing = [p for p in artifact.patch_ids if p not in applied]
                return [f"patches {missing} were not applied in this run"] if missing or not applied else []
            if isinstance(artifact, Report):
                return await check_claims(artifact, state.handles, self._truth_of)
            return []

        return check

    @staticmethod
    def _is_change(state: RunState) -> bool:
        """
        #Feature: Agent state machine
        #Scenario: Whether intake classified the request as a change
        #Complexity: Time O(1) - constant
        """
        return state.artifacts.get(a.PHASE_INTAKE, {}).get("kind") == "change"

    def _repo_context(self, phase: str, state: RunState) -> str:
        """
        #Feature: Context compilation
        #Scenario: Facts that stop the model hunting: file layout and migration head, plus the contents of the
                   approved scope files when implementing
        #Complexity: Time O(n + s) - nodes plus scope file size
        """
        if phase in (a.PHASE_INTAKE, a.PHASE_REPORT):
            return ""
        layout = repo_layout(self.env.graph)
        if phase != a.PHASE_IMPLEMENT:
            return layout
        return layout + scope_sources(self.env.sandbox.root, state.artifacts[a.PHASE_PLAN]["scope_files"])

    async def _seed_discovery(self, ctx: ToolContext, state: RunState) -> str:
        """
        #Feature: Context compilation (PRD 10.4)
        #Scenario: Run the standard lookups for each intake entity without a model turn; configs without graph
                   tools get nothing, so the baseline still has to explore by itself
        #Complexity: Time O(entities * tool cost)
        """
        entities = state.artifacts.get(a.PHASE_INTAKE, {}).get("entities", [])[:a.MAX_SEEDED_ENTITIES]
        lines = []
        for ref in entities if a.GROUP_STRUCTURAL in a.CONFIG_GROUPS[self.env.config] else []:
            for tool in a.SEEDED_DISCOVERY_TOOLS:
                outcome = await self._phases.call_tool(ctx, tool, {"ref": ref})
                if outcome.ok:
                    lines.append(f"[{tool} {ref}]\n{outcome.text}")
        return "\n## Lookups already run\n" + "\n".join(lines) + "\n" if lines else ""

    async def _llm_phase(self, phase: str, state: RunState) -> str:
        """
        #Feature: Agent state machine
        #Scenario: Run one LLM phase, store its artifact, return the next phase
        #Complexity: Time O(steps * tool cost)
        """
        ctx = self._context(phase, state)
        opening = compile_context(phase, self.env.request, state, self._repo_context(phase, state))
        if phase == a.PHASE_DISCOVER:
            opening += await self._seed_discovery(ctx, state)
        outcome = await self._phases.run(ctx, opening, self._check_for(phase, state))
        state.artifacts[phase] = outcome.artifact.model_dump(mode="json")
        state.feedback = None
        if phase == a.PHASE_ANALYZE:
            return a.PHASE_PLAN if self._is_change(state) else a.PHASE_REPORT
        order = {a.PHASE_INTAKE: a.PHASE_DISCOVER, a.PHASE_DISCOVER: a.PHASE_ANALYZE, a.PHASE_PLAN: a.PHASE_APPROVAL,
                 a.PHASE_IMPLEMENT: a.PHASE_VERIFY, a.PHASE_REPORT: a.PHASE_DONE}
        return order[phase]

    async def _verify(self, state: RunState) -> str:
        """
        #Feature: Agent state machine (PRD 10.3)
        #Scenario: Ladder; unplanned impact -> Analyze (re-approval), failures -> Implement (3 rounds), else Report
        #Complexity: Time O(test runtime + extraction)
        """
        plan = Plan.model_validate(state.artifacts[a.PHASE_PLAN])
        result = await asyncio.to_thread(run_ladder, self.env.sandbox, self.env.graph, self.env.repo_url, plan,
                                         state.impact, state.patches, self.env.mode)
        state.verification = result.to_dict()
        failures = [r for r in result.rungs if r["status"] == "failed"]
        if result.passed:
            return a.PHASE_REPORT
        if result.needs_reanalysis and state.reanalysis_rounds < a.MAX_REANALYSIS:
            state.reanalysis_rounds += 1
            state.approval = None
            state.feedback = REANALYZE_FEEDBACK.format(detail=failures)
            return a.PHASE_ANALYZE
        if state.correction_rounds < a.MAX_CORRECTION_ROUNDS:
            state.correction_rounds += 1
            state.feedback = VERIFY_FEEDBACK.format(detail=failures)
            return a.PHASE_IMPLEMENT
        return a.PHASE_REPORT

    async def _step(self, phase: str, state: RunState) -> tuple[str, str]:
        """
        #Feature: Agent state machine
        #Scenario: Execute the current phase; returns (status, next phase)
        #Complexity: Time per phase
        """
        if phase in a.LLM_PHASES:
            nxt = await self._llm_phase(phase, state)
            intake = state.artifacts.get(a.PHASE_INTAKE, {})
            if phase == a.PHASE_INTAKE and intake.get("ambiguities") and self.env.mode == a.MODE_INTERACTIVE:
                return a.STATUS_AWAITING_USER, nxt
            return (a.STATUS_COMPLETED if nxt == a.PHASE_DONE else a.STATUS_RUNNING), nxt
        if phase == a.PHASE_APPROVAL:
            if self.env.mode == a.MODE_BENCHMARK:
                state.approval = {"approved": True, "by": "auto"}
            if state.approval is None:
                return a.STATUS_AWAITING_APPROVAL, a.PHASE_APPROVAL
            return (a.STATUS_RUNNING, a.PHASE_IMPLEMENT) if state.approval["approved"] else (a.STATUS_REJECTED, a.PHASE_DONE)
        if phase == a.PHASE_VERIFY:
            return a.STATUS_RUNNING, await self._verify(state)
        return a.STATUS_COMPLETED, a.PHASE_DONE

    async def advance(self, phase: str, state: RunState) -> str:
        """
        #Feature: Agent state machine
        #Scenario: Run until the run completes, pauses for approval or input, or fails; every transition persisted
        #Complexity: Time O(phases * steps * tool cost)
        """
        status = a.STATUS_RUNNING
        while status == a.STATUS_RUNNING:
            try:
                status, nxt = await self._step(phase, state)
            except AppError as exc:
                state.error = exc.message
                status = a.STATUS_BUDGET_EXHAUSTED if exc.details.get("budget") else a.STATUS_FAILED
                nxt = phase
                if status == a.STATUS_BUDGET_EXHAUSTED:
                    state.partial_report = partial_report(phase, exc.message, state)
                await self._store.event("error", phase, {"error": exc.message, "code": exc.code})
            state.phase_history.append(phase)
            await self._store.event("transition", phase, {"to": nxt, "status": status})
            phase = nxt
            await self._store.save(status, phase, state)
            logger.info("Run transition", extra={"run_id": self.env.run_id, "phase": phase, "status": status})
        return status
