from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from tracegraph.agent.artifacts import Plan
from tracegraph.constants.agent import MODE_BENCHMARK
from tracegraph.constants.impact import (
    BREAKS,
    OBLIGATION_ORM_ATTRIBUTE,
    OBLIGATION_REMOVE_MAPPED_ATTRIBUTE,
    TEST_OBLIGATIONS,
)
from tracegraph.engine.graph import GraphSnapshot
from tracegraph.engine.loader import graph_from_directory
from tracegraph.errors import AppError
from tracegraph.impact import ChangeSpec, ImpactAnalyzer, check_all
from tracegraph.sandbox.run_sandbox import SandboxWorkspace

_SPECS = TypeAdapter(list[ChangeSpec])
_SYMBOL_TYPES = ("Function", "Method", "Class", "Attribute", "Variable", "Migration", "Column", "EnumMember")


@dataclass(slots=True)
class LadderResult:
    """
    #Feature: Verification ladder (PRD 11.2)
    #Scenario: Rung outcomes, plan conformance and the loop decision
    #Complexity: Time O(1) - constant
    """

    rungs: list[dict[str, Any]] = field(default_factory=list)
    conformance: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """
        #Feature: Verification ladder
        #Scenario: Every executed rung passed and conformance is clean
        #Complexity: Time O(r) - rungs
        """
        return all(r["status"] != "failed" for r in self.rungs) and not self.needs_reanalysis and not self.conformance.get(
            "unresolved_breaks") and not self.conformance.get("unmet_obligations")

    @property
    def needs_reanalysis(self) -> bool:
        """
        #Feature: Verification ladder
        #Scenario: Unplanned impact (scope creep or new invariant violations) forces Analyze again (PRD 10.3)
        #Complexity: Time O(1) - constant
        """
        return bool(self.conformance.get("scope_creep") or self.conformance.get("new_violations"))

    def add(self, rung: int, name: str, status: str, detail: Any = None) -> None:
        """
        #Feature: Verification ladder
        #Scenario: Record one rung
        #Complexity: Time O(1) - constant
        """
        self.rungs.append({"rung": rung, "name": name, "status": status, "detail": detail})

    def to_dict(self) -> dict[str, Any]:
        """
        #Feature: Verification ladder
        #Scenario: Persistable form
        #Complexity: Time O(r) - rungs
        """
        return {"passed": self.passed, "needs_reanalysis": self.needs_reanalysis,
                "rungs": sorted(self.rungs, key=lambda r: r["rung"]),
                "conformance": self.conformance}


def graph_of_worktree(base: GraphSnapshot, root: Path, repo_url: str) -> GraphSnapshot:
    """
    #Feature: Verification ladder (rung 7)
    #Scenario: Reindex the sandbox in memory (no snapshot is written) for conformance and invariant diff
    #Complexity: Time O(N * r) - extraction cost
    """
    return graph_from_directory(base.registry, root, base.repo_id, repo_url, "WORKTREE", base.seq)


def changed_symbols(graph: GraphSnapshot, changed: dict[str, set[int]]) -> set[str]:
    """
    #Feature: Plan conformance
    #Scenario: Innermost symbols whose span overlaps changed lines (a changed method does not also blame its class)
    #Complexity: Time O(n) - nodes
    """
    hits = [n for n in graph.nodes.values() if n.type in _SYMBOL_TYPES and n.file in changed and n.line_start
            and changed[n.file] & set(range(n.line_start, (n.line_end or n.line_start) + 1))]
    inner = [n for n in hits if not any(o is not n and o.file == n.file and n.line_start <= o.line_start
                                        and (o.line_end or 0) <= (n.line_end or 0) and o.type != "Column" for o in hits)]
    return {n.key for n in inner}


def migration_problems(base: GraphSnapshot, new: GraphSnapshot) -> list[str]:
    """
    #Feature: Verification ladder (rung 4, static)
    #Scenario: New migrations must revise an existing revision and the history must keep exactly one head.
               Alembic refuses to upgrade otherwise; tests that never run Alembic would not notice.
    #Complexity: Time O(m) - migrations
    """
    known = {n.key for n in base.of_type("Migration")}
    migrations = {n.props.get("revision") or n.key: n for n in new.of_type("Migration")}
    problems = [f"{rev}: down_revision {n.props.get('down_revision')!r} is not a known revision "
                f"(known: {sorted(migrations)})" for rev, n in migrations.items()
                if n.key not in known and n.props.get("down_revision") not in migrations]
    parents = {n.props.get("down_revision") for n in migrations.values()}
    heads = sorted(rev for rev in migrations if rev not in parents)
    if len(heads) > 1:
        problems.append(f"multiple heads {heads}; the new migration must revise the current head")
    return problems


