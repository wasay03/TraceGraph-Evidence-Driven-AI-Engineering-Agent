from tracegraph.extract.builder import GraphPayload
from tracegraph.extract.pipeline import ModuleFingerprint


def dirty_scope(
    previous: dict[str, ModuleFingerprint],
    current: dict[str, ModuleFingerprint],
    importers: dict[str, set[str]],
) -> list[str]:
    """
    #Feature: Incremental indexing (PRD 5.4 steps 1-2)
    #Scenario: Changed + deleted files, plus importers of files whose public signature changed
    #Complexity: Time O(f + i) - files plus importer links

    Args:
        previous: Fingerprints at the base snapshot, keyed by file path.
        current: Fingerprints of this extraction.
        importers: File -> files importing from it.

    Returns:
        Sorted list of file paths whose owned rows are re-committed.

    Raises:
        ValueError: When an argument is None.
    """
    if previous is None or current is None or importers is None:
        raise ValueError("[dirty_scope] 'previous', 'current' and 'importers' are required.")
    changed = {p for p, fp in current.items() if p not in previous or previous[p].content_hash != fp.content_hash}
    deleted = set(previous) - set(current)
    signature_changed = deleted | {p for p in changed if p not in previous
                                   or previous[p].signature_hash != current[p].signature_hash}
    dependents = {imp for p in signature_changed for imp in importers.get(p, ())}
    return sorted(changed | deleted | dependents)


def filter_payload(payload: GraphPayload, scope: list[str]) -> GraphPayload:
    """
    #Feature: Incremental indexing
    #Scenario: Keep only rows owned by files in scope (and file-less rows such as packages and type expressions)
    #Complexity: Time O(n + e + v) - linear in payload

    Args:
        payload: Full validated payload.
        scope: Files whose rows are re-committed.

    Returns:
        New GraphPayload restricted to the scope.

    Raises:
        ValueError: When an argument is None.
    """
    if payload is None or scope is None:
        raise ValueError("[filter_payload] 'payload' and 'scope' are required.")
    files = set(scope)
    nodes = [n for n in payload.nodes if n["file_path"] is None or n["file_path"] in files]
    edges = [e for e in payload.edges if e["owner_file"] is None or e["owner_file"] in files]
    kept = {e["id"] for e in edges}
    links = [link for link in payload.links if link["edge_id"] in kept]
    evidence_ids = {link["evidence_id"] for link in links}
    evidence = [ev for ev in payload.evidence if ev["id"] in evidence_ids]
    holes = [h for h in payload.holes if h["file_path"] in files]
    stats = {**payload.stats, "scope_files": len(files)}
    return GraphPayload(nodes=nodes, edges=edges, evidence=evidence, links=links, holes=holes, stats=stats)
