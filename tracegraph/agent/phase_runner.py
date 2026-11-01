import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from tracegraph.agent.artifacts import ARTIFACTS
from tracegraph.constants import agent as a
from tracegraph.constants.agent_prompts import BASE_SYSTEM, NUDGE_SUBMIT, PHASE_GOALS
from tracegraph.errors import Errors
from tracegraph.interfaces.llm import ILlmClient
from tracegraph.tools.registry import ToolContext, ToolRegistry, clean_schema

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

    def __init__(self, llm: ILlmClient, registry: ToolRegistry, services: ServicesFactory, events: EventSink) -> None:
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
                results.append({"type": "tool_result", "tool_use_id": call["id"], "content": text,
                                "is_error": accepted is None})
                continue
            async with self._services() as services:
                ctx.services = services
                outcome = await self._registry.call(ctx, call["name"], call.get("input") or {})
            await self._events("tool_call", ctx.phase, {"tool": outcome.name, "input": call.get("input"), "ok": outcome.ok,
                                             "error": outcome.error_code, "handle": outcome.handle,
                                             "latency_ms": outcome.latency_ms})
            results.append({"type": "tool_result", "tool_use_id": call["id"], "content": outcome.text,
                            "is_error": not outcome.ok})
        return results, artifact

    async def run(self, ctx: ToolContext, opening: str, check: ArtifactCheck | None = None) -> PhaseOutcome:
        """
        #Feature: Agent phases
        #Scenario: Loop model turns until the artifact is accepted or the step budget is spent
        #Complexity: Time O(steps * tool cost)

        Raises:
            Errors.Domain.Base: When the model refuses, or the phase exhausts its steps or the run budget.
        """
        system = f"{BASE_SYSTEM}\n\nPhase: {ctx.phase}. Goal: {PHASE_GOALS[ctx.phase]}"
        tools = [*self._registry.definitions(ctx.phase, ctx.config), submit_tool(ctx.phase)]
        messages: list[dict[str, Any]] = [{"role": "user", "content": opening}]
        for step in range(1, a.MAX_STEPS[ctx.phase] + 1):
            if ctx.state.budget.exhausted():
                raise Errors.Domain.Base(f"Run budget exhausted ({ctx.state.budget.exhausted()}).", {"budget": True})
            turn = await self._llm.turn(system, messages, tools)
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
            messages.append({"role": "user", "content": results})
            if artifact is not None:
                return PhaseOutcome(artifact, step)
        raise Errors.Domain.Base(f"Phase {ctx.phase} used its {a.MAX_STEPS[ctx.phase]} steps without an artifact.",
                                 {"phase": ctx.phase})

