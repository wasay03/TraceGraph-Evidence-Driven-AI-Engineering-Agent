from functools import cached_property
from typing import Any

from tracegraph.errors import Errors
from tracegraph.ontology.specs import EdgeTypeSpec, NodeTypeSpec, PropSpec


class Registry:
    """
    #Feature: Ontology registry
    #Scenario: Closed, pre-registered set of node and edge types; the write path validates against it
    #Complexity: Time O(1) per lookup after registration

    Type ids are assigned in declaration order and must stay append-only across versions.
    """

    def __init__(self, semver: str) -> None:
        """
        #Feature: Ontology registry
        #Scenario: Create an empty registry for one ontology version
        #Complexity: Time O(1) - constant

        Args:
            semver: Ontology version, bumped on every registry change.

        Raises:
            ValueError: When semver is empty.
        """
        if not semver:
            raise ValueError("[Registry.__init__] 'semver' is required and must be non-empty.")
        self.semver = semver
        self._nodes: dict[str, NodeTypeSpec] = {}
        self._edges: dict[str, EdgeTypeSpec] = {}

    # ---- registration -------------------------------------------------------------------

    def node(self, name: str, parent: str | None = None, **kwargs: Any) -> NodeTypeSpec:
        """
        #Feature: Ontology registry
        #Scenario: Register a node type; its parent must already be registered
        #Complexity: Time O(1) - constant

        Args:
            name: Type name, e.g. Function.
            parent: Parent type name (single inheritance).
            **kwargs: Remaining NodeTypeSpec fields (abstract, key, props, tiers, owner).

        Returns:
            The registered spec.

        Raises:
            ValueError: On duplicate name or unknown parent.
        """
        if name in self._nodes:
            raise ValueError(f"[Registry.node] Node type {name!r} registered twice. Fix: remove the duplicate.")
        if parent is not None and parent not in self._nodes:
            raise ValueError(f"[Registry.node] Parent {parent!r} of {name!r} is not registered. Fix: register it first.")
        spec = NodeTypeSpec(id=len(self._nodes) + 1, name=name, parent=parent, **kwargs)
        self._nodes[name] = spec
        return spec

    def edge(self, name: str, signatures: list[tuple[str, str]], **kwargs: Any) -> EdgeTypeSpec:
        """
        #Feature: Ontology registry
        #Scenario: Register an edge type with its permitted (domain, range) pairs
        #Complexity: Time O(s) - linear in signatures

        Args:
            name: Edge name, e.g. CALLS.
            signatures: Permitted (domain type, range type) pairs; subtypes are implied.
            **kwargs: Remaining EdgeTypeSpec fields.

        Returns:
            The registered spec.

        Raises:
            ValueError: On duplicate name or an unregistered endpoint type.
        """
        if name in self._edges:
            raise ValueError(f"[Registry.edge] Edge type {name!r} registered twice. Fix: remove the duplicate.")
        unknown = {t for pair in signatures for t in pair if t not in self._nodes}
        if unknown:
            raise ValueError(f"[Registry.edge] {name!r} references unregistered node types {sorted(unknown)}.")
        spec = EdgeTypeSpec(id=len(self._edges) + 1, name=name, signatures=tuple(signatures), **kwargs)
        self._edges[name] = spec
        return spec

    # ---- lookup -------------------------------------------------------------------------

    @property
    def node_types(self) -> list[NodeTypeSpec]:
        """
        #Feature: Ontology registry
        #Scenario: All node types in id order
        #Complexity: Time O(n) - linear in node types
        """
        return list(self._nodes.values())

    @property
    def edge_types(self) -> list[EdgeTypeSpec]:
        """
        #Feature: Ontology registry
        #Scenario: All edge types in id order
        #Complexity: Time O(e) - linear in edge types
        """
        return list(self._edges.values())

    def node_type(self, name: str) -> NodeTypeSpec:
        """
        #Feature: Ontology registry
        #Scenario: Look up a node type by name
        #Complexity: Time O(1) - constant

        Raises:
            Errors.Domain.UnknownType: When the name is not registered.
        """
        spec = self._nodes.get(name)
        if spec is None:
            raise Errors.Domain.UnknownType(f"Node type {name!r} is not registered.", {"type": name})
        return spec

    def edge_type(self, name: str) -> EdgeTypeSpec:
        """
        #Feature: Ontology registry
        #Scenario: Look up an edge type by name
        #Complexity: Time O(1) - constant

        Raises:
            Errors.Domain.UnknownType: When the name is not registered.
        """
        spec = self._edges.get(name)
        if spec is None:
            raise Errors.Domain.UnknownType(f"Edge type {name!r} is not registered.", {"type": name})
        return spec

    def has_node_type(self, name: str) -> bool:
        """
        #Feature: Ontology registry
        #Scenario: Membership test without raising
        #Complexity: Time O(1) - constant
        """
        return name in self._nodes

    def has_edge_type(self, name: str) -> bool:
        """
        #Feature: Ontology registry
        #Scenario: Membership test without raising
        #Complexity: Time O(1) - constant
        """
        return name in self._edges

    @cached_property
    def node_type_by_id(self) -> dict[int, NodeTypeSpec]:
        """
        #Feature: Ontology registry
        #Scenario: Reverse index from catalog id to node type
        #Complexity: Time O(n) once, then O(1)
        """
        return {spec.id: spec for spec in self._nodes.values()}

    @cached_property
    def edge_type_by_id(self) -> dict[int, EdgeTypeSpec]:
        """
        #Feature: Ontology registry
        #Scenario: Reverse index from catalog id to edge type
        #Complexity: Time O(e) once, then O(1)
        """
        return {spec.id: spec for spec in self._edges.values()}

    # ---- hierarchy ----------------------------------------------------------------------

    def ancestors(self, name: str) -> tuple[str, ...]:
        """
        #Feature: Ontology registry
        #Scenario: Type itself followed by its ancestors up to the root
        #Complexity: Time O(d) - linear in hierarchy depth

        Raises:
            Errors.Domain.UnknownType: When the name is not registered.
        """
        chain = [name]
        parent = self.node_type(name).parent
        while parent is not None:
            chain.append(parent)
            parent = self._nodes[parent].parent
        return tuple(chain)

    def is_subtype(self, name: str, ancestor: str) -> bool:
        """
        #Feature: Ontology registry
        #Scenario: True when name equals ancestor or inherits from it
        #Complexity: Time O(d) - linear in hierarchy depth
        """
        return ancestor in self.ancestors(name)

    def subtypes(self, name: str) -> frozenset[str]:
        """
        #Feature: Ontology registry
        #Scenario: Type itself plus every registered descendant (hierarchy-aware Select)
        #Complexity: Time O(n * d) - node types times depth
        """
        self.node_type(name)
        return frozenset(t for t in self._nodes if self.is_subtype(t, name))

    def node_props(self, name: str) -> dict[str, PropSpec]:
        """
        #Feature: Ontology registry
        #Scenario: Effective properties of a node type including inherited ones
        #Complexity: Time O(d * p) - depth times props per level
        """
        merged: dict[str, PropSpec] = {}
        for type_name in reversed(self.ancestors(name)):
            merged.update(self._nodes[type_name].props)
        return merged

    def edge_permits(self, edge: str, src_type: str, dst_type: str) -> bool:
        """
        #Feature: Ontology registry
        #Scenario: Whether (src_type, dst_type) satisfies any signature of the edge type
        #Complexity: Time O(s * d) - signatures times depth
        """
        src_chain, dst_chain = self.ancestors(src_type), self.ancestors(dst_type)
        return any(d in src_chain and r in dst_chain for d, r in self.edge_type(edge).signatures)
