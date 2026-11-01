from collections.abc import Callable
from typing import Any

from tracegraph.constants import impact as c
from tracegraph.constants.graph import TIER_ASSERTED, TIER_RANK
from tracegraph.engine.evaluator import Derivation
from tracegraph.engine.graph import EdgeView, GraphSnapshot, NodeView
from tracegraph.impact import changespec as cs
from tracegraph.impact.findings import Finding, Obligation

_ANY_TIER = TIER_RANK["hypothesized"]
RuleOutput = tuple[list[Finding], list[Obligation]]


def _in(g: GraphSnapshot, node: int, edge_type: str) -> list[tuple[int, EdgeView]]:
    """
    #Feature: Impact rule packs
    #Scenario: Sources of incoming edges of one type
    #Complexity: Time O(deg) - in-degree
    """
    return list(g.neighbors(node, (edge_type, "rev"), _ANY_TIER))


def _out(g: GraphSnapshot, node: int, edge_type: str) -> list[tuple[int, EdgeView]]:
    """
    #Feature: Impact rule packs
    #Scenario: Targets of outgoing edges of one type
    #Complexity: Time O(deg) - out-degree
    """
    return list(g.neighbors(node, (edge_type, "fwd"), _ANY_TIER))


def _finding(node: int, cls: str, reason: str, spec: Any, edges: list[EdgeView], rule: str) -> Finding:
    """
    #Feature: Impact rule packs
    #Scenario: Finding with a derivation over the given witness edges
    #Complexity: Time O(p) - path length
    """
    deriv = Derivation()
    for edge in edges:
        deriv = deriv.extend(edge)
    return Finding(node, cls, reason, spec.kind, rule, deriv, distance=max(1, len(edges) - 1))


def _readers(g: GraphSnapshot, target: int, kinds: tuple[str, ...]) -> list[tuple[int, list[EdgeView]]]:
    """
    #Feature: Impact rule packs
    #Scenario: Callables accessing a column/table directly or through a QuerySite they execute
    #Complexity: Time O(deg^2) - two hops
    """
    out = []
    for kind in kinds:
        for src, edge in _in(g, target, kind):
            if g.nodes[src].type == "QuerySite":
                out += [(fn, [edge, ex]) for fn, ex in _in(g, src, "EXECUTES")]
                out.append((src, [edge]))
            else:
                out.append((src, [edge]))
    return out


def make_column_nullable(g: GraphSnapshot, spec: cs.MakeColumnNullable, column: NodeView) -> RuleOutput:
    """
    #Feature: Impact rule packs (PRD 8.2 example pack)
    #Scenario: breaks <- ASSUMES_NOT_NULL (asserted) on a mapped attribute; guarded <- BRANCHES_ON with None;
               at_risk <- other readers of the column or attribute
    #Complexity: Time O(deg^2) - neighbourhood of the column
    """
    findings: list[Finding] = []
    attrs = _in(g, column.id, "MAPS_TO")
    for attr, map_edge in attrs:
        guarded = {fn for fn, e in _in(g, attr, "BRANCHES_ON") if "None" in e.props.get("compared_values", [])}
        for fn, edge in _in(g, attr, "ASSUMES_NOT_NULL"):
            if fn in guarded:
                findings.append(_finding(fn, c.GUARDED, "branches_on_none", spec, [map_edge, edge], "nullable.guarded"))
            elif edge.tier == TIER_ASSERTED:
                findings.append(_finding(fn, c.BREAKS, "assumes_not_null", spec, [map_edge, edge], "nullable.breaks"))
        for fn, edge in _in(g, attr, "READS_ATTR"):
            findings.append(_finding(fn, c.AT_RISK, "reads_attribute", spec, [map_edge, edge], "nullable.at_risk"))
    for fn, edges in _readers(g, column.id, ("READS_FROM", "FILTERS_ON")):
        findings.append(_finding(fn, c.AT_RISK, "reads_column", spec, edges, "nullable.at_risk"))
    obligations = [Obligation(c.OBLIGATION_MIGRATION_ALTER_NULLABLE, column.id,
                              f"op.alter_column('{column.props.get('table')}', '{column.props.get('name')}', nullable=True)")]
    obligations += [Obligation(c.OBLIGATION_ORM_OPTIONAL, attr, "annotate the mapped attribute as Optional")
                    for attr, _ in attrs]
    return findings, obligations


