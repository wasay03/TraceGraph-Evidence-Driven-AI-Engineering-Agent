import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from tracegraph.agent.artifacts import ARTIFACTS
from tracegraph.constants import agent as a
from tracegraph.constants.agent_prompts import BASE_SYSTEM, LAST_STEP, NUDGE_SUBMIT, PHASE_GOALS, STEPS_LEFT
from tracegraph.errors import Errors
from tracegraph.interfaces.llm import ILlmClient
from tracegraph.tools.registry import ToolCallResult, ToolContext, ToolRegistry, clean_schema

logger = logging.getLogger(__name__)

# Opens a transaction and yields a ServiceContainer bound to it (one per model step).
ServicesFactory = Callable[[], AbstractAsyncContextManager[Any]]
# Validates a submitted artifact beyond its schema; returns violations (empty means accepted).
ArtifactCheck = Callable[[Any], Awaitable[list[str]]]
EventSink = Callable[[str, str, dict[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class PhaseOutcome:
    """
    #Feature: Agent phases
    #Scenario: Accepted artifact of a phase plus the turn count
    #Complexity: Time O(1) - constant
    """

    artifact: Any
    turns: int


def submit_tool(phase: str) -> dict[str, Any]:
    """
    #Feature: Agent phases
    #Scenario: The phase's submit tool; its input schema is the exit artifact (PRD 10.1)
    #Complexity: Time O(s) - schema size
    """
    model = ARTIFACTS[phase]
    return {"name": a.SUBMIT_TOOLS[phase], "description": f"Submit the {phase} artifact and end the phase.",
            "input_schema": clean_schema(model.model_json_schema())}


class PhaseRunner:
    """
    #Feature: Agent phases (PRD 10)
    #Scenario: Manual tool-use loop for one phase: only the phase's tools, results appended in one user message,
               the phase ends when the submit tool's artifact validates; step budget per phase
    #Complexity: Time O(steps * tool cost)
    """

    def __init__(self, llm: ILlmClient, registry: ToolRegistry, services: ServicesFactory, events: EventSink,
                 max_steps: dict[str, int] | None = None) -> None:
        """
        #Feature: Agent phases
        #Scenario: Constructor injection
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a dependency is None.
        """
        if llm is None or registry is None or services is None or events is None:
            raise ValueError("[PhaseRunner.__init__] 'llm', 'registry', 'services' and 'events' are required.")
        self._llm, self._registry, self._services, self._events = llm, registry, services, events
        self._max_steps = {**a.MAX_STEPS, **(max_steps or {})}

    async def _submit(self, phase: str, raw: dict[str, Any], check: ArtifactCheck | None) -> tuple[Any, str]:
        """
        #Feature: Agent phases
        #Scenario: Validate a submission: schema first, then the phase's code-level checks
        #Complexity: Time O(s) - artifact size
        """
        try:
            artifact = ARTIFACTS[phase].model_validate(raw)
        except ValidationError as exc:
            return None, f"Rejected: {exc.json(include_url=False)[:2000]}"
        problems = await check(artifact) if check else []
        if problems:
            return None, "Rejected:\n- " + "\n- ".join(problems)
        return artifact, "Accepted."

    async def call_tool(self, ctx: ToolContext, name: str, args: dict[str, Any]) -> ToolCallResult:
        """
        #Feature: Agent phases
        #Scenario: One audited tool call in its own transaction, by the model or by the orchestrator
        #Complexity: Time O(1) plus the tool
        """
        async with self._services() as services:
            ctx.services = services
            outcome = await self._registry.call(ctx, name, args)
        await self._events("tool_call", ctx.phase, {"tool": outcome.name, "input": args, "ok": outcome.ok,
                                                    "error": outcome.error_code, "handle": outcome.handle,
                                                    "latency_ms": outcome.latency_ms})
        return outcome

    async def _tool_results(self, ctx: ToolContext, calls: list[dict[str, Any]], check: ArtifactCheck | None
                            ) -> tuple[list[dict[str, Any]], Any]:
        """
        #Feature: Agent phases
        #Scenario: Execute every tool_use block of a turn; each call runs in its own transaction
        #Complexity: Time O(c * tool cost)
        """
        results, artifact = [], None
        for call in calls:
            if call["name"] == a.SUBMIT_TOOLS[ctx.phase]:
                accepted, text = await self._submit(ctx.phase, call.get("input") or {}, check)
                artifact = artifact or accepted
                await self._events("tool_call", ctx.phase, {"tool": call["name"], "input": call.get("input"),
                                                            "ok": accepted is not None, "handle": None, "latency_ms": 0,
                                                            "error": None if accepted is not None else "Rejected",
                                                            "detail": text[:2000]})
                results.append({"type": "tool_result", "tool_use_id": call["id"], "content": text,
                                "is_error": accepted is None})
                continue
            outcome = await self.call_tool(ctx, call["name"], call.get("input") or {})
            results.append({"type": "tool_result", "tool_use_id": call["id"], "content": outcome.text,
                            "is_error": not outcome.ok})
        return results, artifact

    @staticmethod
    def _step_note(phase: str, left: int) -> dict[str, str]:
        """
        #Feature: Agent phases
        #Scenario: Text block after tool results telling the model its remaining step budget
        #Complexity: Time O(1) - constant
        """
        tool = a.SUBMIT_TOOLS[phase]
        return {"type": "text", "text": LAST_STEP.format(tool=tool) if left <= 1 else STEPS_LEFT.format(left=left)}

    async def run(self, ctx: ToolContext, opening: str, check: ArtifactCheck | None = None) -> PhaseOutcome:
        """
        #Feature: Agent phases
        #Scenario: Loop model turns until the artifact is accepted; once the step budget is spent only the submit tool
                   is offered, for a couple of turns, so a rejected artifact can still be repaired
        #Complexity: Time O(steps * tool cost)

        Raises:
            Errors.Domain.Base: When the model refuses, or the phase exhausts its steps or the run budget.
        """
        system = f"{BASE_SYSTEM}\n\nPhase: {ctx.phase}. Goal: {PHASE_GOALS[ctx.phase]}"
        submit = submit_tool(ctx.phase)
        tools = [*self._registry.definitions(ctx.phase, ctx.config), submit]
        limit = self._max_steps[ctx.phase]
        messages: list[dict[str, Any]] = [{"role": "user", "content": f"{opening}\n{STEPS_LEFT.format(left=limit)}"}]
        for step in range(1, limit + a.MAX_SUBMIT_REPAIRS + 1):
            if ctx.state.budget.exhausted():
                raise Errors.Domain.Base(f"Run budget exhausted ({ctx.state.budget.exhausted()}).", {"budget": True})
            ctx.state.budget.llm_calls += 1
            turn = await self._llm.turn(system, messages, tools if step < limit else [submit])
            ctx.state.budget.output_tokens += turn.output_tokens
            ctx.state.budget.input_tokens += turn.input_tokens
            await self._events("llm_turn", ctx.phase, {"step": step, "stop_reason": turn.stop_reason, "model": turn.model,
                                            "output_tokens": turn.output_tokens, "tool_calls": len(turn.tool_calls)})
            if turn.refusal:
                raise Errors.Domain.Base(f"Model declined the request ({turn.refusal}).", {"refusal": turn.refusal})
            messages.append({"role": "assistant", "content": turn.content})
            if not turn.tool_calls:
                messages.append({"role": "user", "content": NUDGE_SUBMIT.format(tool=a.SUBMIT_TOOLS[ctx.phase])})
                continue
            results, artifact = await self._tool_results(ctx, turn.tool_calls, check)
            if artifact is not None:
                return PhaseOutcome(artifact, step)
            messages.append({"role": "user", "content": [*results, self._step_note(ctx.phase, limit - step)]})
        raise Errors.Domain.Base(f"Phase {ctx.phase} used its {limit} steps and repairs without an accepted artifact.",
                                 {"phase": ctx.phase})

