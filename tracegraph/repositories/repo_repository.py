from typing import Any

from tracegraph.interfaces.repositories.repos import IRepoRepository
from tracegraph.repositories.base import UdfRepository

_CREATE = "SELECT * FROM tg_repo_create(:url, :name, :default_branch)"
_GET = "SELECT * FROM tg_repo_get(:id)"
_LIST = "SELECT * FROM tg_repo_list(:limit, :offset)"
_FIND_BY_URL = "SELECT * FROM tg_repo_find_by_url(:url)"


class RepoRepository(UdfRepository, IRepoRepository):
    """
    #Feature: Repositories
    #Scenario: Repository persistence via tg_repo_* functions
    #Complexity: Time O(1) - constant per call excluding database work
    """

    async def create(self, url: str, name: str, default_branch: str) -> dict[str, Any]:
        """
        #Feature: Repositories
        #Scenario: Insert a repository row
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When url or name is missing.
            Errors.HTTP.Conflict: When the url is already registered (TG409).
        """
        if not url or not name:
            raise ValueError("[RepoRepository.create] 'url' and 'name' are required.")
        return await self._fetch_one(_CREATE, {"url": url, "name": name, "default_branch": default_branch})

    async def get(self, repo_id: int) -> dict[str, Any]:
        """
        #Feature: Repositories
        #Scenario: Fetch one repository
        #Complexity: Time O(1) - constant

        Raises:
            Errors.HTTP.NotFound: When the id is unknown (TG404).
        """
        if repo_id is None:
            raise ValueError("[RepoRepository.get] 'repo_id' is required.")
        return await self._fetch_one(_GET, {"id": repo_id})

    async def find_by_url(self, url: str) -> dict[str, Any] | None:
        """
        #Feature: Repositories
        #Scenario: Repository registered under a URL, or None
        #Complexity: Time O(1) - unique index lookup
        """
        if not url:
            raise ValueError("[RepoRepository.find_by_url] 'url' is required.")
        return await self._fetch_one(_FIND_BY_URL, {"url": url})

    async def list_page(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """
        #Feature: Repositories
        #Scenario: Page of repositories with total from the window count
        #Complexity: Time O(l) - linear in page size
        """
        rows = await self._fetch_all(_LIST, {"limit": limit, "offset": offset})
        total = rows[0]["total"] if rows else 0
        return [{k: v for k, v in row.items() if k != "total"} for row in rows], total
