from collections.abc import Callable
from dataclasses import dataclass

from tracegraph.constants.engine import TRUTH_TRUE, TRUTH_UNKNOWN
from tracegraph.constants.graph import TIER_RANK
from tracegraph.constants.impact import PROPAGATION_MAX_HOPS
from tracegraph.engine import ir
from tracegraph.engine.evaluator import Derivation, Evaluator
from tracegraph.engine.graph import GraphSnapshot
from tracegraph.engine.rpq import compile_rpq

_ANY = TIER_RANK["hypothesized"]


@dataclass(frozen=True, slots=True)
class Violation:
    """
    #Feature: Invariant packs (PRD 8.3)
    #Scenario: One counterexample; truth TRUE means a definite violation, UNKNOWN means coverage holes intervene
    #Complexity: Time O(1) - constant
    """

    invariant: str
    severity: str
    node: int
    message: str
    truth: str = TRUTH_TRUE


def _reach(graph: GraphSnapshot, node: int, rpq: str, types: list[str]):
    """
    #Feature: Invariant packs
    #Scenario: Product BFS from one node
    #Complexity: Time O((n + e) * q)
    """
    return Evaluator(graph).walk({node: Derivation()}, compile_rpq(rpq, graph.registry), PROPAGATION_MAX_HOPS,
                                 "hypothesized", types)


def inv_002_tested_writing_endpoints(graph: GraphSnapshot) -> list[Violation]:
    """
    #Feature: Invariant packs
    #Scenario: INV-002 every Endpoint that writes data has at least one test reaching its handler
    #Complexity: Time O(|endpoints| * (n + e))
    """
    out = []
    for ep in graph.of_type("Endpoint"):
        if not _reach(graph, ep.id, "HANDLED_BY . (CALLS|INJECTS)* . WRITES_TO", ["DataObject"]).reached:
            continue
        walk = _reach(graph, ep.id, "HANDLED_BY . CALLED_BY* . TESTED_BY", ["Test"])
        if not walk.reached:
            truth = TRUTH_UNKNOWN if any(graph.holes.get(n) for n in walk.visited) else TRUTH_TRUE
            out.append(Violation("INV-002", "warn", ep.id, f"{ep.key} writes data but no test reaches it", truth))
    return out


def inv_003_tenant_filter(graph: GraphSnapshot) -> list[Violation]:
    """
    #Feature: Invariant packs
    #Scenario: INV-003 every non-insert QuerySite on a table with tenant_id filters on tenant_id
    #Complexity: Time O(|sites| * deg)
    """
    out = []
    for table in graph.of_type("Table"):
        tenant = next((c for c, _ in graph.neighbors(table.id, ("HAS_COLUMN", "fwd"), _ANY)
                       if graph.nodes[c].props.get("name") == "tenant_id"), None)
        if tenant is None:
            continue
        for kind in ("READS_FROM", "WRITES_TO"):
            for site, edge in graph.neighbors(table.id, (kind, "rev"), _ANY):
                node = graph.nodes[site]
                filters = {d for d, _ in graph.neighbors(site, ("FILTERS_ON", "fwd"), _ANY)}
                if node.type == "QuerySite" and node.props.get("op") != "insert" and tenant not in filters:
                    truth = TRUTH_UNKNOWN if node.props.get("is_dynamic") else TRUTH_TRUE
                    out.append(Violation("INV-003", "error", site, f"{node.key} on {table.key} without tenant_id", truth))
    return out


def inv_004_nullability_drift(graph: GraphSnapshot) -> list[Violation]:
    """
    #Feature: Invariant packs
    #Scenario: INV-004 ORM nullability matches database nullability for every mapped column
    #Complexity: Time O(|columns|)
    """
    out = []
    for col in graph.of_type("Column"):
        p = col.props
        if p.get("in_orm") and p.get("in_db") and p.get("db_nullable") is not None and p.get("nullable") != p.get("db_nullable"):
            out.append(Violation("INV-004", "error", col.id,
                                 f"{col.key}: ORM nullable={p.get('nullable')} but database nullable={p.get('db_nullable')}"))
        elif p.get("in_orm") and p.get("in_db") is False:
            out.append(Violation("INV-004", "error", col.id, f"{col.key} is mapped but absent from migrations"))
    return out


def _enum_members(graph: GraphSnapshot) -> dict[str, set[str]]:
    """
    #Feature: Invariant packs
    #Scenario: Member names per enum, including hypothesized members of an overlay
    #Complexity: Time O(n) - scan of nodes
    """
    members: dict[str, set[str]] = {}
    for node in graph.of_type("EnumMember"):
        members.setdefault(node.props.get("enum_qname"), set()).add(node.props.get("name"))
    return members


