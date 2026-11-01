from fastapi import APIRouter, Depends, Query

from tracegraph.constants.permissions import repo
from tracegraph.containers import ServiceContainer
from tracegraph.dependencies import get_service_container, require_permission
from tracegraph.schemas.snapshots import SnapshotDetailResponse, SourceResponse, ValidationResponse

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/{snapshot_id}", response_model=SnapshotDetailResponse,
            dependencies=[Depends(require_permission(repo.read))])
async def get_snapshot(
    snapshot_id: int, services: ServiceContainer = Depends(get_service_container)
) -> SnapshotDetailResponse:
    """
    #Feature: Snapshots API
    #Scenario: GET /snapshots/{id} - status, counts, coverage holes, extractor versions
    #Complexity: Time O(n + e) - database aggregate
    """
    return await services.snapshots.get(snapshot_id)


@router.get("/{snapshot_id}/validation", response_model=ValidationResponse,
            dependencies=[Depends(require_permission(repo.read))])
async def validate_snapshot(
    snapshot_id: int, services: ServiceContainer = Depends(get_service_container)
) -> ValidationResponse:
    """
    #Feature: Graph validation
    #Scenario: GET /snapshots/{id}/validation - CI validation query
    #Complexity: Time O(e) - database scan of edges
    """
    return await services.snapshots.validate(snapshot_id)


@router.get("/{snapshot_id}/source", response_model=SourceResponse,
            dependencies=[Depends(require_permission(repo.read))])
async def get_source(
    snapshot_id: int,
    path: str = Query(min_length=1, max_length=1024),
    start: int = Query(1, ge=1),
    end: int | None = Query(None, ge=1),
    services: ServiceContainer = Depends(get_service_container),
) -> SourceResponse:
    """
    #Feature: Provenance
    #Scenario: GET /snapshots/{id}/source - source lines for expanding evidence
    #Complexity: Time O(s) - file size
    """
    return await services.snapshots.source(snapshot_id, path, start, end)
