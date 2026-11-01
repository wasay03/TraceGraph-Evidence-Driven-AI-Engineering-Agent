from fastapi import APIRouter, Depends

from tracegraph.constants.permissions import repo
from tracegraph.containers import ServiceContainer
from tracegraph.dependencies import get_service_container, require_permission
from tracegraph.schemas.snapshots import SnapshotDetailResponse, ValidationResponse

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
