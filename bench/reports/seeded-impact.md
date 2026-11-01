# Impact benchmark: seeded (9 tasks, frozen=False)

| task | predictor | P | R | F1 | BREAKS R | BREAKS P | nDCG@10 | obligations R | holes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| discount_code_nullable | tracegraph | 0.8 | 1.0 | 0.8889 | 1.0 | 1.0 | 0.9106 | 1.0 | ok |
| discount_code_nullable | grep_baseline | 0.4 | 0.5 | 0.4444 | 1.0 | 0.2 | 0.7387 | 0.0 | missed |
| total_nullable | tracegraph | 0.875 | 1.0 | 0.9333 | 0.3333 | 1.0 | 0.9005 | 1.0 | ok |
| total_nullable | grep_baseline | 0.5714 | 0.5714 | 0.5714 | 1.0 | 0.4286 | 0.7288 | 0.0 | missed |
| status_cancelled | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| status_cancelled | grep_baseline | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | ok |
| discount_requires_tenant | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| discount_requires_tenant | grep_baseline | 0.6667 | 0.3333 | 0.4444 | 1.0 | 0.6667 | 0.4583 | 0.0 | ok |
| total_may_be_none | tracegraph | 1.0 | 1.0 | 1.0 | 0.5 | 0.5 | 0.9688 | 1.0 | ok |
| total_may_be_none | grep_baseline | 0.6667 | 0.5 | 0.5714 | 0.5 | 0.3333 | 0.4202 | 0.0 | ok |
| remove_mark_refunded | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| remove_mark_refunded | grep_baseline | 0.5 | 0.3333 | 0.4 | 1.0 | 0.5 | 0.403 | 1.0 | ok |
| drop_discount_code | tracegraph | 1.0 | 1.0 | 1.0 | 0.5 | 1.0 | 0.9114 | 1.0 | ok |
| drop_discount_code | grep_baseline | 0.4 | 0.4 | 0.4 | 1.0 | 0.4 | 0.7123 | 0.0 | missed |
| rework_get_discount | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| rework_get_discount | grep_baseline | 0.6667 | 0.3333 | 0.4444 | 1.0 | 0.0 | 0.3422 | 1.0 | ok |
| tenant_name_nullable | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| tenant_name_nullable | grep_baseline | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | missed |

| metric | tracegraph | grep_baseline |
| --- | --- | --- |
| precision | 0.9639 [0.9111, 1.0] | 0.4302 [0.263, 0.5783] |
| recall | 1.0 [1.0, 1.0] | 0.5524 [0.4079, 0.7222] |
| f1 | 0.9802 [0.9506, 1.0] | 0.364 [0.2272, 0.4818] |
| breaks_recall | 0.8148 [0.6296, 1.0] | 0.9444 [0.8333, 1.0] |
| breaks_precision | 0.9444 [0.8333, 1.0] | 0.281 [0.137, 0.4328] |
| ndcg@10 | 0.9657 [0.936, 0.9902] | 0.6448 [0.5001, 0.8033] |
| obligation_recall | 1.0 [1.0, 1.0] | 0.2222 [0.0, 0.5556] |
| hole_tasks_reported | 1 | 0 |

Wilcoxon signed-rank on f1 (baseline vs tracegraph): n=9, W+=45.0, p=0.0092

Wilcoxon signed-rank on breaks_recall (baseline vs tracegraph): n=2, W+=0, p=0.3711