def inv_005_exhaustive_enum_branches(graph: GraphSnapshot) -> list[Violation]:
    """
    #Feature: Invariant packs
    #Scenario: INV-005 BRANCHES_ON over an Enum covers all members or has a default branch
    #Complexity: Time O(n + |branch edges|)
    """
    members, out, seen = _enum_members(graph), [], set()
    for edge in (e for edges in graph.fwd.get("BRANCHES_ON", {}).values() for e in edges):
        target = graph.nodes[edge.dst]
        enum = target.props.get("enum_qname")
        if target.type != "EnumMember" or edge.props.get("has_default") or (edge.src, enum) in seen:
            continue
        missing = members.get(enum, set()) - set(edge.props.get("compared_values", []))
        if missing:
            seen.add((edge.src, enum))
            out.append(Violation("INV-005", "warn", edge.src,
                                 f"{graph.nodes[edge.src].key} misses {sorted(missing)} of {enum} without a default"))
    return out


def inv_006_exceptions_handled(graph: GraphSnapshot) -> list[Violation]:
    """
    #Feature: Invariant packs
    #Scenario: INV-006 exceptions raised below an Endpoint are caught on the way up
    #Complexity: Time O(|endpoints| * (n + e))
    """
    out = []
    for ep in graph.of_type("Endpoint"):
        region = _reach(graph, ep.id, "HANDLED_BY . CALLS*", ["Callable"])
        callables = set(region.reached)
        caught = {c for fn in callables for c, _ in graph.neighbors(fn, ("CATCHES", "fwd"), _ANY)}
        for fn in callables:
            for exc, _ in graph.neighbors(fn, ("RAISES", "fwd"), _ANY):
                ancestors = {exc} | {a for a, _ in graph.neighbors(exc, ("INHERITS", "fwd"), _ANY)}
                if not ancestors & caught:
                    out.append(Violation("INV-006", "warn", fn, f"{graph.nodes[exc].key} raised under {ep.key} "
                                         "is not caught"))
    return out


def inv_007_layering(graph: GraphSnapshot, source: str = "app.api", forbidden: str = "app.db") -> list[Violation]:
    """
    #Feature: Invariant packs
    #Scenario: INV-007 modules under app.api do not import from app.db directly
    #Complexity: Time O(|imports|)
    """
    out = []
    for module in graph.of_type("Module"):
        if not (module.key == source or module.key.startswith(source + ".")):
            continue
        for target, _ in graph.neighbors(module.id, ("IMPORTS", "fwd"), _ANY):
            key = graph.nodes[target].key
            if key == forbidden or key.startswith(forbidden + "."):
                out.append(Violation("INV-007", "warn", module.id, f"{module.key} imports {key}"))
    return out


def inv_008_import_cycles(graph: GraphSnapshot) -> list[Violation]:
    """
    #Feature: Invariant packs
    #Scenario: INV-008 no import cycles inside a top-level package
    #Complexity: Time O(n + e) - SCC
    """
    result = Evaluator(graph).evaluate(ir.SCC(input=ir.Select(type="Module"), edge="IMPORTS"))
    out = []
    for row in result.rows or []:
        keys = [graph.nodes[n].key for n in row["nodes"]]
        if len({k.split(".")[0] for k in keys}) == 1:
            out.append(Violation("INV-008", "warn", row["nodes"][0], f"import cycle: {' -> '.join(keys)}"))
    return out


INVARIANTS: dict[str, Callable[[GraphSnapshot], list[Violation]]] = {
    "INV-002": inv_002_tested_writing_endpoints,
    "INV-003": inv_003_tenant_filter,
    "INV-004": inv_004_nullability_drift,
    "INV-005": inv_005_exhaustive_enum_branches,
    "INV-006": inv_006_exceptions_handled,
    "INV-007": inv_007_layering,
    "INV-008": inv_008_import_cycles,
}


def check_all(graph: GraphSnapshot, ids: list[str] | None = None) -> list[Violation]:
    """
    #Feature: Invariant packs
    #Scenario: Run the selected (default all) invariants
    #Complexity: Time sum of the checks

    Raises:
        ValueError: When graph is None or an id is unknown.
    """
    if graph is None:
        raise ValueError("[check_all] 'graph' is required.")
    unknown = set(ids or []) - set(INVARIANTS)
    if unknown:
        raise ValueError(f"[check_all] Unknown invariants {sorted(unknown)}. Fix: use one of {sorted(INVARIANTS)}.")
    return [v for inv in (ids or list(INVARIANTS)) for v in INVARIANTS[inv](graph)]
