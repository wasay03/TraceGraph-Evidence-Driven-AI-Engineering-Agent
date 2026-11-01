from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from tracegraph.constants.agent import CONFIG_GROUPS, MODE_INTERACTIVE

Config = Literal[tuple(CONFIG_GROUPS)]  # type: ignore[valid-type]


class RunCreateRequest(BaseModel):
    """
    #Feature: Runs API (PRD 13.1 POST /runs)
    #Scenario: Start an agent run on a repo's snapshot (latest ready when omitted)
    #Complexity: Time O(1) - constant
    """

    repo_id: int = Field(ge=1)
    snapshot_id: int | None = Field(default=None, ge=1)
    request: str = Field(min_length=3, max_length=8000)
    mode: Literal["interactive", "benchmark"] = MODE_INTERACTIVE
    config: Config = "A4"


class ApprovalRequest(BaseModel):
    """
    #Feature: Runs API (PRD 13.1 POST /runs/{id}/approval)
    #Scenario: Approve or reject the plan; an edited plan replaces it before approval
    #Complexity: Time O(1) - constant
    """

    approved: bool
    comment: str | None = Field(default=None, max_length=4000)
    plan: dict[str, Any] | None = None


class ClarifyRequest(BaseModel):
    """
    #Feature: Runs API
    #Scenario: Answer the agent's ambiguity question and resume
    #Complexity: Time O(1) - constant
    """

    answer: str = Field(min_length=1, max_length=4000)


class RetryRequest(BaseModel):
    """
    #Feature: Runs API
    #Scenario: Resume a failed or budget-exhausted run from its saved phase, optionally allowing more LLM calls
    #Complexity: Time O(1) - constant
    """

    extra_llm_calls: int = Field(default=0, ge=0, le=200)


class RunEventOut(BaseModel):
    """
    #Feature: Runs API
    #Scenario: One audit event
    #Complexity: Time O(1) - constant
    """

    seq: int
    kind: str
    phase: str
    payload: dict[str, Any]
    created_at: datetime


class RunResponse(BaseModel):
    """
    #Feature: Runs API (PRD 13.1 GET /runs/{id})
    #Scenario: Run status, phase, artifacts, verification and recent events
    #Complexity: Time O(1) - constant
    """

    id: int
    repo_id: int
    snapshot_id: int
    mode: str
    config: str
    status: str
    phase: str
    request: str
    version: int
    state: dict[str, Any]
    events: list[RunEventOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
