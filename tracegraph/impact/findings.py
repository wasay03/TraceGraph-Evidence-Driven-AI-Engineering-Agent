import math
from dataclasses import dataclass, field

from tracegraph.constants.impact import CLASS_PRIORITY, SEVERITY, TIER_WEIGHT
from tracegraph.constants.graph import TIERS
from tracegraph.engine.evaluator import Derivation


@dataclass(slots=True)
class Finding:
    """
    #Feature: Impact analysis (PRD 8.2)
    #Scenario: One classified consequence of a change with the derivation that justifies it
    #Complexity: Time O(1) - constant
    """

    node: int
    cls: str
    reason: str
    change: str
    rule: str
    derivation: Derivation = field(default_factory=Derivation)
    distance: int = 1
    score: float = 0.0


@dataclass(slots=True)
class Obligation:
    """
    #Feature: Impact analysis (PRD 8.2 step 5)
    #Scenario: Something the change requires regardless of code, e.g. an Alembic migration
    #Complexity: Time O(1) - constant
    """

    kind: str
    target: int
    detail: str


def merge(findings: dict[int, Finding], new: Finding) -> None:
    """
    #Feature: Impact analysis
    #Scenario: Keep the strongest classification per node (BREAKS > UNKNOWN > AT_RISK > GUARDED), then shortest
    #Complexity: Time O(1) - constant
    """
    old = findings.get(new.node)
    if old is None or (CLASS_PRIORITY[new.cls], new.distance) < (CLASS_PRIORITY[old.cls], old.distance):
        findings[new.node] = new


def score(finding: Finding, fan_in: int) -> float:
    """
    #Feature: Impact ranking (PRD 8.2 step 8)
    #Scenario: severity x tier weight x 1/(1 + distance) x log(2 + fan_in); log(2 + .) keeps zero-fan-in nodes ranked
    #Complexity: Time O(1) - constant
    """
    tier = TIERS[finding.derivation.tier_rank]
    return round(SEVERITY[finding.cls] * TIER_WEIGHT[tier] / (1 + finding.distance) * math.log(2 + fan_in), 4)
