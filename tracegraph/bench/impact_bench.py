import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import TypeAdapter

from tracegraph.bench.metrics import bootstrap_ci, ndcg_at_k, prf, wilcoxon_signed_rank
from tracegraph.bench.tasks import Suite, Task
from tracegraph.constants.impact import AT_RISK, BREAKS, UNKNOWN
from tracegraph.engine.graph import GraphSnapshot
from tracegraph.engine.loader import graph_from_directory
from tracegraph.impact import ChangeSpec, ImpactAnalyzer
from tracegraph.ontology import get_registry

_SPECS = TypeAdapter(list[ChangeSpec])
PREDICTORS = ("tracegraph", "grep_baseline")


@dataclass(slots=True)
class Prediction:
    """
    #Feature: Impact benchmark
    #Scenario: What one predictor claims for a task, ranked
    #Complexity: Time O(1) - constant
    """

    ranked: list[str]
    breaks: set[str] = field(default_factory=set)
    unknown: set[str] = field(default_factory=set)
    obligations: set[str] = field(default_factory=set)


def predict_tracegraph(graph: GraphSnapshot, task: Task) -> Prediction:
    """
    #Feature: Impact benchmark
    #Scenario: Impact analyzer on the task's ChangeSpecs; affected = BREAKS + AT_RISK + UNKNOWN, ranked by score
    #Complexity: Time per impact analysis
    """
    result = ImpactAnalyzer(graph).analyze(_SPECS.validate_python(task.changes))
    keyed = [(graph.nodes[f.node].key, f.cls) for f in result.findings if f.node in graph.nodes]
    return Prediction(ranked=[k for k, cls in keyed if cls in (BREAKS, AT_RISK, UNKNOWN)],
                      breaks={k for k, cls in keyed if cls == BREAKS},
                      unknown={k for k, cls in keyed if cls == UNKNOWN},
                      obligations={o.kind for o in result.obligations})


def predict_grep(graph: GraphSnapshot, task: Task, sources: dict[str, list[str]]) -> Prediction:
    """
    #Feature: Impact benchmark
    #Scenario: Text-only proxy for "search and file reads": callables whose source mentions a task token; it
               cannot tell breaks from risks, so every hit counts as a predicted break
    #Complexity: Time O(F * l) - callables times body lines
    """
    patterns = [re.compile(rf"\b{re.escape(t)}\b") for t in task.tokens]
    hits = []
    for node in sorted(graph.of_type("Callable"), key=lambda n: (n.file or "", n.line_start or 0)):
        body = sources.get(node.file or "", [])[(node.line_start or 1) - 1: node.line_end or 0]
        if any(p.search(line) for p in patterns for line in body):
            hits.append(node.key)
    return Prediction(ranked=hits, breaks=set(hits))


def score(task: Task, prediction: Prediction) -> dict[str, Any]:
    """
    #Feature: Impact benchmark (PRD 12.1 "Impact" layer)
    #Scenario: Affected-set P/R/F1, BREAKS recall, nDCG@10, obligation recall and the hole-task check
    #Complexity: Time O(p + g) - set sizes
    """
    gold = task.gold
    claimed = set(prediction.ranked) - set(gold.unknown_expected)  # a correct UNKNOWN is not a false positive
    affected = prf(claimed, gold.affected)
    relevance = {k: 2.0 for k in gold.breaks} | {k: 1.0 for k in gold.at_risk}
    holes_ok = all(k in prediction.unknown for k in gold.unknown_expected)
    return {**affected,
            "breaks_recall": prf(prediction.breaks, set(gold.breaks))["recall"],
            "breaks_precision": prf(prediction.breaks, set(gold.breaks))["precision"],
            "ndcg@10": ndcg_at_k(prediction.ranked, relevance),
            "obligation_recall": prf(prediction.obligations, set(gold.obligations))["recall"],
            "holes_reported": holes_ok,
            "false_positives": sorted(set(prediction.ranked) - gold.affected - set(gold.unknown_expected)),
            "missed": sorted(gold.affected - set(prediction.ranked))}


