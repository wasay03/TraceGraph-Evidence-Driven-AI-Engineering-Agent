from tests.conftest import SHOP_FIXTURE
from tracegraph.engine import GraphSnapshot
from tracegraph.extract import GraphPayload, run_extraction
from tracegraph.ontology import get_registry

REGISTRY = get_registry()


def graph_from_payload(payload: GraphPayload, repo_id: int = 1, seq: int = 1) -> GraphSnapshot:
    nodes = [{**n, "line_start": n["span_lo"], "line_end": n["span_hi"]} for n in payload.nodes]
    holes = [h for h in payload.holes]
    return GraphSnapshot.from_rows(REGISTRY, repo_id, seq, "c0ffee", nodes, payload.edges, holes)


def shop_graph() -> GraphSnapshot:
    return graph_from_payload(run_extraction(REGISTRY, SHOP_FIXTURE, 1, "file:///shop", "c0ffee").payload)