def _linked_migrations(base: GraphSnapshot, new: GraphSnapshot) -> list[str]:
    """
    #Feature: Plan conformance
    #Scenario: New migrations whose down_revision is a real revision
    #Complexity: Time O(m) - migrations
    """
    known = {n.key for n in base.of_type("Migration")}
    revisions = {n.props.get("revision") or n.key for n in new.of_type("Migration")}
    return [n.key for n in new.of_type("Migration") if n.key not in known and n.props.get("down_revision") in revisions]


def _obligation_met(kind: str, target: str, detail: str, base: GraphSnapshot, new: GraphSnapshot) -> str:
    """
    #Feature: Plan conformance
    #Scenario: met / unmet / unchecked per obligation kind
    #Complexity: Time O(n) - nodes
    """
    new_by_key = {n.key: n for n in new.nodes.values()}
    if kind.startswith("migration_"):
        return "met" if _linked_migrations(base, new) else "unmet"
    if kind == "orm_attribute_optional":
        annotation = (new_by_key.get(target).props.get("annotation") or "") if target in new_by_key else ""
        return "met" if "None" in annotation or "Optional" in annotation else "unmet"
    if kind == "update_return_annotation":
        node = new_by_key.get(target)
        return "met" if node and node.props.get("return_annotation") == detail.removeprefix("-> ") else "unmet"
    if kind in TEST_OBLIGATIONS:
        known = {n.key for n in base.of_type("Test")}
        return "met" if any(n.key not in known for n in new.of_type("Test")) else "unmet"
    if kind == OBLIGATION_REMOVE_MAPPED_ATTRIBUTE:
        return "unmet" if target in new_by_key else "met"
    if kind == OBLIGATION_ORM_ATTRIBUTE:
        return "met" if f"{target}.{detail.rsplit(' ', 1)[-1]}" in new_by_key else "unmet"
    return "unchecked"


def _unresolved_breaks(new: GraphSnapshot, changes: list[dict[str, Any]]) -> list[str] | None:
    """
    #Feature: Plan conformance
    #Scenario: Re-run the change kind's rule pack on the new snapshot; remaining BREAKS are unresolved
    #Complexity: Time per impact analysis; None when the targets no longer resolve
    """
    try:
        result = ImpactAnalyzer(new).analyze(_SPECS.validate_python(changes))
    except AppError:
        return None
    return sorted(new.nodes[f.node].key for f in result.findings if f.cls == BREAKS and f.node in new.nodes)


def _scope_creep(touched: list[str] | set[str], allowed: set[str], base: GraphSnapshot, new: GraphSnapshot,
                 plan: Plan) -> list[str]:
    """
    #Feature: Plan conformance
    #Scenario: Editing an existing symbol the plan did not name is creep. A member of a planned target, anything in a
               file named as a target, and a new symbol in a planned file are what the approved plan asked for
    #Complexity: Time O(n + t * d) - nodes, touched symbols and key depth
    """
    known = {n.key for n in base.nodes.values()}
    file_of = {n.key: n.file for n in new.nodes.values()}
    targets = {t for s in plan.steps for t in s.targets}
    planned_files = {f for s in plan.steps for f in s.files}

    def in_scope(key: str) -> bool:
        parts = key.split(".")
        return (key in allowed or file_of.get(key) in targets
                or any(".".join(parts[:i]) in targets for i in range(1, len(parts)))
                or (key not in known and file_of.get(key) in planned_files))

    return sorted(k for k in touched if not in_scope(k))


