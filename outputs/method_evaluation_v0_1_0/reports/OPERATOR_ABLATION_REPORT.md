# Prespecified operator ablation report

Contract: `contracts/OPERATOR_ABLATION_CONTRACT_v1.0_2026-08-05.md`.
All variants were specified before the aggregate queries and are retained regardless of result.

## Main findings

1. Exact identity is consequential: relaxing same-POE identity to same-class/window added 56,465 converted order units (170,890 to 227,355).
2. Time is an independent dimension: A2 hospital-overlap eligibility added 121 order-exposed patients (655 to 776), while strict administration remained a distinct 521-patient representation in that paired analysis.
3. A1 is a construct-measurability demonstration: route is required by the prophylactic construct but absent in the evaluated administration layer, so all 20,248 A1 analysis units are classified unmeasurable under the route-required operator—not unexposed.
4. Table-only and collapsed-semantic comparators classify more patients than the literal exact-identity operator; their counts are reported below as deliberate naive baselines, not candidate replacements.
5. Downstream association estimates can be exposure-sensitive: the already-frozen A1 broad comparator crosses the null direction relative to the order estimate, whereas the exact-identity pair is close; A2 identity and window changes alter magnitude without supporting a new causal conclusion.

## Baseline and full-operator counts

| Anchor | Operator | Status | Exposed | Unexposed | Unresolved | Unmeasurable |
|---|---|---|---:|---:|---:|---:|
| A1 | table-only | measurable=TRUE, executable=TRUE | 12,950 | 7,298 | 0 | 0 |
| A1 | source+class+window | measurable=TRUE, executable=TRUE | 12,362 | 7,886 | 0 | 0 |
| A1 | collapsed event semantics | measurable=TRUE, executable=TRUE | 12,722 | 7,526 | 0 | 0 |
| A1 | full exact-identity operator | measurable=TRUE, executable=TRUE | 5,538 | 14,710 | 0 | 0 |
| A2 | table-only | measurable=TRUE, executable=TRUE | 1,061 | 1,752 | 0 | 0 |
| A2 | source+class+window | measurable=TRUE, executable=TRUE | 870 | 1,943 | 0 | 0 |
| A2 | collapsed event semantics | measurable=TRUE, executable=TRUE | 871 | 1,942 | 0 | 0 |
| A2 | full exact-identity operator | measurable=TRUE, executable=TRUE | 518 | 2,295 | 0 | 0 |
| A1 | route required | measurable=FALSE, executable=FALSE | 0 | 0 | 0 | 20,248 |
| A1 | route ignored / broad administration | measurable=TRUE, executable=TRUE | 12,362 | 7,886 | 0 | 0 |
| six_class_order_units | deployment gate retained | measurable=TRUE, executable=TRUE | 170,890 | 93,281 | 0 | 0 |
| six_class_order_units | deployment gate removed | measurable=PARTIAL, executable=TRUE | 218,981 | 414,100 | 0 | 0 |

## Reclassification metrics

| Anchor | Comparison | Agreement | Positive agreement | Negative agreement | Jaccard |
|---|---|---:|---:|---:|---:|
| A1 | full_strict_vs_table_only | 0.634 | 0.599 | 0.663 | 0.428 |
| A1 | full_strict_vs_source_class_window | 0.663 | 0.619 | 0.698 | 0.448 |
| A1 | full_strict_vs_collapsed_semantics | 0.645 | 0.607 | 0.677 | 0.435 |
| A2 | full_strict_vs_table_only | 0.807 | 0.656 | 0.866 | 0.488 |
| A2 | full_strict_vs_source_class_window | 0.875 | 0.746 | 0.917 | 0.595 |
| A2 | full_strict_vs_collapsed_semantics | 0.875 | 0.746 | 0.917 | 0.595 |
| A1 | exact_identity_vs_same_class | 0.663 | 0.619 | 0.698 | 0.448 |
| A2 | exact_identity_vs_same_class | 0.875 | 0.746 | 0.917 | 0.595 |
| A2 | original_order_vs_hospital_overlap_order | 0.951 | 0.903 | 0.967 | 0.823 |

## Interpretation boundary

The route-required operator returned 20,248 unmeasurable units. Treating these units as negative would be a category error. Event-semantic collapse is likewise a comparator only: `Flushed`, `Confirmed`, blank, and other states remain separate under the scientific operator.

A1/A2 ORs and HRs in the accompanying table are downstream measurement stress tests. They do not estimate medication benefit, harm, or an optimal treatment strategy. No P value was used to select a definition.
