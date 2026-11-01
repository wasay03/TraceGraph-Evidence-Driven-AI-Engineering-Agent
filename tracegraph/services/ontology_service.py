import json
import logging

from tracegraph.interfaces.repositories.ontology import IOntologyRepository
from tracegraph.interfaces.services.ontology import IOntologyService
from tracegraph.ontology import Registry, to_catalog
from tracegraph.ontology.specs import PropSpec
from tracegraph.schemas.ontology import EdgeTypeSchema, NodeTypeSchema, OntologyResponse, PropSchema
from tracegraph.utilities.ids import content_hash

logger = logging.getLogger(__name__)


def _props(props: dict[str, PropSpec]) -> list[PropSchema]:
    """
    #Feature: Ontology
    #Scenario: Map prop specs to API schema
    #Complexity: Time O(p) - linear in props
    """
    return [PropSchema(name=n, value_type=p.value_type, required=p.required,
                       enum_values=list(p.enum_values) if p.enum_values else None) for n, p in props.items()]


class OntologyService(IOntologyService):
    """
    #Feature: Ontology
    #Scenario: Serve the code registry and keep the database catalog in step with it
    #Complexity: Time O(n + e) - linear in registry size
    """

    def __init__(self, ontology_repository: IOntologyRepository, registry: Registry) -> None:
        """
        #Feature: Ontology
        #Scenario: Constructor injection of the catalog repository and registry
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When an argument is None.
        """
        if ontology_repository is None or registry is None:
            raise ValueError("[OntologyService.__init__] 'ontology_repository' and 'registry' are required.")
        self._repo = ontology_repository
        self._registry = registry

    def _catalog_version(self) -> tuple[str, dict]:
        """
        #Feature: Ontology
        #Scenario: Version label "semver+hash" so an unbumped registry edit still triggers a sync
        #Complexity: Time O(n + e) - serialises the catalog
        """
        catalog = to_catalog(self._registry)
        digest = content_hash(json.dumps(catalog, sort_keys=True))[:12]
        return f"{self._registry.semver}+{digest}", catalog

    async def ensure_catalog(self) -> int:
        """
        #Feature: Ontology
        #Scenario: Sync only when the stored version label differs from the registry's
        #Complexity: Time O(n + e) - linear in registry size

        Returns:
            ontology_version id.
        """
        label, catalog = self._catalog_version()
        current = await self._repo.get_current()
        if current is not None and current["semver"] == label:
            return current["id"]
        version_id = await self._repo.sync(label, catalog)
        logger.info("Ontology catalog synced", extra={"ontology_version": label, "ontology_version_id": version_id})
        return version_id

    async def describe(self) -> OntologyResponse:
        """
        #Feature: Ontology
        #Scenario: Registry types with effective props and catalog sync state
        #Complexity: Time O(n + e) - linear in registry size
        """
        label, _ = self._catalog_version()
        current = await self._repo.get_current()
        r = self._registry
        nodes = [NodeTypeSchema(id=n.id, name=n.name, parent=n.parent, abstract=n.abstract, key=n.key,
                                tiers=sorted(n.tiers), owner=n.owner, props=_props(r.node_props(n.name)))
                 for n in r.node_types]
        edges = [EdgeTypeSchema(id=e.id, name=e.name, signatures=list(e.signatures), cardinality=e.cardinality,
                                inverse=e.inverse, flags=e.flags, tiers=sorted(e.tiers), evidence=e.evidence,
                                props=_props(e.props)) for e in r.edge_types]
        return OntologyResponse(semver=r.semver, catalog_version_id=current["id"] if current else None,
                                catalog_in_sync=bool(current and current["semver"] == label),
                                node_types=nodes, edge_types=edges)
