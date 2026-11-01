import time
from typing import Any

from pydantic import BaseModel, Field

from tracegraph.constants import agent as a


class Budget(BaseModel):
    """
    #Feature: Agent budgets (PRD 9.3)
    #Scenario: Per-run counters; remaining budget is returned with every tool result
    #Complexity: Time O(1) - constant
    """

    tool_calls: int = 0
    query_calls: int = 0
    llm_calls: int = 0
    max_llm_calls: int = a.MAX_LLM_CALLS
    output_tokens: int = 0
    input_tokens: int = 0
    started_at: float = Field(default_factory=time.time)

    def exhausted(self) -> str | None:
        """
        #Feature: Agent budgets
        #Scenario: Name of the first exhausted budget, or None
        #Complexity: Time O(1) - constant
        """
        if self.llm_calls >= self.max_llm_calls:
            return "llm_calls"
        if self.tool_calls >= a.MAX_TOOL_CALLS:
            return "tool_calls"
        if self.output_tokens >= a.MAX_OUTPUT_TOKENS:
            return "output_tokens"
        if time.time() - self.started_at >= a.MAX_WALL_SECONDS:
            return "wall_time"
        return None

    def remaining(self) -> dict[str, int]:
        """
        #Feature: Agent budgets
        #Scenario: Remaining budget summary shown to the model
        #Complexity: Time O(1) - constant
        """
        return {"llm_calls": self.max_llm_calls - self.llm_calls, "tool_calls": a.MAX_TOOL_CALLS - self.tool_calls, "query_calls": a.MAX_QUERY_CALLS - self.query_calls,
                "output_tokens": a.MAX_OUTPUT_TOKENS - self.output_tokens,
                "seconds": int(a.MAX_WALL_SECONDS - (time.time() - self.started_at))}


class RunState(BaseModel):
    """
    #Feature: Persisted run state (PRD 10.5)
    #Scenario: Everything needed to resume, replay or diff a run; stored as JSONB, versioned per transition
    #Complexity: Time O(1) - constant
    """

    phase_history: list[str] = Field(default_factory=list)
    snapshot_id: int | None = None
    snapshot_seq: int | None = None
    commit: str | None = None
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    impact: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    worktree: str | None = None
    patches: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] | None = None
    feedback: str | None = None
    correction_rounds: int = 0
    reanalysis_rounds: int = 0
    handles: list[str] = Field(default_factory=list)
    call_counts: dict[str, int] = Field(default_factory=dict)
    budget: Budget = Field(default_factory=Budget)
    error: str | None = None
