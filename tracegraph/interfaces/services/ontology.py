from abc import ABC, abstractmethod

from tracegraph.schemas.ontology import OntologyResponse


class IOntologyService(ABC):
    """
    #Feature: Ontology
    #Scenario: Contract for describing the registry and keeping the catalog mirror current
    #Complexity: Time O(1) - constant per call excluding registry size
    """

    @abstractmethod
    async def describe(self) -> OntologyResponse:
        """
        #Feature: Ontology
        #Scenario: Registry node and edge types plus catalog sync state
        #Complexity: Time O(n + e) - linear in registry size
        """

    @abstractmethod
    async def ensure_catalog(self) -> int:
        """
        #Feature: Ontology
        #Scenario: Sync the catalog if the registry changed; return the ontology_version id
        #Complexity: Time O(n + e) - linear in registry size when syncing
        """
