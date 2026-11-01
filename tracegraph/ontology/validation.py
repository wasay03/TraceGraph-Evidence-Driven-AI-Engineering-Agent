import string
from typing import Any

from tracegraph.errors import Errors
from tracegraph.ontology.registry import Registry
from tracegraph.ontology.specs import PropSpec

_FORMATTER = string.Formatter()


def _check_props(owner: str, specs: dict[str, PropSpec], props: dict[str, Any]) -> None:
    """
    #Feature: Ontology validation
    #Scenario: Reject unknown props, missing required props and ill-typed values
    #Complexity: Time O(p) - linear in props

    Args:
        owner: Type name, for error messages.
        specs: Effective prop specs of the type.
        props: Candidate props.

    Raises:
        Errors.Domain.PropertyViolation: On the first violation found.
    """
    unknown = set(props) - set(specs)
    if unknown:
        raise Errors.Domain.PropertyViolation(
            f"{owner} has unregistered properties {sorted(unknown)}.", {"type": owner, "props": sorted(unknown)}
        )
    for name, spec in specs.items():
        if not spec.accepts(props.get(name)):
            raise Errors.Domain.PropertyViolation(
                f"{owner}.{name} rejects value {props.get(name)!r}; expected {spec.value_type}"
                f"{' in ' + str(spec.enum_values) if spec.enum_values else ''}"
                f"{' (required)' if spec.required else ''}.",
                {"type": owner, "prop": name},
            )


def _check_tier(owner: str, allowed: frozenset[str], tier: str) -> None:
    """
    #Feature: Ontology validation
    #Scenario: Reject rows written with a tier their type does not allow (D7)
    #Complexity: Time O(1) - constant

    Raises:
        Errors.Domain.TierViolation: When tier is not allowed.
    """
    if tier not in allowed:
        raise Errors.Domain.TierViolation(
            f"{owner} does not allow tier {tier!r}; allowed {sorted(allowed)}.", {"type": owner, "tier": tier}
        )


def natural_key_of(registry: Registry, type_name: str, props: dict[str, Any]) -> str:
    """
    #Feature: Ontology validation
    #Scenario: Render a node's natural key from its type's key format and props
    #Complexity: Time O(k) - linear in key fields

    Args:
        registry: Ontology registry.
        type_name: Concrete node type.
        props: Node props containing every key field.

    Returns:
        The natural key string.

    Raises:
        Errors.Domain.PropertyViolation: When a key field is missing or the type has no key.
    """
    spec = registry.node_type(type_name)
    if spec.key is None:
        raise Errors.Domain.PropertyViolation(f"{type_name} declares no natural key.", {"type": type_name})
    fields = [f for _, f, _, _ in _FORMATTER.parse(spec.key) if f]
    missing = [f for f in fields if props.get(f) is None]
    if missing:
        raise Errors.Domain.PropertyViolation(
            f"{type_name} natural key needs props {missing}.", {"type": type_name, "missing": missing}
        )
    return spec.key.format(**{f: props[f] for f in fields})


def validate_node(registry: Registry, type_name: str, props: dict[str, Any], tier: str) -> None:
    """
    #Feature: Ontology validation
    #Scenario: Write-path check for a node: known concrete type, valid props, allowed tier
    #Complexity: Time O(p + d) - props plus hierarchy depth

    Raises:
        Errors.Domain.UnknownType: When the type is missing or abstract.
        Errors.Domain.PropertyViolation: When props are invalid.
        Errors.Domain.TierViolation: When the tier is not allowed.
    """
    spec = registry.node_type(type_name)
    if spec.abstract:
        raise Errors.Domain.UnknownType(f"{type_name} is abstract and cannot be instantiated.", {"type": type_name})
    _check_props(type_name, registry.node_props(type_name), props)
    _check_tier(type_name, spec.tiers, tier)


def validate_edge(
    registry: Registry,
    edge_name: str,
    src_type: str,
    dst_type: str,
    props: dict[str, Any],
    tier: str,
    evidence_count: int,
    has_span: bool,
) -> None:
    """
    #Feature: Ontology validation
    #Scenario: Write-path check for an edge: signature, props, tier and evidence policy
    #Complexity: Time O(s * d + p) - signatures times depth plus props

    Raises:
        Errors.Domain.DomainViolation: When endpoints do not satisfy any signature.
        Errors.Domain.MissingEvidence: When the evidence policy is not met.
        Errors.Domain.PropertyViolation / TierViolation: As for nodes.
    """
    spec = registry.edge_type(edge_name)
    if not registry.edge_permits(edge_name, src_type, dst_type):
        raise Errors.Domain.DomainViolation(
            f"{edge_name} does not permit {src_type} -> {dst_type}.",
            {"edge": edge_name, "src_type": src_type, "dst_type": dst_type},
        )
    _check_props(edge_name, spec.props, props)
    _check_tier(edge_name, spec.tiers, tier)
    if spec.evidence != "none" and evidence_count == 0:
        raise Errors.Domain.MissingEvidence(f"{edge_name} requires evidence.", {"edge": edge_name})
    if spec.evidence == "span_required" and not has_span:
        raise Errors.Domain.MissingEvidence(f"{edge_name} requires evidence with a source span.", {"edge": edge_name})
