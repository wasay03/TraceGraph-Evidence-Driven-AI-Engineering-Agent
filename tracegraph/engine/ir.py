from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from tracegraph.constants.engine import DEFAULT_MAX_HOPS, MAX_HOPS_LIMIT

Tier = Literal["asserted", "observed", "derived", "inferred", "hypothesized"]


class _Op(BaseModel):
    """
    #Feature: Query IR (PRD 7.2)
    #Scenario: Base for every operator; operators are immutable and JSON-serialisable
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class Select(_Op):
    """
    #Feature: Query IR
    #Scenario: Typed anchor with property equality predicates; includes subtypes; "key" matches natural_key
    #Complexity: Time O(n) - scan of the type's nodes
    """

    op: Literal["select"] = "select"
    type: str
    where: dict[str, Any] = Field(default_factory=dict)


class Resolve(_Op):
    """
    #Feature: Query IR
    #Scenario: Fuzzy text lookup returning ranked candidates; never commits to one
    #Complexity: Time O(n) - scan of candidate types
    """

    op: Literal["resolve"] = "resolve"
    text: str = Field(min_length=1)
    types: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=100)


class Expand(_Op):
    """
    #Feature: Query IR
    #Scenario: One typed hop; edge may be an edge name (forward) or its inverse name (reverse)
    #Complexity: Time O(d) - degree of input nodes
    """

    op: Literal["expand"] = "expand"
    input: "Query"
    edge: str
    min_tier: Tier = "inferred"
    target_types: list[str] = Field(default_factory=list)


class Reach(_Op):
    """
    #Feature: Query IR
    #Scenario: Regular path query from the input set, e.g. "HANDLED_BY . (CALLS|INJECTS)* . WRITES_TO"
    #Complexity: Time O((n + e) * q) - product of graph and automaton
    """

    op: Literal["reach"] = "reach"
    input: "Query"
    rpq: str
    max_hops: int = Field(default=DEFAULT_MAX_HOPS, ge=1, le=MAX_HOPS_LIMIT)
    min_tier: Tier = "inferred"
    target_types: list[str] = Field(default_factory=list)
    include_start: bool = False


class Paths(_Op):
    """
    #Feature: Query IR
    #Scenario: Up to k shortest witness paths from source set to target set along an RPQ
    #Complexity: Time O(k * (n + e) * q) - repeated product BFS
    """

    op: Literal["paths"] = "paths"
    source: "Query"
    target: "Query"
    rpq: str
    k: int = Field(default=1, ge=1, le=20)
    max_hops: int = Field(default=DEFAULT_MAX_HOPS, ge=1, le=MAX_HOPS_LIMIT)
    min_tier: Tier = "inferred"


class Union_(_Op):
    """
    #Feature: Query IR
    #Scenario: Set union of sub-queries
    #Complexity: Time O(sum of inputs)
    """

    op: Literal["union"] = "union"
    inputs: list["Query"] = Field(min_length=1)


class Intersect(_Op):
    """
    #Feature: Query IR
    #Scenario: Set intersection of sub-queries
    #Complexity: Time O(sum of inputs)
    """

    op: Literal["intersect"] = "intersect"
    inputs: list["Query"] = Field(min_length=2)


class Minus(_Op):
    """
    #Feature: Query IR
    #Scenario: Nodes of left not in right (set difference, no closed-world claim)
    #Complexity: Time O(left + right)
    """

    op: Literal["minus"] = "minus"
    left: "Query"
    right: "Query"


class NotExists(_Op):
    """
    #Feature: Query IR (PRD 7.5 three-valued negation)
    #Scenario: Scope nodes from which the RPQ reaches no target; TRUE only where the explored region has no
               coverage holes, else UNKNOWN with the blocking holes
    #Complexity: Time O(|scope| * (n + e) * q)
    """

    op: Literal["not_exists"] = "not_exists"
    scope: "Query"
    rpq: str
    target_types: list[str] = Field(default_factory=list)
    max_hops: int = Field(default=DEFAULT_MAX_HOPS, ge=1, le=MAX_HOPS_LIMIT)
    min_tier: Tier = "inferred"


class ForAll(_Op):
    """
    #Feature: Query IR
    #Scenario: Every scope node reaches a target along the RPQ; evaluated as not-exists-not with counterexamples
    #Complexity: Time O(|scope| * (n + e) * q)
    """

    op: Literal["forall"] = "forall"
    scope: "Query"
    rpq: str
    target_types: list[str] = Field(default_factory=list)
    max_hops: int = Field(default=DEFAULT_MAX_HOPS, ge=1, le=MAX_HOPS_LIMIT)
    min_tier: Tier = "inferred"


class Aggregate(_Op):
    """
    #Feature: Query IR
    #Scenario: Per group node, count (distinct) nodes reached along an RPQ; lower bounds under coverage holes
    #Complexity: Time O(|groups| * (n + e) * q)
    """

    op: Literal["aggregate"] = "aggregate"
    groups: "Query"
    rpq: str
    fn: Literal["count", "count_distinct"] = "count_distinct"
    target_types: list[str] = Field(default_factory=list)
    having_min: int = Field(default=0, ge=0)
    order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=50, ge=1, le=1000)
    max_hops: int = Field(default=DEFAULT_MAX_HOPS, ge=1, le=MAX_HOPS_LIMIT)


class Rank(_Op):
    """
    #Feature: Query IR
    #Scenario: Top-k of a node set by fan_in / fan_out over edge types, or blast radius along an RPQ
    #Complexity: Time O(|input| * score cost)
    """

    op: Literal["rank"] = "rank"
    input: "Query"
    score: Literal["fan_in", "fan_out", "blast_radius"]
    edges: list[str] = Field(default_factory=list)
    rpq: str | None = None
    k: int = Field(default=10, ge=1, le=1000)


class SCC(_Op):
    """
    #Feature: Query IR
    #Scenario: Strongly connected components (size > 1) among the input nodes over one edge type
    #Complexity: Time O(n + e) - Tarjan
    """

    op: Literal["scc"] = "scc"
    input: "Query"
    edge: str


Query = Annotated[
    Union[Select, Resolve, Expand, Reach, Paths, Union_, Intersect, Minus, NotExists, ForAll, Aggregate, Rank, SCC],
    Field(discriminator="op"),
]

for _model in (Expand, Reach, Paths, Union_, Intersect, Minus, NotExists, ForAll, Aggregate, Rank, SCC):
    _model.model_rebuild()