def _sources(root, graph: GraphSnapshot) -> dict[str, list[str]]:
    """
    #Feature: Impact benchmark
    #Scenario: Source lines per file for the text baseline
    #Complexity: Time O(b) - bytes read
    """
    files = {n.file for n in graph.nodes.values() if n.file}
    return {f: (root / f).read_text(encoding="utf-8", errors="replace").splitlines() for f in files}


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    #Feature: Impact benchmark
    #Scenario: Mean and 95% bootstrap interval per metric and predictor; paired Wilcoxon on F1 and BREAKS recall
    #Complexity: Time O(bootstrap iterations * tasks)
    """
    summary: dict[str, Any] = {}
    for predictor in PREDICTORS:
        mine = [r for r in rows if r["predictor"] == predictor]
        summary[predictor] = {m: bootstrap_ci([float(r[m]) for r in mine])
                              for m in ("precision", "recall", "f1", "breaks_recall", "breaks_precision", "ndcg@10",
                                        "obligation_recall")}
        summary[predictor]["hole_tasks_reported"] = sum(r["holes_reported"] for r in mine if r["hole_task"])
    for metric in ("f1", "breaks_recall"):
        base = [r[metric] for r in rows if r["predictor"] == "grep_baseline"]
        full = [r[metric] for r in rows if r["predictor"] == "tracegraph"]
        summary[f"wilcoxon_{metric}"] = wilcoxon_signed_rank(base, full)
    return summary


def run_impact_benchmark(suite: Suite) -> dict[str, Any]:
    """
    #Feature: Impact benchmark (PRD 12.2 question-only tasks)
    #Scenario: Score both predictors on every task; no LLM involved, fully deterministic
    #Complexity: Time O(tasks * (extraction + impact analysis))

    Raises:
        ValueError: When the suite is empty.
    """
    if not suite.tasks:
        raise ValueError("[run_impact_benchmark] the suite has no tasks.")
    registry, graphs, rows = get_registry(), {}, []
    for task in suite.tasks:
        root = (suite.base_dir / task.repo).resolve()
        if root not in graphs:
            graphs[root] = graph_from_directory(registry, root)
        graph = graphs[root]
        for name, prediction in (("tracegraph", predict_tracegraph(graph, task)),
                                 ("grep_baseline", predict_grep(graph, task, _sources(root, graph)))):
            rows.append({"task": task.id, "predictor": name, "hole_task": task.hole_task, **score(task, prediction)})
    return {"suite": suite.name, "frozen": suite.frozen, "tasks": len(suite.tasks), "rows": rows,
            "summary": _aggregate(rows)}


def render_markdown(result: dict[str, Any]) -> str:
    """
    #Feature: Impact benchmark
    #Scenario: Human-readable report: per-task rows, then means with 95% bootstrap intervals and the paired test
    #Complexity: Time O(rows)
    """
    head = "| task | predictor | P | R | F1 | BREAKS R | BREAKS P | nDCG@10 | obligations R | holes |"
    lines = [f"# Impact benchmark: {result['suite']} ({result['tasks']} tasks, frozen={result['frozen']})", "",
             head, "|" + " --- |" * 10]
    for r in result["rows"]:
        lines.append(f"| {r['task']} | {r['predictor']} | {r['precision']} | {r['recall']} | {r['f1']} | "
                     f"{r['breaks_recall']} | {r['breaks_precision']} | {r['ndcg@10']} | {r['obligation_recall']} | "
                     f"{'ok' if r['holes_reported'] else 'missed'} |")
    lines += ["", "| metric | " + " | ".join(PREDICTORS) + " |", "| --- |" + " --- |" * len(PREDICTORS)]
    for metric in result["summary"][PREDICTORS[0]]:
        cells = []
        for p in PREDICTORS:
            value = result["summary"][p][metric]
            cells.append(f"{value[0]} [{value[1]}, {value[2]}]" if isinstance(value, (list, tuple)) else str(value))
        lines.append(f"| {metric} | " + " | ".join(cells) + " |")
    for metric in ("f1", "breaks_recall"):
        w = result["summary"][f"wilcoxon_{metric}"]
        lines.append(f"\nWilcoxon signed-rank on {metric} (baseline vs tracegraph): n={w['n']}, "
                     f"W+={w['w_plus']}, p={w['p_value']}")
    return "\n".join(lines) + "\n"
