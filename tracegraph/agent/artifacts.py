from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Artifact(BaseModel):
    """
    #Feature: Agent exit artifacts (PRD 10.1)
    #Scenario: Base for schema-validated phase outputs
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(extra="forbid")


class Intake(_Artifact):
    """
    #Feature: Agent exit artifacts
    #Scenario: Request classification and resolved entities
    #Complexity: Time O(1) - constant
    """

    kind: Literal["question", "change"]
    summary: str = Field(min_length=1)
    entities: list[str] = Field(default_factory=list, description="Exact node keys resolved with resolve_entity")
    ambiguities: list[str] = Field(default_factory=list)


class ContextSet(_Artifact):
    """
    #Feature: Agent exit artifacts
    #Scenario: Relevant subgraph as node keys plus supporting answer handles
    #Complexity: Time O(1) - constant
    """

    node_keys: list[str] = Field(min_length=1)
    handles: list[str] = Field(default_factory=list)
    notes: str = ""


class Analysis(_Artifact):
    """
    #Feature: Agent exit artifacts
    #Scenario: ChangeSpecs and the simulate_change report handle (change), or the answer handles (question)
    #Complexity: Time O(1) - constant
    """

    change_specs: list[dict[str, Any]] = Field(default_factory=list)
    impact_handle: str | None = None
    answer_handles: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    notes: str = ""


class PlanStep(_Artifact):
    """
    #Feature: Agent exit artifacts
    #Scenario: One plan step naming its targets and the findings or obligations it serves
    #Complexity: Time O(1) - constant
    """

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    files: list[str] = Field(min_length=1)
    targets: list[str] = Field(min_length=1, description="Node keys the step changes")
    serves: list[str] = Field(min_length=1, description="Finding node keys or obligation kinds")


class AcceptedRisk(_Artifact):
    """
    #Feature: Agent exit artifacts
    #Scenario: A BREAKS finding knowingly left unaddressed
    #Complexity: Time O(1) - constant
    """

    node: str
    reason: str = Field(min_length=1)


class Plan(_Artifact):
    """
    #Feature: Agent exit artifacts
    #Scenario: Ordered steps, scope set, tests and accepted risks (validated by plan rules, PRD 10.2)
    #Complexity: Time O(1) - constant
    """

    steps: list[PlanStep] = Field(min_length=1)
    scope_files: list[str] = Field(min_length=1)
    tests: list[str] = Field(default_factory=list, description="pytest node ids")
    accepted_risks: list[AcceptedRisk] = Field(default_factory=list)


class PatchSet(_Artifact):
    """
    #Feature: Agent exit artifacts
    #Scenario: Patches applied in the sandbox and the steps they implement
    #Complexity: Time O(1) - constant
    """

    patch_ids: list[str] = Field(min_length=1)
    steps_done: list[str] = Field(min_length=1)
    summary: str = ""


class Claim(_Artifact):
    """
    #Feature: Agent exit artifacts
    #Scenario: One report claim bound to the answer handle that supports it (PRD 10.4 claim binding)
    #Complexity: Time O(1) - constant
    """

    text: str = Field(min_length=1)
    handle: str = Field(min_length=1)
    truth: Literal["TRUE", "FALSE", "UNKNOWN", "ROWS"] | None = None


class Report(_Artifact):
    """
    #Feature: Agent exit artifacts
    #Scenario: Final evidence-backed report
    #Complexity: Time O(1) - constant
    """

    summary: str = Field(min_length=1)
    claims: list[Claim] = Field(min_length=1)


ARTIFACTS: dict[str, type[_Artifact]] = {
    "intake": Intake, "discover": ContextSet, "analyze": Analysis, "plan": Plan, "implement": PatchSet,
    "report": Report,
}
