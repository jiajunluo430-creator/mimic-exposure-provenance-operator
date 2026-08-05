# Prespecified operator ablation and parity contract v1.0

Frozen: 2026-08-05, before running the medprov ablation builder.  
Status: binding software/method evaluation addendum.  
Parent contracts: `analysis_contract_v1.0_2026-07-29.md` and
`UPGRADE_MASTER_CONTRACT_v1.0_2026-08-05.md`.

## 1. Purpose and invariant scientific definitions

This evaluation tests whether the new specification/compiler reproduces the
frozen analysis and quantifies what is lost when individual operator dimensions
are removed. It is not a new medication efficacy/safety study. The six drug
classes, name/RxNorm whitelist, A1/A2 cohorts, outcomes, covariates, models,
time windows, event semantics, and material-change thresholds remain frozen.
No ablation may be selected or redefined because of its empirical result.

## 2. Inputs and versions

- MIMIC-IV native reference release: 3.1.
- Frozen aggregate/materialized references:
  `n1_validity.duckdb`, `jamia_pre_submission_v1_0.duckdb`,
  `jamia_prereview_upgrade_v1_0.duckdb`, and
  `jamia_residual_provenance_v1_0.duckdb`.
- Frozen public aggregate tables under `outputs/`.
- Generated specifications under `examples/`, schema version 1.0.0.
- Analysis units: order cluster for six-class conversion; patient/stay unit for
  A1/A2; event unit only for semantic and metadata availability summaries.
- Integer outputs must match exactly. Continuous parity tolerance is
  `1e-10` absolute when the same stored estimate is read and `1e-6` when a
  deterministic aggregate is recomputed by a different engine/order.

## 3. Exact-parity gates

All of the following are required:

1. total post-deployment order units = 264,171;
2. strict same-POE conversions = 170,890;
3. same-class/window conversions = 227,355;
4. exact six-class order/strict/broad counts;
5. exact A1 original order/strict/broad cross-classification;
6. exact A2 original and hospital-overlap order/strict/broad
   cross-classification;
7. exact A1/A2 model input counts and equality to the frozen OR/HR table;
8. P2 trace: 183 primary units linked to raw POE; median prescription POE minus
   administration approximately +97.1833 hours, eMAR POE minus administration
   approximately -5.6833 hours, and paired role separation approximately
   106.1000 hours, subject to the stored-table tolerance above.

Any failure creates `PARITY_FAILURE_DIAGNOSTIC.md` and is localized to schema,
adapter, join, deduplication, time boundary, event mapping, or reference input.
Old outputs are never changed to force agreement.

## 4. Prespecified ablations and baselines

Every item is reported, including null, adverse, or non-executable results.

| ID | Comparison | Fixed operational change |
|---|---|---|
| ABL-01 | deployment gate | post-deployment full operator versus all-period order denominator; pre/overlap/post strata remain separate |
| ABL-02 | native identity | exact same-POE/class/stay identity versus same-class/stay/order-window identity |
| ABL-03 | time | A2 original eligible-order ICU window versus the already-frozen hospital-overlap order window |
| ABL-04 | event semantics | literal four-way mapping versus a collapsed map in which only `not_given`, `held`, and `refused` are negative and every other nonempty/blank class-matched eMAR row is treated as positive; this is a deliberately naive comparator, never a replacement definition |
| ABL-05 | required metadata | A1 administration construct with route required versus route ignored; dose-metadata-constrained broad exposure is retained as the already-frozen sensitivity |
| BASE-01 | table-only | any frozen class-name match in the selected source during the admission/stay assignment envelope, ignoring native identity, literal event state, and required metadata |
| BASE-02 | source+class+window | any strict-positive class-matched administration in the frozen clinical window, without exact native order identity or required route/dose |
| FULL-01 | full operator | source observability + exact identity + frozen time + literal event semantics + required construct metadata |

The collapsed comparator intentionally demonstrates why a table row is not an
administration. `Flushed`, `Confirmed`, blank, and other states remain separate
in the scientific analysis even if the comparator collapses them.

## 5. Metrics

For each applicable comparison, report:

- syntactic validity, adapter support, measurability, and executability;
- exposed, unexposed, unresolved, and unmeasurable counts;
- paired 2x2 reclassification cells;
- overall agreement, positive agreement, negative agreement, and positive
  Jaccard, computed only from a retained paired aggregate matrix;
- event-time displacement median/IQR when both definitions retain comparable
  onsets;
- route/dose/state metadata availability and retention;
- frozen A1/A2 downstream estimate and delta-log drift when the exact already-
  fitted model exists;
- explicit failure-reason distribution.

Positive agreement is `2a/(2a+b+c)`, negative agreement is
`2d/(2d+b+c)`, and positive Jaccard is `a/(a+b+c)` for paired cells
`a=both positive`, `b=left positive/right negative`,
`c=left negative/right positive`, and `d=both negative`.

Metrics not recoverable from retained aggregate evidence are labeled
`NOT_EVALUABLE_AGGREGATE_NOT_RETAINED`; they are not imputed. No patient-level
row is written to the public release.

## 6. Interpretation and stop rules

- Exact parity is a software validity gate, not evidence of clinical validity.
- A non-executable required-metadata operator is a positive measurability
  finding, not a zero exposed count.
- Ablations describe classification/estimate propagation, not causal effects.
- No new drug class, window, subgroup, semantic mapping, or model may be added
  to seek a larger contrast.
- If parity fails, downstream method reporting continues only with a prominent
  failure label; no parity claim is permitted.
- The prior long-running join remains an implementation failure audit and is
  never relabeled a statistical failure.
