import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from tracegraph.agent.state import RunState
from tracegraph.constants import agent as a
from tracegraph.engine.graph import GraphSnapshot
from tracegraph.errors import AppError
from tracegraph.sandbox.run_sandbox import SandboxWorkspace

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolOutput:
    """
    #Feature: Tool registry (PRD 9.1)
    #Scenario: Compact rendering for the model plus an optional answer handle for claim binding
    #Complexity: Time O(1) - constant
    """

    text: str
    handle: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolContext:
    """
    #Feature: Tool registry
    #Scenario: What a tool may use: run state, base snapshot, services, sandbox and the approved scope
    #Complexity: Time O(1) - constant
    """

    run_id: int
    phase: str
    config: str
    state: RunState
    graph: GraphSnapshot
    services: Any
    repo_path: Path
    sandbox: SandboxWorkspace | None = None
    scope_files: frozenset[str] = frozenset()


Handler = Callable[[ToolContext, Any], Awaitable[ToolOutput]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """
    #Feature: Tool registry
    #Scenario: Typed, versioned, permissioned tool definition
    #Complexity: Time O(1) - constant
    """

    name: str
    version: str
    group: str
    side_effect: str
    phases: frozenset[str]
    input_model: type[BaseModel]
    handler: Handler
    description: str
    counts_as_query: bool = False
    scoped: bool = False


@dataclass(slots=True)
class ToolCallResult:
    """
    #Feature: Tool registry
    #Scenario: Result returned to the model and written to the audit log
    #Complexity: Time O(1) - constant
    """

    name: str
    ok: bool
    text: str
    handle: str | None
    latency_ms: int
    error_code: str | None = None


def clean_schema(schema: Any) -> Any:
    """
    #Feature: Tool registry
    #Scenario: Drop Pydantic titles and docstring descriptions from a JSON Schema (field descriptions stay)
    #Complexity: Time O(s) - schema size
    """
    if isinstance(schema, dict):
        return {k: clean_schema(v) for k, v in schema.items()
                if k != "title" and not (k == "description" and isinstance(v, str) and v.startswith("#Feature"))}
    if isinstance(schema, list):
        return [clean_schema(v) for v in schema]
    return schema


def _error(name: str, code: str, message: str, started: float) -> ToolCallResult:
    """
    #Feature: Tool registry
    #Scenario: Uniform error result (is_error for the model)
    #Complexity: Time O(1) - constant
    """
    return ToolCallResult(name, False, f"{code}: {message}", None, int((time.perf_counter() - started) * 1000), code)


class ToolRegistry:
    """
    #Feature: Tool registry (PRD 9)
    #Scenario: Phase gating, config (ablation) gating, scope gating, budgets, loop detection and audit records
    #Complexity: Time O(1) per call excluding the tool
    """

    def __init__(self) -> None:
        """
        #Feature: Tool registry
        #Scenario: Empty registry
        #Complexity: Time O(1) - constant
        """
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """
        #Feature: Tool registry
        #Scenario: Add a tool; names are unique
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: On duplicate names.
        """
        if spec.name in self._tools:
            raise ValueError(f"[ToolRegistry.register] Tool {spec.name!r} registered twice.")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        """
        #Feature: Tool registry
        #Scenario: Look up a tool by name
        #Complexity: Time O(1) - constant
        """
        return self._tools.get(name)

    def available(self, phase: str, config: str) -> list[ToolSpec]:
        """
        #Feature: Tool registry
        #Scenario: Tools allowed in a phase under an ablation configuration, in stable order (prompt caching)
        #Complexity: Time O(t) - number of tools
        """
        groups = a.CONFIG_GROUPS[config]
        return [t for t in sorted(self._tools.values(), key=lambda t: t.name) if phase in t.phases and t.group in groups]

    def definitions(self, phase: str, config: str) -> list[dict[str, Any]]:
        """
        #Feature: Tool registry
        #Scenario: Messages API tool definitions (JSON Schema from the Pydantic input model)
        #Complexity: Time O(t) - number of tools
        """
        return [{"name": t.name, "description": f"[{t.group} v{t.version}] {t.description}",
                 "input_schema": clean_schema(t.input_model.model_json_schema())} for t in self.available(phase, config)]

    def _gate(self, ctx: ToolContext, spec: ToolSpec | None, name: str, raw: dict[str, Any]) -> tuple[str, str] | None:
        """
        #Feature: Tool guardrails (PRD 9.3)
        #Scenario: Reason a call is refused before it runs, or None
        #Complexity: Time O(1) - constant
        """
        if spec is None or spec.group not in a.CONFIG_GROUPS[ctx.config]:
            return "UnknownTool", f"{name} is not available in configuration {ctx.config}"
        if ctx.phase not in spec.phases:
            return "PhaseViolation", f"{name} is not allowed in phase {ctx.phase}; allowed: {sorted(spec.phases)}"
        exhausted = ctx.state.budget.exhausted()
        if exhausted or (spec.counts_as_query and ctx.state.budget.query_calls >= a.MAX_QUERY_CALLS):
            return "BudgetExceeded", f"{exhausted or 'query_calls'} budget exhausted"
        key = f"{ctx.phase}:{name}:{json.dumps(raw, sort_keys=True)}"
        if ctx.state.call_counts.get(key, 0) >= a.MAX_REPEATED_CALLS:
            return "LoopDetected", f"identical {name} call refused after {a.MAX_REPEATED_CALLS} repeats"
        ctx.state.call_counts[key] = ctx.state.call_counts.get(key, 0) + 1
        return None

    async def call(self, ctx: ToolContext, name: str, raw: dict[str, Any]) -> ToolCallResult:
        """
        #Feature: Tool registry
        #Scenario: Gate, validate, run and render one tool call; every outcome is a result, never an exception
        #Complexity: Time O(1) plus the tool
        """
        started, spec = time.perf_counter(), self._tools.get(name)
        refusal = self._gate(ctx, spec, name, raw or {})
        if refusal:
            return _error(name, *refusal, started)
        try:
            args = spec.input_model.model_validate(raw or {})
        except ValidationError as exc:
            return _error(name, "InvalidInput", exc.json(include_url=False)[:1500], started)
        ctx.state.budget.tool_calls += 1
        ctx.state.budget.query_calls += int(spec.counts_as_query)
        try:
            out = await spec.handler(ctx, args)
        except AppError as exc:
            return _error(name, type(exc).__name__.removesuffix("Error") or "Failed", exc.message, started)
        if out.handle:
            ctx.state.handles.append(out.handle)
        text = out.text if len(out.text) <= a.MAX_TOOL_OUTPUT_CHARS else out.text[: a.MAX_TOOL_OUTPUT_CHARS] + "\n[truncated]"
        footer = f"\n[handle={out.handle}] " if out.handle else "\n"
        return ToolCallResult(name, True, text + footer + f"budget={ctx.state.budget.remaining()}", out.handle,
                              int((time.perf_counter() - started) * 1000))
