from fastapi import APIRouter, Depends

from tracegraph.constants.permissions import query
from tracegraph.containers import ServiceContainer
from tracegraph.dependencies import get_service_container, require_permission
from tracegraph.schemas.impact import ImpactReport, ImpactRequest, InvariantCheckRequest, InvariantCheckResponse

router = APIRouter(tags=["impact"])


@router.post("/impact", response_model=ImpactReport, dependencies=[Depends(require_permission(query.execute))])
async def analyze_impact(request: ImpactRequest, services: ServiceContainer = Depends(get_service_container)) -> ImpactReport:
    """
    #Feature: Impact API
    #Scenario: POST /impact - ChangeSpecs -> overlay + impact report
    #Complexity: Time per analysis

    Args:
        request: Repo, optional snapshot and ChangeSpecs.
        services: Per-request service container.

    Returns:
        ImpactReport with a handle.
    """
    return await services.impact.analyze(request)


@router.get("/impact/{handle}", response_model=ImpactReport, dependencies=[Depends(require_permission(query.read))])
async def get_impact(handle: str, services: ServiceContainer = Depends(get_service_container)) -> ImpactReport:
    """
    #Feature: Impact API
    #Scenario: GET /impact/{handle} - stored report
    #Complexity: Time O(1) - unique index lookup
    """
    return await services.impact.get_report(handle)


@router.post("/invariants/check", response_model=InvariantCheckResponse,
             dependencies=[Depends(require_permission(query.execute))])
async def check_invariants(
    request: InvariantCheckRequest, services: ServiceContainer = Depends(get_service_container)
) -> InvariantCheckResponse:
    """
    #Feature: Invariants API
    #Scenario: POST /invariants/check - run invariant packs on a snapshot
    #Complexity: Time cost of the selected invariants
    """
    return await services.impact.check_invariants(request)
