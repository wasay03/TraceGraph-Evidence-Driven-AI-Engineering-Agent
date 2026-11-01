import math
import random
from collections.abc import Sequence


def prf(predicted: set[str], gold: set[str]) -> dict[str, float]:
    """
    #Feature: Benchmark metrics (PRD 12.1)
    #Scenario: Precision, recall and F1; an empty prediction against an empty gold set scores 1.0
    #Complexity: Time O(p + g) - set sizes
    """
    hit = len(predicted & gold)
    precision = hit / len(predicted) if predicted else (1.0 if not gold else 0.0)
    recall = hit / len(gold) if gold else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def ndcg_at_k(ranked: Sequence[str], relevance: dict[str, float], k: int = 10) -> float:
    """
    #Feature: Benchmark metrics
    #Scenario: Normalised discounted cumulative gain of a ranked list (1.0 when nothing is relevant)
    #Complexity: Time O(k log k)
    """
    dcg = sum(relevance.get(key, 0.0) / math.log2(i + 2) for i, key in enumerate(ranked[:k]))
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal))
    return round(dcg / idcg, 4) if idcg else 1.0


def bootstrap_ci(values: Sequence[float], iterations: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """
    #Feature: Benchmark metrics (PRD 12.4)
    #Scenario: Mean with a 95% percentile bootstrap interval; deterministic for a seed
    #Complexity: Time O(iterations * n)

    Raises:
        ValueError: When values is empty.
    """
    if not values:
        raise ValueError("[bootstrap_ci] at least one value is required.")
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(iterations))
    mean = sum(values) / len(values)
    return round(mean, 4), round(means[int(0.025 * iterations)], 4), round(means[int(0.975 * iterations) - 1], 4)


def wilcoxon_signed_rank(a: Sequence[float], b: Sequence[float]) -> dict[str, float | int]:
    """
    #Feature: Benchmark metrics (PRD 12.4)
    #Scenario: Paired two-sided Wilcoxon signed-rank test, zero differences dropped, average ranks for ties,
               normal approximation with continuity correction (indicative only for small n)
    #Complexity: Time O(n log n)

    Raises:
        ValueError: When the samples differ in length.
    """
    if len(a) != len(b):
        raise ValueError("[wilcoxon_signed_rank] samples must be paired (same length).")
    diffs = [y - x for x, y in zip(a, b, strict=True) if y != x]
    n = len(diffs)
    if n == 0:
        return {"n": 0, "w_plus": 0.0, "p_value": 1.0}
    order = sorted(range(n), key=lambda i: abs(diffs[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(diffs[order[j + 1]]) == abs(diffs[order[i]]):
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    w_plus = sum(r for r, d in zip(ranks, diffs, strict=True) if d > 0)
    mean, sd = n * (n + 1) / 4, math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    z = (abs(w_plus - mean) - 0.5) / sd if sd else 0.0
    p = math.erfc(max(z, 0.0) / math.sqrt(2))
    return {"n": n, "w_plus": w_plus, "p_value": round(min(p, 1.0), 4)}
