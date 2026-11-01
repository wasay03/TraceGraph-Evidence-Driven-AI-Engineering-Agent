from abc import ABC, abstractmethod
from typing import Any


class IRepoRepository(ABC):
    """
    #Feature: Repositories
    #Scenario: Contract for registered repository persistence
    #Complexity: Time O(1) - constant per call
    """

    @abstractmethod
    async def create(self, url: str, name: str, default_branch: str) -> dict[str, Any]:
        """
        #Feature: Repositories
        #Scenario: Register a repository; conflicts raise Errors.HTTP.Conflict
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def get(self, repo_id: int) -> dict[str, Any]:
        """
        #Feature: Repositories
        #Scenario: Fetch one repository; missing raises Errors.HTTP.NotFound
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def list_page(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """
        #Feature: Repositories
        #Scenario: Page of repositories and the total count
        #Complexity: Time O(l) - linear in page size
        """
