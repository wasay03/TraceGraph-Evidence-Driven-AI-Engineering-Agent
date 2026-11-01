import asyncio
import logging
import time

from tracegraph.constants.engine import TRUTH_FALSE, TRUTH_TRUE, TRUTH_UNKNOWN
from tracegraph.errors import Errors
from tracegraph.impact import INVARIANTS, ImpactAnalyzer, build_report, check_all, finding_edge_ids
from tracegraph.engine.answer import node_out
from tracegraph.impact.report import ImpactReport, InvariantChangeOut
from tracegraph.interfaces.repositories.answers import IAnswerRepository
from tracegraph.interfaces.repositories.graph import IGraphRepository
from tracegraph.interfaces.repositories.overlays import IOverlayRepository
from tracegraph.interfaces.services.impact import IImpactService
from tracegraph.interfaces.services.query import IQueryService
from tracegraph.schemas.impact import ImpactRequest, InvariantCheckRequest, InvariantCheckResponse
from tracegraph.services.query_service import query_hash

logger = logging.getLogger(__name__)


class ImpactService(IImpactService):
    """
    #Feature: Impact analysis service (PRD 8)
    #Scenario: Load the base snapshot through the query service, analyze off the event loop, persist overlay and report
    #Complexity: Time per analysis
    """

    def __init__(self, query_service: IQueryService, graph_repository: IGraphRepository,
                 overlay_repository: IOverlayRepository, answer_repository: IAnswerRepository) -> None:
        """
        #Feature: Impact analysis service
        #Scenario: Constructor injection
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a dependency is None.
        """
        deps = (query_service, graph_repository, overlay_repository, answer_repository)
        if any(d is None for d in deps):
            raise ValueError("[ImpactService.__init__] All dependencies are required.")
        self._query, self._graph, self._overlays, self._answers = deps

    async def _evidence(self, repo_id: int, edge_ids: set[int]) -> dict[int, list[dict]]:
        """
        #Feature: Impact analysis service
        #Scenario: Evidence rows for finding witness edges (hypothesized edges have none)
        #Complexity: Time O(k) - edges requested
        """
        if not edge_ids:
            return {}
        grouped: dict[int, list[dict]] = {}
        for row in await self._graph.evidence_for_edges(repo_id, sorted(edge_ids)):
            grouped.setdefault(row["edge_id"], []).append(row)
        return grouped

    async def analyze(self, request: ImpactRequest) -> ImpactReport:
        """
        #Feature: Impact analysis service
        #Scenario: POST /impact
        #Complexity: Time per analysis

        Raises:
            Errors.Domain.ChangeSpec: When a target cannot be resolved.
        """
        if request is None:
            raise ValueError("[ImpactService.analyze] 'request' is required.")
        started = time.perf_counter()
        base = await self._query.load_graph(request.repo_id, request.snapshot_id)
        result = await asyncio.to_thread(ImpactAnalyzer(base).analyze, list(request.changes))
        changes = [c.model_dump(mode="json") for c in request.changes]
        overlay_id = await self._overlays.create(base.repo_id, base.seq, {"changes": changes}, result.overlay.ops)
        result.overlay.graph.overlay_id = overlay_id
        report = build_report(base, result, changes, query_hash({"impact": changes}),
                              await self._evidence(base.repo_id, finding_edge_ids(result)))
        report.latency_ms = int((time.perf_counter() - started) * 1000)
        report.handle = await self._answers.insert(report.model_dump(mode="json"), {"impact": changes}, "hypothesized")
        logger.info("Impact analyzed", extra={"repo_id": base.repo_id, "snapshot_seq": base.seq,
                                              "answer_handle": report.handle, **report.summary})
        return report

    async def get_report(self, handle: str) -> ImpactReport:
        """
        #Feature: Impact analysis service
        #Scenario: GET /impact/{handle}
        #Complexity: Time O(1) - unique index lookup

        Raises:
            Errors.HTTP.NotFound: When the handle is not an impact report.
        """
        row = await self._answers.get(handle)
        if "impact" not in row["query_ir"]:
            raise Errors.HTTP.NotFound(f"{handle} is not an impact report.", {"handle": handle})
        return ImpactReport(**row["result"])

    async def check_invariants(self, request: InvariantCheckRequest) -> InvariantCheckResponse:
        """
        #Feature: Impact analysis service
        #Scenario: POST /invariants/check
        #Complexity: Time cost of the selected invariants

        Raises:
            Errors.HTTP.BadRequest: When an invariant id is unknown.
        """
        unknown = set(request.invariants) - set(INVARIANTS)
        if unknown:
            raise Errors.HTTP.BadRequest(f"Unknown invariants {sorted(unknown)}.", {"known": sorted(INVARIANTS)})
        graph = await self._query.load_graph(request.repo_id, request.snapshot_id)
        violations = await asyncio.to_thread(check_all, graph, request.invariants or None)
        truth = (TRUTH_FALSE if any(v.truth == TRUTH_TRUE for v in violations)
                 else TRUTH_UNKNOWN if violations else TRUTH_TRUE)
        rendered = [InvariantChangeOut(invariant=v.invariant, severity=v.severity, status="present", truth=v.truth,
                                       node=node_out(graph, v.node), message=v.message) for v in violations]
        return InvariantCheckResponse(snapshot_seq=graph.seq, truth=truth,
                                      checked=request.invariants or sorted(INVARIANTS), violations=rendered)
