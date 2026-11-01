# Impact benchmark: seeded (17 tasks, frozen=False)

| task | predictor | P | R | F1 | BREAKS R | BREAKS P | nDCG@10 | obligations R | holes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| discount_code_nullable | tracegraph | 0.8 | 1.0 | 0.8889 | 1.0 | 1.0 | 0.9106 | 1.0 | ok |
| discount_code_nullable | grep_baseline | 0.4 | 0.5 | 0.4444 | 1.0 | 0.2 | 0.7387 | 0.0 | missed |
| total_nullable | tracegraph | 0.875 | 1.0 | 0.9333 | 1.0 | 1.0 | 0.9775 | 1.0 | ok |
| total_nullable | grep_baseline | 0.5714 | 0.5714 | 0.5714 | 1.0 | 0.4286 | 0.7288 | 0.0 | missed |
| status_cancelled | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| status_cancelled | grep_baseline | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | ok |
| discount_requires_tenant | tracegraph | 0.8571 | 1.0 | 0.9231 | 1.0 | 1.0 | 0.9662 | 1.0 | ok |
| discount_requires_tenant | grep_baseline | 0.6667 | 0.3333 | 0.4444 | 1.0 | 0.6667 | 0.4583 | 0.0 | ok |
| total_may_be_none | tracegraph | 0.8 | 1.0 | 0.8889 | 0.5 | 0.5 | 0.9252 | 1.0 | ok |
| total_may_be_none | grep_baseline | 0.6667 | 0.5 | 0.5714 | 0.5 | 0.3333 | 0.4202 | 0.0 | ok |
| remove_mark_refunded | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| remove_mark_refunded | grep_baseline | 0.5 | 0.3333 | 0.4 | 1.0 | 0.5 | 0.403 | 1.0 | ok |
| drop_discount_code | tracegraph | 0.8333 | 1.0 | 0.9091 | 1.0 | 0.6667 | 0.9473 | 1.0 | ok |
| drop_discount_code | grep_baseline | 0.4 | 0.4 | 0.4 | 1.0 | 0.4 | 0.7123 | 0.0 | missed |
| rework_get_discount | tracegraph | 0.8571 | 1.0 | 0.9231 | 1.0 | 1.0 | 0.7983 | 1.0 | ok |
| rework_get_discount | grep_baseline | 0.6667 | 0.3333 | 0.4444 | 1.0 | 0.0 | 0.3422 | 1.0 | ok |
| tenant_name_nullable | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| tenant_name_nullable | grep_baseline | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | missed |
| rename_get_discount | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9907 | 1.0 | ok |
| rename_get_discount | grep_baseline | 0.6667 | 0.2222 | 0.3333 | 0.4 | 0.6667 | 0.314 | 0.0 | missed |
| orders_region_not_null | tracegraph | 0.8 | 1.0 | 0.8889 | 1.0 | 0.3333 | 0.8437 | 1.0 | ok |
| orders_region_not_null | grep_baseline | 0.2222 | 0.5 | 0.3077 | 1.0 | 0.1111 | 0.468 | 0.0 | missed |
| total_becomes_text | tracegraph | 0.8889 | 1.0 | 0.9412 | 1.0 | 1.0 | 0.9523 | 1.0 | ok |
| total_becomes_text | grep_baseline | 0.5714 | 0.5 | 0.5333 | 1.0 | 0.2857 | 0.5738 | 0.0 | missed |
| discount_raises | tracegraph | 0.8571 | 1.0 | 0.9231 | 1.0 | 1.0 | 0.9309 | 1.0 | ok |
| discount_raises | grep_baseline | 0.6667 | 0.3333 | 0.4444 | 0.0 | 0.0 | 0.2627 | 0.0 | ok |
| order_response_contract | tracegraph | 0.3333 | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| order_response_contract | grep_baseline | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 0.0 | ok |
| remove_describe_status | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9816 | 1.0 | ok |
| remove_describe_status | grep_baseline | 0.5 | 0.3333 | 0.4 | 0.5 | 0.5 | 0.5317 | 1.0 | missed |
| rename_calculate_total | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9938 | 1.0 | ok |
| rename_calculate_total | grep_baseline | 0.6667 | 0.2857 | 0.4 | 0.4 | 0.6667 | 0.3434 | 0.0 | missed |
| drop_tenant_name | tracegraph | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | ok |
| drop_tenant_name | grep_baseline | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | missed |

| metric | tracegraph | grep_baseline |
| --- | --- | --- |
| precision | 0.8766 [0.7894, 0.934] | 0.4803 [0.3458, 0.6087] |
| recall | 1.0 [1.0, 1.0] | 0.538 [0.4113, 0.6682] |
| f1 | 0.9247 [0.8607, 0.964] | 0.3938 [0.2859, 0.5083] |
| breaks_recall | 0.9706 [0.9118, 1.0] | 0.8118 [0.6588, 0.9412] |
| breaks_precision | 0.9118 [0.7941, 1.0] | 0.2799 [0.1541, 0.4] |
| ndcg@10 | 0.954 [0.9246, 0.9777] | 0.6057 [0.4837, 0.729] |
| obligation_recall | 1.0 [1.0, 1.0] | 0.1765 [0.0, 0.3529] |
| hole_tasks_reported | 4 | 0 |

Wilcoxon signed-rank on f1 (baseline vs tracegraph): n=17, W+=145.0, p=0.0013

Wilcoxon signed-rank on breaks_recall (baseline vs tracegraph): n=4, W+=10.0, p=0.1003
