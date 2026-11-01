import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tracegraph.constants.extract import EXTRACTOR_VERSIONS
from tracegraph.extract.builder import GraphBuilder, GraphPayload
from tracegraph.extract.context import AnalysisContext
from tracegraph.extract.index import ProgramIndex
from tracegraph.extract.passes.resolve import ResolvePass
from tracegraph.extract.passes.structure import StructurePass
from tracegraph.extract.records import NodeRecord
from tracegraph.extract.source import discover_sources
from tracegraph.ontology import Registry

logger = logging.getLogger(__name__)

PassRunner = Callable[[AnalysisContext], None]


@dataclass(slots=True)
class ModuleFingerprint:
    """
    #Feature: Incremental indexing
    #Scenario: Content and public-signature hashes of one module file
    #Complexity: Time O(1) - constant
    """

    content_hash: str
    signature_hash: str


@dataclass(slots=True)
class ExtractionResult:
    """
    #Feature: Extraction pipeline
    #Scenario: Validated payload plus the per-file fingerprints and import graph used for incremental scope
    #Complexity: Time O(1) - constant
    """

    payload: GraphPayload
    modules: dict[str, ModuleFingerprint] = field(default_factory=dict)
    importers: dict[str, set[str]] = field(default_factory=dict)
    timings_ms: dict[str, float] = field(default_factory=dict)


def _resolve_pass(ctx: AnalysisContext) -> None:
    """
    #Feature: Extraction pipeline
    #Scenario: Adapter running the resolution pass
    #Complexity: Time O(N * r) - see ResolvePass
    """
    ResolvePass(ctx).run()


DEFAULT_PASSES: list[tuple[str, PassRunner]] = [("resolve", _resolve_pass)]


def _importers(ctx: AnalysisContext) -> dict[str, set[str]]:
    """
    #Feature: Incremental indexing
    #Scenario: Map file -> files that import something defined in it
    #Complexity: Time O(a * d) - import aliases times module depth
    """
    index, out = ctx.index, {}
    for module in index.modules.values():
        for target in module.imports.values():
            canonical = ctx.resolver.canonical(target).split(".")
            owner = next((index.modules[".".join(canonical[:i])] for i in range(len(canonical), 0, -1)
                          if ".".join(canonical[:i]) in index.modules), None)
            if owner is not None and owner.path != module.path:
                out.setdefault(owner.path, set()).add(module.path)
    return out


def run_extraction(
    registry: Registry,
    root: Path,
    repo_id: int,
    repo_url: str,
    commit_sha: str,
    passes: list[tuple[str, PassRunner]] | None = None,
) -> ExtractionResult:
    """
    #Feature: Extraction pipeline (PRD 5.1)
    #Scenario: Snapshot -> structure -> later passes -> registry validation; deterministic for a commit
    #Complexity: Time O(N * r) - AST nodes times resolution cost

    Args:
        registry: Ontology registry to validate against.
        root: Checked-out commit.
        repo_id: Repository id (part of every stable id).
        repo_url: Repository URL for the Repository node.
        commit_sha: Commit stamped on evidence.
        passes: Passes after structure, in order; defaults to DEFAULT_PASSES.

    Returns:
        ExtractionResult.

    Raises:
        Errors.Domain.*: When the batch violates the registry.
    """
    timings: dict[str, float] = {}
    started = time.perf_counter()
    sources = discover_sources(root)
    builder = GraphBuilder(registry, repo_id, commit_sha, EXTRACTOR_VERSIONS)
    builder.add_node(NodeRecord("Repository", {"url": repo_url, "name": Path(root).name}))
    index = ProgramIndex()
    StructurePass(builder, index).run(sources)
    timings["structure"] = round((time.perf_counter() - started) * 1000, 1)
    ctx = AnalysisContext.create(builder, index)
    for name, runner in passes if passes is not None else DEFAULT_PASSES:
        mark = time.perf_counter()
        runner(ctx)
        timings[name] = round((time.perf_counter() - mark) * 1000, 1)
    payload = builder.finalize()
    fingerprints = {r.file_path: ModuleFingerprint(r.props["content_hash"], r.props["signature_hash"])
                    for r in (builder.node_record(ref) for ref in builder.refs_of_type("Module"))}
    timings["total"] = round((time.perf_counter() - started) * 1000, 1)
    logger.info("Extraction done", extra={"repo_id": repo_id, "commit": commit_sha, **payload.stats, **timings})
    return ExtractionResult(payload, fingerprints, _importers(ctx), timings)
