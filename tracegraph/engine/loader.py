from pathlib import Path

from tracegraph.engine.graph import GraphSnapshot
from tracegraph.extract import GraphPayload, run_extraction
from tracegraph.ontology import Registry


def graph_from_payload(registry: Registry, repo_id: int, seq: int, commit: str, payload: GraphPayload) -> GraphSnapshot:
    """
    #Feature: In-memory snapshot
    #Scenario: Build a snapshot straight from an extraction payload, without the store (sandbox, benchmarks, tests)
    #Complexity: Time O(n + e + h) - payload size
    """
    if registry is None or payload is None:
        raise ValueError("[graph_from_payload] 'registry' and 'payload' are required.")
    nodes = [{**n, "line_start": n["span_lo"], "line_end": n["span_hi"]} for n in payload.nodes]
    return GraphSnapshot.from_rows(registry, repo_id, seq, commit, nodes, payload.edges, payload.holes)


def graph_from_directory(registry: Registry, root: Path, repo_id: int = 1, url: str = "file:///in-memory",
                         commit: str = "WORKTREE", seq: int = 1) -> GraphSnapshot:
    """
    #Feature: In-memory snapshot
    #Scenario: Extract a directory and load it as a snapshot in one step
    #Complexity: Time O(N * r) - extraction cost
    """
    payload = run_extraction(registry, root, repo_id, url, commit).payload
    return graph_from_payload(registry, repo_id, seq, commit, payload)
