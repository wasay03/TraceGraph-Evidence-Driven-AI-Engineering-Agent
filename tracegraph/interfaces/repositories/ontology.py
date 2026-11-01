from abc import ABC, abstractmethod
from typing import Any


class IOntologyRepository(ABC):
    """
    #Feature: Ontology catalog
    #Scenario: Contract for mirroring the registry into catalog tables
    #Complexity: Time O(1) - constant per call
    """

    @abstractmethod
    async def sync(self, semver: str, catalog: dict[str, Any]) -> int:
        """
        #Feature: Ontology catalog
        #Scenario: Upsert catalog rows; returns the ontology_version id
        #Complexity: Time O(n) - linear in catalog rows
        """

    @abstractmethod
    async def get_current(self) -> dict[str, Any] | None:
        """
        #Feature: Ontology catalog
        #Scenario: Latest loaded ontology version, or None
        #Complexity: Time O(1) - constant
        """
