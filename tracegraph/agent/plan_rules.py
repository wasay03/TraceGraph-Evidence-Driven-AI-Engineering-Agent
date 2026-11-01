from pathlib import Path
from typing import Any

from tracegraph.agent.artifacts import Plan
from tracegraph.constants.impact import AT_RISK, BREAKS

TOP_RANKED_TESTS = 1


def _path_problems(plan: Plan, root: Path) -> list[str]:
    """
    #Feature: Plan validity rules
    #Scenario: Scope entries must be files that exist, or new files in a directory that exists; tests must be pytest
               ids in a test file that exists or is created by this plan
    #Complexity: Time O(f + t) - scope files plus tests
    """
    problems = []
    for name in plan.scope_files:
        path = root / name
        if name.endswith("/") or path.is_dir():
            problems.append(f"scope file {name!r} is a directory; name the exact file to change or create")
        elif not path.is_file() and not path.parent.is_dir():
            problems.append(f"scope file {name!r} is not in the repository and its directory does not exist; "
                            "use the repository layout in your context")
    for test in plan.tests:
        file = test.split("::")[0]
        if not file.endswith(".py"):
            problems.append(f"test {test!r} must be a pytest id such as tests/test_x.py::test_name")
        elif not (root / file).is_file() and file not in plan.scope_files:
            problems.append(f"test file {file!r} neither exists nor is created by this plan")
    return problems


def validate_plan(plan: Plan, impact: dict[str, Any] | None, root: Path | None = None) -> list[str]:
    """
    #Feature: Plan validity rules (PRD 10.2)
    #Scenario: Rejected in code unless BREAKS are addressed or accepted, obligations covered, steps name targets
               and what they serve, top tests listed, and the scope set equals the step files
    #Complexity: Time O(s + f) - steps plus findings

    Args:
        plan: Submitted plan.
        impact: simulate_change summary stored on the run (None when no change was simulated).
        root: Checkout to verify paths against (None skips those checks).

    Returns:
        Violations; empty means the plan is valid.

    Raises:
        ValueError: When plan is None.
    """
    if plan is None:
        raise ValueError("[validate_plan] 'plan' is required.")
    violations = []
    step_files = {f for s in plan.steps for f in s.files}
    if set(plan.scope_files) != step_files:
        violations.append(f"scope_files must equal the union of step files {sorted(step_files)}, "
                          f"got {sorted(plan.scope_files)}")
    if root is not None:
        violations += _path_problems(plan, root)
    if impact is None:
        return violations
    served = {x for s in plan.steps for x in s.serves} | {t for s in plan.steps for t in s.targets}
    accepted = {r.node for r in plan.accepted_risks}
    for finding in impact.get("findings", []):
        if finding["cls"] == BREAKS and finding["key"] not in served | accepted:
            violations.append(f"BREAKS finding {finding['key']} is neither addressed by a step nor accepted")
    for obligation in impact.get("obligations", []):
        if obligation["kind"] not in served and obligation["target"] not in served:
            violations.append(f"obligation {obligation['kind']} on {obligation['target']} has no step")
    risky = any(f["cls"] in (BREAKS, AT_RISK) for f in impact.get("findings", []))
    wanted = impact.get("tests", [])[:TOP_RANKED_TESTS] if risky else []
    missing = [t for t in wanted if t not in plan.tests]
    if missing:
        violations.append(f"tests must include the top-ranked tests {missing}")
    return violations
