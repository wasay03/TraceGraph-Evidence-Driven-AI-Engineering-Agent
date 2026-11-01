from abc import ABC, abstractmethod

from tracegraph.schemas.common import Page
from tracegraph.schemas.repos import RepoCreateRequest, RepoResponse


class IRepoService(ABC):
    """
    #Feature: Repositories
    #Scenario: Contract for registering and reading repositories
    #Complexity: Time O(1) - constant per call
    """

    @abstractmethod
    async def register(self, request: RepoCreateRequest) -> RepoResponse:
        """
        #Feature: Repositories
        #Scenario: Validate the location and register the repository
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def get(self, repo_id: int) -> RepoResponse:
        """
        #Feature: Repositories
        #Scenario: Fetch one repository
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def list_page(self, page: int, limit: int) -> Page[RepoResponse]:
        """
        #Feature: Repositories
        #Scenario: Paged list of repositories
        #Complexity: Time O(l) - linear in page size
        """
