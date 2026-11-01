from typing import Any

from pydantic import Field, TypeAdapter, ValidationError

from tracegraph.constants import agent as a
from tracegraph.errors import AppError, Errors
from tracegraph.impact import ChangeSpec, target_of
from tracegraph.schemas.impact import ImpactRequest
from tracegraph.tools.common import ToolInput
from tracegraph.tools.registry import ToolContext, ToolOutput, ToolSpec

_SPECS = TypeAdapter(list[ChangeSpec])
_ANALYZE = frozenset({a.PHASE_ANALYZE})


class ChangesInput(ToolInput):
    """
    #Feature: Tool catalog (impact)
    #Scenario: ChangeSpecs as JSON objects, e.g. {"kind": "make_column_nullable", "column": "orders.status"}
    #Complexity: Time O(1) - constant
    """

    changes: list[dict[str, Any]] = Field(min_length=1, max_length=10)


def _validate(ctx: ToolContext, changes: list[dict[str, Any]]) -> list[Any]:
    """
    #Feature: Tool catalog (impact)
    #Scenario: Schema-validate ChangeSpecs and resolve every target on the snapshot
    #Complexity: Time O(s * n) - specs times nodes

    Raises:
        Errors.HTTP.BadRequest: With every schema or target error at once.
    """
    try:
        specs = _SPECS.validate_python(changes)
    except ValidationError as exc:
        raise Errors.HTTP.BadRequest(f"Invalid ChangeSpecs: {exc.errors(include_url=False)[:5]}") from exc
    problems = []
    for spec in specs:
        try:
            target_of(ctx.graph, spec)
        except AppError as exc:
            problems.append(exc.message)
    if problems:
        raise Errors.HTTP.BadRequest("Unresolved targets: " + "; ".join(problems))
    return specs


async def propose_change_spec(ctx: ToolContext, args: ChangesInput) -> ToolOutput:
    """
    #Feature: Tool catalog (impact)
    #Scenario: Validate ChangeSpecs without simulating them
    #Complexity: Time O(s * n)
    """
    specs = _validate(ctx, args.changes)
    return ToolOutput("valid: " + "; ".join(f"{s.kind} {s.model_dump(exclude={'kind'})}" for s in specs))


async def simulate_change(ctx: ToolContext, args: ChangesInput) -> ToolOutput:
    """
    #Feature: Tool catalog (impact)
    #Scenario: What-if overlay + impact report; the report is kept on the run for plan validation
    #Complexity: Time per impact analysis
    """
    specs = _validate(ctx, args.changes)
    request = ImpactRequest(repo_id=ctx.graph.repo_id, snapshot_id=ctx.state.snapshot_id, changes=specs)
    report = await ctx.services.impact.analyze(request)
    ctx.state.impact = {
        "handle": report.handle, "changes": report.changes,
        "findings": [{"key": f.node.key, "type": f.node.type, "cls": f.cls, "reason": f.reason, "file": f.node.file}
                     for f in report.findings],
        "obligations": [{"kind": o.kind, "target": o.target.key, "detail": o.detail} for o in report.obligations],
        "tests": [t.node.key for t in report.tests],
        "invariants": [{"id": i.invariant, "status": i.status, "message": i.message} for i in report.invariants],
    }
    lines = [f"impact: {report.summary}"]
    lines += [f"  {f.cls:8} {f.node.type} {f.node.key} ({f.reason})"
              + (f" {f.evidence[-1].file}:{f.evidence[-1].lines[0]}" if f.evidence else "") for f in report.findings]
    lines += [f"  obligation {o.kind}: {o.target.key} - {o.detail}" for o in report.obligations]
    lines += [f"  test {t.node.key} score={t.score}" for t in report.tests]
    lines += [f"  invariant [{i.status}] {i.invariant}: {i.message}" for i in report.invariants]
    lines += [f"  coverage gap {g['node']}: {g['kind']}" for g in report.coverage_gaps]
    return ToolOutput("\n".join(lines), report.handle)


IMPACT_TOOLS: list[ToolSpec] = [
    ToolSpec("propose_change_spec", "1.0.0", a.GROUP_IMPACT, a.SIDE_READ, _ANALYZE, ChangesInput, propose_change_spec,
             "Validate ChangeSpecs (make_column_nullable, drop_column, add_enum_member, change_return_type, "
             "change_signature, remove_symbol, modify_body) and resolve their targets."),
    ToolSpec("simulate_change", "1.0.0", a.GROUP_IMPACT, a.SIDE_OVERLAY, _ANALYZE, ChangesInput, simulate_change,
             "Simulate ChangeSpecs on a what-if overlay: classified findings, obligations, tests, invariant diff."),
]
