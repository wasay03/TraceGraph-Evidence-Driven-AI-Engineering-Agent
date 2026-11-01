import json
from typing import Any

from tracegraph.interfaces.repositories.ontology import IOntologyRepository
from tracegraph.repositories.base import UdfRepository

_SYNC = "SELECT tg_ontology_sync(:semver, CAST(:catalog AS jsonb))"
_GET_CURRENT = "SELECT * FROM tg_ontology_get_current()"


class OntologyRepository(UdfRepository, IOntologyRepository):
    """
    #Feature: Ontology catalog
    #Scenario: Catalog mirror via tg_ontology_sync / tg_ontology_get_current
    #Complexity: Time O(1) - constant per call excluding database work
    """

    async def sync(self, semver: str, catalog: dict[str, Any]) -> int:
        """
        #Feature: Ontology catalog
        #Scenario: Upsert the catalog and return the version id
        #Complexity: Time O(n) - linear in catalog rows

        Raises:
            ValueError: When semver or catalog is missing.
        """
        if not semver or catalog is None:
            raise ValueError("[OntologyRepository.sync] 'semver' and 'catalog' are required.")
        return await self._fetch_scalar(_SYNC, {"semver": semver, "catalog": json.dumps(catalog)})

    async def get_current(self) -> dict[str, Any] | None:
        """
        #Feature: Ontology catalog
        #Scenario: Latest loaded version, or None when never synced
        #Complexity: Time O(1) - constant
        """
        return await self._fetch_one(_GET_CURRENT)
