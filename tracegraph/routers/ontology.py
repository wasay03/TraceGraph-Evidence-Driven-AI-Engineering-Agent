from fastapi import APIRouter, Depends

from tracegraph.constants.permissions import ontology
from tracegraph.containers import ServiceContainer
from tracegraph.dependencies import get_service_container, require_permission
from tracegraph.schemas.ontology import OntologyResponse

router = APIRouter(prefix="/ontology", tags=["ontology"])


@router.get("", response_model=OntologyResponse, dependencies=[Depends(require_permission(ontology.read))])
async def describe_ontology(services: ServiceContainer = Depends(get_service_container)) -> OntologyResponse:
    """
    #Feature: Ontology API
    #Scenario: GET /ontology - node and edge types, signatures and version
    #Complexity: Time O(n + e) - linear in registry size

    Args:
        services: Per-request service container.

    Returns:
        OntologyResponse.
    """
    return await services.ontology.describe()


@router.post("/sync", response_model=OntologyResponse, dependencies=[Depends(require_permission(ontology.manage))])
async def sync_ontology(services: ServiceContainer = Depends(get_service_container)) -> OntologyResponse:
    """
    #Feature: Ontology API
    #Scenario: POST /ontology/sync - mirror the registry into the catalog tables now
    #Complexity: Time O(n + e) - linear in registry size

    Args:
        services: Per-request service container.

    Returns:
        OntologyResponse after the sync.
    """
    await services.ontology.ensure_catalog()
    return await services.ontology.describe()
