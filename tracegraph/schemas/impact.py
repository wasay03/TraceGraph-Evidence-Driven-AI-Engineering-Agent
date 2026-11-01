from pydantic import BaseModel, Field

from tracegraph.impact.changespec import ChangeSpec
from tracegraph.impact.report import ImpactReport, InvariantChangeOut


class ImpactRequest(BaseModel):
    """
    #Feature: Impact API (PRD 13.1 POST /impact)
    #Scenario: ChangeSpecs evaluated on a repo's snapshot (latest ready when omitted)
    #Complexity: Time O(1) - constant
    """

    repo_id: int = Field(ge=1)
    snapshot_id: int | None = Field(default=None, ge=1)
    changes: list[ChangeSpec] = Field(min_length=1, max_length=20)


class InvariantCheckRequest(BaseModel):
    """
    #Feature: Invariants API
    #Scenario: Run invariant packs on a snapshot
    #Complexity: Time O(1) - constant
    """

    repo_id: int = Field(ge=1)
    snapshot_id: int | None = Field(default=None, ge=1)
    invariants: list[str] = Field(default_factory=list)


class InvariantCheckResponse(BaseModel):
    """
    #Feature: Invariants API
    #Scenario: Violations per invariant; truth FALSE when any definite violation exists
    #Complexity: Time O(1) - constant
    """

    snapshot_seq: int
    truth: str
    checked: list[str]
    violations: list[InvariantChangeOut]


__all__ = ["ImpactReport", "ImpactRequest", "InvariantCheckRequest", "InvariantCheckResponse"]
