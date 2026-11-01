from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from tracegraph.constants.graph import JOB_KIND_FULL


class SnapshotCreateRequest(BaseModel):
    """
    #Feature: Snapshots API
    #Scenario: Index a commit; ref "WORKTREE" indexes the working tree including uncommitted edits
    #Complexity: Time O(1) - constant
    """

    ref: str = Field(default="HEAD", min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_./^~@-]+$")
    kind: Literal["full", "incremental"] = JOB_KIND_FULL


class SnapshotResponse(BaseModel):
    """
    #Feature: Snapshots API
    #Scenario: Snapshot status and summary stats
    #Complexity: Time O(1) - constant
    """

    id: int
    repo_id: int
    seq: int
    commit_sha: str
    status: str
    ontology_version_id: int | None
    extractor_versions: dict[str, Any]
    stats: dict[str, Any]
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class SnapshotJobResponse(BaseModel):
    """
    #Feature: Snapshots API
    #Scenario: Accepted indexing request: the new snapshot and its queued job
    #Complexity: Time O(1) - constant
    """

    snapshot: SnapshotResponse
    job_id: int


class TypeCount(BaseModel):
    """
    #Feature: Snapshots API
    #Scenario: Count of rows of one type
    #Complexity: Time O(1) - constant
    """

    kind: str
    type_name: str
    total: int


class CoverageHoleSchema(BaseModel):
    """
    #Feature: Snapshots API
    #Scenario: One coverage hole
    #Complexity: Time O(1) - constant
    """

    node_id: int | None
    kind: str
    file_path: str | None
    line_start: int | None
    line_end: int | None
    detail: dict[str, Any]


class SnapshotDetailResponse(SnapshotResponse):
    """
    #Feature: Snapshots API
    #Scenario: Snapshot plus per-type counts and coverage holes (PRD 13.1 GET /snapshots/{id})
    #Complexity: Time O(1) - constant
    """

    counts: list[TypeCount]
    coverage_holes: list[CoverageHoleSchema]


class ValidationViolation(BaseModel):
    """
    #Feature: Snapshots API
    #Scenario: One graph validation violation
    #Complexity: Time O(1) - constant
    """

    violation: str
    edge_id: int | None
    edge_type: str | None
    src: int | None
    dst: int | None
    detail: str | None


class ValidationResponse(BaseModel):
    """
    #Feature: Snapshots API
    #Scenario: Result of the CI validation query for a snapshot
    #Complexity: Time O(1) - constant
    """

    snapshot_id: int
    valid: bool
    violations: list[ValidationViolation]
