from collections.abc import Awaitable, Callable

from tracegraph.agent.artifacts import Report

TruthLookup = Callable[[str], Awaitable[str | None]]


async def check_claims(report: Report, run_handles: list[str], truth_of: TruthLookup) -> list[str]:
    """
    #Feature: Claim binding (PRD 10.4)
    #Scenario: Every claim cites a handle produced in this run, and a stated truth matches the stored answer
    #Complexity: Time O(c) - claims, one lookup each

    Args:
        report: Submitted report.
        run_handles: Handles returned by tools during this run.
        truth_of: Stored truth of a handle, or None when the handle does not exist.

    Returns:
        Violations; empty means every claim is bound.

    Raises:
        ValueError: When report is None.
    """
    if report is None:
        raise ValueError("[check_claims] 'report' is required.")
    issued, problems = set(run_handles), []
    for i, claim in enumerate(report.claims):
        if claim.handle not in issued:
            problems.append(f"claim {i} cites {claim.handle}, which no tool returned in this run")
            continue
        stored = await truth_of(claim.handle)
        if stored is None:
            problems.append(f"claim {i} cites unknown handle {claim.handle}")
        elif claim.truth is not None and claim.truth != stored:
            problems.append(f"claim {i} states truth {claim.truth} but {claim.handle} has truth {stored}")
    return problems
