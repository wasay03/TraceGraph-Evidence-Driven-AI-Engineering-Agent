from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ValueType = Literal["str", "bool", "int", "float", "enum", "list", "json"]
Cardinality = Literal["1:1", "1:N", "N:1", "N:M"]
EvidencePolicy = Literal["span_required", "evidence_required", "none"]

_PY_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "bool": (bool,),
    "int": (int,),
    "float": (int, float),
    "enum": (str,),
    "list": (list, tuple),
    "json": (dict, list, str, int, float, bool),
}


class PropSpec(BaseModel):
    """
    #Feature: Ontology registry
    #Scenario: Typed property declaration on a node or edge type
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(frozen=True)

    value_type: ValueType
    required: bool = False
    enum_values: tuple[str, ...] | None = None
    default: Any = None

    def accepts(self, value: Any) -> bool:
        """
        #Feature: Ontology registry
        #Scenario: Check a value against the declared type and enum domain
        #Complexity: Time O(1) - constant

        Args:
            value: Candidate property value; None is accepted for optional props.

        Returns:
            True when the value is admissible.
        """
        if value is None:
            return not self.required
        if self.value_type in ("int", "float") and isinstance(value, bool):
            return False
        if not isinstance(value, _PY_TYPES[self.value_type]):
            return False
        return self.enum_values is None or value in self.enum_values


class NodeTypeSpec(BaseModel):
    """
    #Feature: Ontology registry
    #Scenario: Registered node type; key is a format string over its props, e.g. "{method} {path}"
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1)
    name: str
    parent: str | None = None
    abstract: bool = False
    key: str | None = None
    props: dict[str, PropSpec] = Field(default_factory=dict)
    tiers: frozenset[str] = frozenset({"asserted"})
    owner: str | None = None


class EdgeTypeSpec(BaseModel):
    """
    #Feature: Ontology registry
    #Scenario: Registered edge type; signatures are permitted (domain, range) pairs, subtypes included
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1)
    name: str
    signatures: tuple[tuple[str, str], ...]
    cardinality: Cardinality
    inverse: str | None = None
    props: dict[str, PropSpec] = Field(default_factory=dict)
    flags: dict[str, Any] = Field(default_factory=dict)
    tiers: frozenset[str] = frozenset({"asserted"})
    evidence: EvidencePolicy = "span_required"


def Str(required: bool = False, default: str | None = None) -> PropSpec:  # noqa: N802
    """
    #Feature: Ontology registry
    #Scenario: Shorthand for a string property
    #Complexity: Time O(1) - constant
    """
    return PropSpec(value_type="str", required=required, default=default)


def Bool(required: bool = False, default: bool | None = None) -> PropSpec:  # noqa: N802
    """
    #Feature: Ontology registry
    #Scenario: Shorthand for a boolean property
    #Complexity: Time O(1) - constant
    """
    return PropSpec(value_type="bool", required=required, default=default)


def Int(required: bool = False, default: int | None = None) -> PropSpec:  # noqa: N802
    """
    #Feature: Ontology registry
    #Scenario: Shorthand for an integer property
    #Complexity: Time O(1) - constant
    """
    return PropSpec(value_type="int", required=required, default=default)


def Float(required: bool = False, default: float | None = None) -> PropSpec:  # noqa: N802
    """
    #Feature: Ontology registry
    #Scenario: Shorthand for a float property
    #Complexity: Time O(1) - constant
    """
    return PropSpec(value_type="float", required=required, default=default)


def Enum(*values: str, required: bool = False, default: str | None = None) -> PropSpec:  # noqa: N802
    """
    #Feature: Ontology registry
    #Scenario: Shorthand for an enum property with a closed value domain
    #Complexity: Time O(1) - constant
    """
    return PropSpec(value_type="enum", required=required, enum_values=tuple(values), default=default)


def List(required: bool = False) -> PropSpec:  # noqa: N802
    """
    #Feature: Ontology registry
    #Scenario: Shorthand for a list property
    #Complexity: Time O(1) - constant
    """
    return PropSpec(value_type="list", required=required)
