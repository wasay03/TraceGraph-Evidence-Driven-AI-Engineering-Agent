from fastapi import APIRouter, Depends

from tracegraph.containers import ServiceContainer
from tracegraph.dependencies import get_service_container
from tracegraph.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(services: ServiceContainer = Depends(get_service_container)) -> HealthResponse:
    """
    #Feature: Health
    #Scenario: Unauthenticated liveness and readiness probe
    #Complexity: Time O(1) - constant

    Args:
        services: Per-request service container.

    Returns:
        HealthResponse.
    """
    return await services.health.status()
