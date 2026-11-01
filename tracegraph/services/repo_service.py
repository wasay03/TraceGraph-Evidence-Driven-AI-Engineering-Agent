import logging

from tracegraph.interfaces.repositories.repos import IRepoRepository
from tracegraph.interfaces.services.repos import IRepoService
from tracegraph.interfaces.workspace import IWorkspace
from tracegraph.schemas.common import Page
from tracegraph.schemas.repos import RepoCreateRequest, RepoResponse

logger = logging.getLogger(__name__)


class RepoService(IRepoService):
    """
    #Feature: Repositories
    #Scenario: Register local repositories after checking they exist
    #Complexity: Time O(1) - constant per call
    """

    def __init__(self, repo_repository: IRepoRepository, workspace: IWorkspace) -> None:
        """
        #Feature: Repositories
        #Scenario: Constructor injection
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When an argument is None.
        """
        if repo_repository is None or workspace is None:
            raise ValueError("[RepoService.__init__] 'repo_repository' and 'workspace' are required.")
        self._repo = repo_repository
        self._workspace = workspace

    async def register(self, request: RepoCreateRequest) -> RepoResponse:
        """
        #Feature: Repositories
        #Scenario: Normalise to file:// URL, default the name to the directory name, insert
        #Complexity: Time O(1) - constant

        Raises:
            Errors.HTTP.BadRequest: When the location is not a local directory.
            Errors.HTTP.Conflict: When already registered.
        """
        path = self._workspace.local_path(request.url)
        row = await self._repo.create(url=path.as_uri(), name=request.name or path.name,
                                      default_branch=request.default_branch)
        logger.info("Repository registered", extra={"repo_id": row["id"], "url": row["url"]})
        return RepoResponse(**row)

    async def get(self, repo_id: int) -> RepoResponse:
        """
        #Feature: Repositories
        #Scenario: Fetch one repository
        #Complexity: Time O(1) - constant
        """
        return RepoResponse(**await self._repo.get(repo_id))

    async def list_page(self, page: int, limit: int) -> Page[RepoResponse]:
        """
        #Feature: Repositories
        #Scenario: Paged list
        #Complexity: Time O(l) - linear in page size
        """
        rows, total = await self._repo.list_page(limit=limit, offset=(page - 1) * limit)
        return Page[RepoResponse](items=[RepoResponse(**r) for r in rows], total=total, page=page, limit=limit)
