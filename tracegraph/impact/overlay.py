import dataclasses
from dataclasses import dataclass, field
from typing import Any

from tracegraph.constants.graph import TIER_HYPOTHESIZED
from tracegraph.engine.graph import EdgeView, GraphSnapshot, NodeView
from tracegraph.errors import Errors
from tracegraph.impact import changespec as cs
from tracegraph.utilities.ids import stable_id


@dataclass(slots=True)
class Overlay:
    """
    #Feature: What-if overlays
    #Scenario: Hypothesized graph plus the ordered ops that produced it and the directly changed seeds
    #Complexity: Time O(1) - constant
    """

    graph: GraphSnapshot
    ops: list[dict[str, Any]] = field(default_factory=list)
    seeds: dict[int, str] = field(default_factory=dict)


def _node_by_key(graph: GraphSnapshot, types: tuple[str, ...], key: str) -> NodeView:
    """
    #Feature: What-if overlays
    #Scenario: Exact natural-key lookup; unresolved targets are returned to the caller, never guessed
    #Complexity: Time O(n) - scan of nodes

    Raises:
        Errors.Domain.ChangeSpec: When no node of the given types has that key.
    """
    matches = [n for n in graph.nodes.values() if n.key == key and any(graph.registry.is_subtype(n.type, t)
                                                                         for t in types)]
    if not matches:
        raise Errors.Domain.ChangeSpec(f"No {'/'.join(types)} with key {key!r} in snapshot {graph.seq}.",
                                       {"key": key, "types": list(types)})
    return matches[0]


def _set_props(overlay: Overlay, node: NodeView, **props: Any) -> None:
    """
    #Feature: What-if overlays
    #Scenario: set_props op: replace the node view with hypothesized props
    #Complexity: Time O(p) - props copied
    """
    overlay.graph.add_node(dataclasses.replace(node, props={**node.props, **props}))
    overlay.ops.append({"op": "set_props", "target_id": node.id, "payload": props})


def _add_member(overlay: Overlay, enum: NodeView, spec: cs.AddEnumMember) -> int:
    """
    #Feature: What-if overlays
    #Scenario: add_node + add_edge ops for a hypothesized EnumMember and its CONTAINS edge
    #Complexity: Time O(1) - constant
    """
    key = f"{enum.key}.{spec.member}"
    node = NodeView(stable_id(overlay.graph.repo_id, "node", "EnumMember", key), "EnumMember", key,
                    {"enum_qname": enum.key, "name": spec.member, "value": spec.value}, TIER_HYPOTHESIZED, enum.file)
    edge = EdgeView(stable_id(overlay.graph.repo_id, "edge", "CONTAINS", enum.id, node.id), "CONTAINS", enum.id,
                    node.id, {}, TIER_HYPOTHESIZED)
    overlay.graph.add_node(node)
    overlay.graph.add_edge(edge)
    overlay.ops += [{"op": "add_node", "target_id": node.id, "payload": {"type": node.type, "key": key}},
                    {"op": "add_edge", "target_id": edge.id, "payload": {"type": "CONTAINS", "src": enum.id,
                                                                         "dst": node.id}}]
    return node.id


_TARGETS: dict[type, tuple[str, tuple[str, ...]]] = {
    cs.MakeColumnNullable: ("column", ("Column",)),
    cs.DropColumn: ("column", ("Column",)),
    cs.AddEnumMember: ("enum", ("Class",)),
    cs.ChangeReturnType: ("function", ("Callable",)),
    cs.ChangeSignature: ("function", ("Callable",)),
    cs.ModifyBody: ("function", ("Callable",)),
    cs.RemoveSymbol: ("symbol", ("Callable", "Class")),
}


def target_of(graph: GraphSnapshot, spec: Any) -> NodeView:
    """
    #Feature: What-if overlays
    #Scenario: The node a ChangeSpec targets, by exact natural key
    #Complexity: Time O(n) - scan of nodes

    Raises:
        Errors.Domain.ChangeSpec: When the target is missing or of the wrong kind.
    """
    field_name, types = _TARGETS[type(spec)]
    node = _node_by_key(graph, types, getattr(spec, field_name))
    if isinstance(spec, cs.AddEnumMember) and not node.props.get("is_enum"):
        raise Errors.Domain.ChangeSpec(f"{spec.enum} is not an Enum class.", {"enum": spec.enum})
    return node


def _apply(overlay: Overlay, spec: Any) -> None:
    """
    #Feature: What-if overlays
    #Scenario: Translate one ChangeSpec into overlay ops (PRD 8.1 "Overlay ops" column)
    #Complexity: Time O(n) - target lookup
    """
    node = target_of(overlay.graph, spec)
    overlay.seeds[node.id] = spec.kind
    if isinstance(spec, cs.MakeColumnNullable):
        _set_props(overlay, node, nullable=True)
    elif isinstance(spec, cs.AddEnumMember):
        overlay.seeds[_add_member(overlay, node, spec)] = spec.kind
    elif isinstance(spec, cs.ChangeReturnType):
        _set_props(overlay, node, return_annotation=spec.new_type,
                   returns_none="some_paths" if "None" in spec.new_type else node.props.get("returns_none"))
    elif isinstance(spec, (cs.DropColumn, cs.RemoveSymbol)):
        overlay.ops.append({"op": "drop_node", "target_id": node.id, "payload": {}})
    else:
        overlay.ops.append({"op": "set_props", "target_id": node.id, "payload": spec.model_dump(mode="json")})


def build_overlay(base: GraphSnapshot, specs: list[Any]) -> Overlay:
    """
    #Feature: What-if overlays
    #Scenario: Apply ChangeSpecs to a copy of the base snapshot. Drops are recorded but applied last, after
               rules have read the base relations they need.
    #Complexity: Time O(n + e + s * n) - clone plus target lookups

    Raises:
        ValueError: When base or specs is missing.
        Errors.Domain.ChangeSpec: When a target cannot be resolved.
    """
    if base is None or not specs:
        raise ValueError("[build_overlay] 'base' and at least one spec are required.")
    overlay = Overlay(base.clone())
    for spec in specs:
        _apply(overlay, spec)
    return overlay


def apply_drops(overlay: Overlay) -> None:
    """
    #Feature: What-if overlays
    #Scenario: Materialise recorded drop_node ops on the overlay graph
    #Complexity: Time O(d * deg) - drops times degree
    """
    for op in overlay.ops:
        if op["op"] == "drop_node":
            overlay.graph.remove_node(op["target_id"])
