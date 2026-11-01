from typing import Any

from tracegraph.agent.state import RunState
from tracegraph.constants import agent as a

_LADDER = ("patch_in_scope", "lint", "type_check", "migration_round_trip", "targeted_tests", "full_suite",
           "reindex_invariants", "plan_conformance")


def partial_report(phase: str, reason: str, state: RunState) -> dict[str, Any]:
    """
    #Feature: Partial report (PRD 13, budget exhausted)
    #Scenario: Built from run state with no model call, so it still exists when the budget is gone
    #Complexity: Time O(r + o) - rungs and obligations
    """
    verification = state.verification or {}
    rungs = {r["name"]: r["status"] for r in verification.get("rungs", [])}
    obligations = (verification.get("conformance") or {}).get("obligations", {})
    return {
        "reason": reason, "stopped_in": phase, "patches": len(state.patches),
        "completed_phases": [p for p in a.LLM_PHASES if p in state.artifacts],
        "verified": [name for name, status in rungs.items() if status == "passed"],
        "failed": [name for name, status in rungs.items() if status == "failed"],
        "not_verified": [name for name in _LADDER if rungs.get(name) not in ("passed", "failed")],
        "unmet_obligations": sorted(k for k, v in obligations.items() if v == "unmet"),
        "unchecked_obligations": sorted(k for k, v in obligations.items() if v == "unchecked"),
    }
