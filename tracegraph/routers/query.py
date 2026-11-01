from fastapi import APIRouter, Depends

from tracegraph.constants.permissions import query
from tracegraph.containers import ServiceContainer
from tracegraph.dependencies import get_service_container, require_permission
from tracegraph.schemas.query import Answer, QueryRequest

router = APIRouter(tags=["query"])


@router.post("/query", response_model=Answer, dependencies=[Depends(require_permission(query.execute))])
async def run_query(request: QueryRequest, services: ServiceContainer = Depends(get_service_container)) -> Answer:
    """
    #Feature: Query API
    #Scenario: POST /query - evaluate typed IR; returns an Answer with derivations and a handle
    #Complexity: Time per query

    Args:
        request: Repo, optional snapshot and IR.
        services: Per-request service container.

    Returns:
        Answer.
    """
    return await services.query.run(request)


@router.get("/answers/{handle}", response_model=Answer, dependencies=[Depends(require_permission(query.read))])
async def get_answer(handle: str, services: ServiceContainer = Depends(get_service_container)) -> Answer:
    """
    #Feature: Query API
    #Scenario: GET /answers/{handle} - full stored answer
    #Complexity: Time O(1) - unique index lookup
    """
    return await services.query.get_answer(handle)