def conformance(base: GraphSnapshot, new: GraphSnapshot, plan: Plan, impact: dict[str, Any] | None,
                changed: dict[str, set[int]]) -> dict[str, Any]:
    """
    #Feature: Plan conformance (PRD 8.4)
    #Scenario: Scope creep, unmet obligations, unresolved breaks, new violations and prediction error
    #Complexity: Time O(n + invariants + impact analysis)
    """
    touched = changed_symbols(new, changed)
    findings = {f["key"] for f in (impact or {}).get("findings", [])}
    obligations = (impact or {}).get("obligations", [])
    allowed = {t for s in plan.steps for t in s.targets} | findings | {o["target"] for o in obligations}
    migration_ok = any(o["kind"].startswith("migration_") for o in obligations)
    in_migrations = {n.key for n in new.nodes.values() if n.file and "versions" in n.file.split("/")[:-1]}
    creep = [k for k in _scope_creep(touched, allowed, base, new, plan) if not (migration_ok and k in in_migrations)]
    status = {f"{o['kind']}:{o['target']}": _obligation_met(o["kind"], o["target"], o["detail"], base, new)
              for o in obligations}
    before = {(v.invariant, v.message) for v in check_all(base)}
    new_violations = sorted(f"{v.invariant}: {v.message}" for v in check_all(new) if (v.invariant, v.message) not in before)
    predicted = {f["key"] for f in (impact or {}).get("findings", []) if f["cls"] != "GUARDED"}
    return {"changed_symbols": sorted(touched), "scope_creep": creep, "obligations": status,
            "unmet_obligations": sorted(k for k, v in status.items() if v == "unmet"),
            "unresolved_breaks": _unresolved_breaks(new, impact["changes"]) if impact else None,
            "new_violations": new_violations,
            "prediction": {"predicted": sorted(predicted), "actual": sorted(touched),
                           "hit": sorted(predicted & touched)}}


def run_ladder(sandbox: SandboxWorkspace, base: GraphSnapshot, repo_url: str, plan: Plan,
               impact: dict[str, Any] | None, patches: list[dict[str, Any]], mode: str) -> LadderResult:
    """
    #Feature: Verification ladder (PRD 11.2)
    #Scenario: 1 scope, 2-3 checks, 5 targeted tests, 6 full suite (benchmark), 7 reindex + invariants, 8 conformance.
               Rung 4 checks the migration chain statically; a database round trip is not run.
    #Complexity: Time O(test runtime + extraction)

    Raises:
        ValueError: When a required argument is missing.
    """
    if sandbox is None or base is None or plan is None:
        raise ValueError("[run_ladder] 'sandbox', 'base' and 'plan' are required.")
    result, scope = LadderResult(), set(plan.scope_files)
    outside = sorted({f for p in patches for f in p["files"]} - scope)
    result.add(1, "patch_in_scope", "failed" if outside or not patches else "passed", outside or None)
    changed = sandbox.changed_lines()
    checks = sandbox.run_checks(sorted(f for f in changed if f.endswith(".py")))
    result.add(2, "lint", "passed" if checks["ok"] and checks["status"] == "checked" else
               checks["status"] if checks["ok"] else "failed", checks["output"][-1500:] or None)
    result.add(3, "type_check", "unavailable")
    if plan.tests:
        targeted = sandbox.run_tests(plan.tests)
        result.add(5, "targeted_tests", "passed" if targeted["ok"] else "failed",
                   {"counts": targeted["counts"], "output": targeted["output"][-2000:]})
    else:
        result.add(5, "targeted_tests", "skipped")
    if mode == MODE_BENCHMARK:
        suite = sandbox.run_tests([])
        result.add(6, "full_suite", "passed" if suite["ok"] else "failed",
                   {"counts": suite["counts"], "output": suite["output"][-2000:]})
    new = graph_of_worktree(base, sandbox.root, repo_url)
    problems = migration_problems(base, new)
    touched = len(new.of_type("Migration")) != len(base.of_type("Migration"))
    result.add(4, "migration_chain", "failed" if problems else "passed" if touched else "skipped",
               problems or ("static check of revision links and heads; no database round trip" if touched else None))
    result.conformance = conformance(base, new, plan, impact, changed)
    result.add(7, "reindex_invariants", "failed" if result.conformance["new_violations"] else "passed",
               result.conformance["new_violations"] or None)
    status = "failed" if result.needs_reanalysis or result.conformance["unmet_obligations"] or \
        result.conformance["unresolved_breaks"] else "passed"
    result.add(8, "plan_conformance", status, {k: result.conformance[k] for k in
                                                ("scope_creep", "unmet_obligations", "unresolved_breaks")})
    return result
