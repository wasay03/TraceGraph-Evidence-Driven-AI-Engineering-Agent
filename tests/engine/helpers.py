from tests.conftest import SHOP_FIXTURE
from tracegraph.engine import GraphSnapshot
from tracegraph.engine.loader import graph_from_directory
from tracegraph.engine.loader import graph_from_payload as _from_payload
from tracegraph.extract import GraphPayload
from tracegraph.ontology import get_registry

REGISTRY = get_registry()


def graph_from_payload(payload: GraphPayload, repo_id: int = 1, seq: int = 1) -> GraphSnapshot:
    return _from_payload(REGISTRY, repo_id, seq, "c0ffee", payload)


def shop_graph() -> GraphSnapshot:
    return graph_from_directory(REGISTRY, SHOP_FIXTURE, 1, "file:///shop", "c0ffee")
