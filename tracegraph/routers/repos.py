from fastapi import APIRouter, Depends, Query, status

from tracegraph.constants.permissions import repo
from tracegraph.containers import ServiceContainer
from tracegraph.dependencies import get_service_container, require_permission
from tracegraph.schemas.common import Page
from tracegraph.schemas.repos import RepoCreateRequest, RepoResponse
from tracegraph.schemas.snapshots import SnapshotCreateRequest, SnapshotJobResponse, SnapshotResponse

router = APIRouter(prefix="/repos", tags=["repos"])


@router.post("", response_model=RepoResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(repo.create))])
async def register_repo(
    request: RepoCreateRequest, services: ServiceContainer = Depends(get_service_container)
) -> RepoResponse:
    """
    #Feature: Repositories API
    #Scenario: POST /repos - register a local repository
    #Complexity: Time O(1) - constant

    Args:
        request: Repository location and metadata.
        services: Per-request service container.

    Returns:
        The registered repository.
    """
    return await services.repos.register(request)


@router.get("", response_model=Page[RepoResponse], dependencies=[Depends(require_permission(repo.read))])
async def list_repos(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    services: ServiceContainer = Depends(get_service_container),
) -> Page[RepoResponse]:
    """
    #Feature: Repositories API
    #Scenario: GET /repos - paged list
    #Complexity: Time O(l) - linear in page size
    """
    return await services.repos.list_page(page=page, limit=limit)


@router.get("/{repo_id}", response_model=RepoResponse, dependencies=[Depends(require_permission(repo.read))])
async def get_repo(repo_id: int, services: ServiceContainer = Depends(get_service_container)) -> RepoResponse:
    """
    #Feature: Repositories API
    #Scenario: GET /repos/{id}
    #Complexity: Time O(1) - constant
    """
    return await services.repos.get(repo_id)


@router.post("/{repo_id}/snapshots", response_model=SnapshotJobResponse, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(require_permission(repo.execute))])
async def index_repo(
    repo_id: int, request: SnapshotCreateRequest, services: ServiceContainer = Depends(get_service_container)
) -> SnapshotJobResponse:
    """
    #Feature: Snapshots API
    #Scenario: POST /repos/{id}/snapshots - index a commit in the background; returns the job id
    #Complexity: Time O(1) - constant

    Args:
        repo_id: Repository id.
        request: Ref and full/incremental kind.
        services: Per-request service container.

    Returns:
        Pending snapshot and queued job id.
    """
    return await services.snapshots.request_index(repo_id, request)


@router.get("/{repo_id}/snapshots", response_model=Page[SnapshotResponse],
            dependencies=[Depends(require_permission(repo.read))])
async def list_snapshots(
    repo_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    services: ServiceContainer = Depends(get_service_container),
) -> Page[SnapshotResponse]:
    """
    #Feature: Snapshots API
    #Scenario: GET /repos/{id}/snapshots - newest first
    #Complexity: Time O(l) - linear in page size
    """
    return await services.snapshots.list_page(repo_id, page=page, limit=limit)