def drop_column(g: GraphSnapshot, spec: cs.DropColumn, column: NodeView) -> RuleOutput:
    """
    #Feature: Impact rule packs
    #Scenario: Every read, write, filter and mapped-attribute use of the column breaks
    #Complexity: Time O(deg^2) - neighbourhood of the column
    """
    findings = [_finding(fn, c.BREAKS, "uses_dropped_column", spec, edges, "drop_column.breaks")
                for fn, edges in _readers(g, column.id, ("READS_FROM", "WRITES_TO", "FILTERS_ON"))]
    obligations = [Obligation(c.OBLIGATION_MIGRATION_DROP_COLUMN, column.id,
                              f"op.drop_column('{column.props.get('table')}', '{column.props.get('name')}')")]
    for attr, map_edge in _in(g, column.id, "MAPS_TO"):
        obligations.append(Obligation(c.OBLIGATION_REMOVE_MAPPED_ATTRIBUTE, attr, "remove the mapped attribute"))
        for kind in ("READS_ATTR", "WRITES_ATTR", "ASSUMES_NOT_NULL", "BRANCHES_ON", "VALIDATES"):
            findings += [_finding(fn, c.BREAKS, "uses_dropped_attribute", spec, [map_edge, e], "drop_column.breaks")
                         for fn, e in _in(g, attr, kind)]
    return findings, obligations


def add_enum_member(g: GraphSnapshot, spec: cs.AddEnumMember, enum: NodeView) -> RuleOutput:
    """
    #Feature: Impact rule packs
    #Scenario: Branches enumerating members without a default break; with a default they are guarded;
               a native ENUM column needs a migration
    #Complexity: Time O(m * deg) - members times branch sites
    """
    findings: dict[int, Finding] = {}
    for member, contains in _out(g, enum.id, "CONTAINS"):
        if g.nodes[member].type != "EnumMember" or g.nodes[member].tier != TIER_ASSERTED:
            continue
        for fn, edge in _in(g, member, "BRANCHES_ON"):
            cls, reason = (c.GUARDED, "default_branch") if edge.props.get("has_default") else (c.BREAKS, "non_exhaustive")
            findings.setdefault(fn, _finding(fn, cls, reason, spec, [contains, edge], f"enum.{reason}"))
    obligations = [Obligation(c.OBLIGATION_TEST_NEW_BRANCH, enum.id, f"cover {enum.key}.{spec.member} in tests")]
    short = enum.key.rsplit(".", 1)[-1]
    for node in g.of_type("Attribute"):
        if short in (node.props.get("annotation") or ""):
            for column, _ in _out(g, node.id, "MAPS_TO"):
                if g.nodes[column].props.get("sql_type") == "ENUM":
                    obligations.append(Obligation(c.OBLIGATION_MIGRATION_ENUM_TYPE, column,
                                                  f"add '{spec.value or spec.member}' to the database enum type"))
    return list(findings.values()), obligations


def change_return_type(g: GraphSnapshot, spec: cs.ChangeReturnType, fn: NodeView) -> RuleOutput:
    """
    #Feature: Impact rule packs
    #Scenario: Becoming Optional breaks callers that use the result unguarded; guarded callers are GUARDED;
               returned results and other type changes are AT_RISK; dispatch candidates are UNKNOWN
    #Complexity: Time O(deg) - callers
    """
    to_optional = "None" in spec.new_type and fn.props.get("returns_none") in (None, "never", "unknown")
    findings = []
    for caller, edge in _in(g, fn.id, "CALLS"):
        use = edge.props.get("result_use")
        if use == "unused":
            continue
        if edge.props.get("resolution") == "dispatch_candidate":
            cls, reason = c.UNKNOWN, "dispatch_candidate"
        elif use == "guarded":
            cls, reason = c.GUARDED, "result_guarded"
        elif use == "unguarded" and to_optional:
            cls, reason = c.BREAKS, "result_used_without_none_guard"
        else:
            cls, reason = c.AT_RISK, f"result_{use or 'used'}"
        findings.append(_finding(caller, cls, reason, spec, [edge], f"return_type.{cls.lower()}"))
    obligations = [Obligation(c.OBLIGATION_UPDATE_ANNOTATION, fn.id, f"-> {spec.new_type}")]
    obligations += [Obligation(c.OBLIGATION_RESPONSE_MODEL, ep, "handler return type changed")
                    for ep, _ in _in(g, fn.id, "HANDLED_BY")]
    return findings, obligations


def _signature_breaks(edge: EdgeView, params: list[NodeView], spec: cs.ChangeSignature, offset: int) -> str | None:
    """
    #Feature: Impact rule packs
    #Scenario: Reason a call site no longer binds after the signature change, or None if it still binds
    #Complexity: Time O(p) - parameters
    """
    kwargs, n_args = set(edge.props.get("kwargs", [])), edge.props.get("n_args", 0) + offset
    if kwargs & (set(spec.remove) | set(spec.rename)):
        return "keyword_argument_removed"
    kept = [p for p in params if p.props.get("name") not in spec.remove]
    positional = [p for p in kept if p.props.get("kind") in ("positional_only", "positional_or_keyword")]
    if n_args > len(positional) and not any(p.props.get("kind") == "var_positional" for p in kept):
        return "too_many_positional_arguments"
    if any(not a.has_default and a.name not in kwargs for a in spec.add):
        return "missing_required_argument"
    return None


def change_signature(g: GraphSnapshot, spec: cs.ChangeSignature, fn: NodeView) -> RuleOutput:
    """
    #Feature: Impact rule packs
    #Scenario: Call sites whose positional/keyword arguments no longer bind break; *args/**kwargs sites are UNKNOWN
    #Complexity: Time O(deg * p) - callers times parameters
    """
    params = sorted((g.nodes[p] for p, _ in _out(g, fn.id, "HAS_PARAM")), key=lambda n: n.props.get("position", 0))
    offset = 1 if fn.type == "Method" and fn.props.get("kind") in ("instance", "class") else 0
    findings = []
    for caller, edge in _in(g, fn.id, "CALLS"):
        if edge.props.get("has_star"):
            findings.append(_finding(caller, c.UNKNOWN, "star_arguments", spec, [edge], "signature.unknown"))
            continue
        reason = _signature_breaks(edge, params, spec, offset)
        cls = c.BREAKS if reason else c.GUARDED
        findings.append(_finding(caller, cls, reason or "still_binds", spec, [edge], f"signature.{cls.lower()}"))
    breaks = [f for f in findings if f.cls == c.BREAKS]
    obligations = [Obligation(c.OBLIGATION_UPDATE_CALL_SITES, fn.id, f"{len(breaks)} call sites")] if breaks else []
    return findings, obligations


def remove_symbol(g: GraphSnapshot, spec: cs.RemoveSymbol, node: NodeView) -> RuleOutput:
    """
    #Feature: Impact rule packs
    #Scenario: Every incoming edge to the symbol (or to members of a removed class) becomes a break
    #Complexity: Time O(deg) - incoming edges of the symbol and its members
    """
    targets = [node.id] + [m for m, _ in _out(g, node.id, "CONTAINS")]
    findings = []
    for target in targets:
        for edge_type, adjacency in g.rev.items():
            if edge_type in c.REMOVAL_IGNORED_EDGES:
                continue
            for edge in adjacency.get(target, []):
                if edge.src not in targets:
                    findings.append(_finding(edge.src, c.BREAKS, f"{edge_type.lower()}_target_removed", spec, [edge],
                                             "remove.breaks"))
    return findings, []


def modify_body(g: GraphSnapshot, spec: cs.ModifyBody, fn: NodeView) -> RuleOutput:
    """
    #Feature: Impact rule packs
    #Scenario: Generic fallback: direct callers are AT_RISK, no BREAKS claims
    #Complexity: Time O(deg) - callers
    """
    return [_finding(caller, c.AT_RISK, "callee_modified", spec, [edge], "modify.at_risk")
            for caller, edge in _in(g, fn.id, "CALLS")], []


RULE_PACKS: dict[type, Callable[..., RuleOutput]] = {
    cs.MakeColumnNullable: make_column_nullable,
    cs.DropColumn: drop_column,
    cs.AddEnumMember: add_enum_member,
    cs.ChangeReturnType: change_return_type,
    cs.ChangeSignature: change_signature,
    cs.RemoveSymbol: remove_symbol,
    cs.ModifyBody: modify_body,
}
