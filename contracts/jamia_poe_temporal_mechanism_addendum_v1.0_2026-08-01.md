# JAMIA POE temporal-mechanism addendum v1.0

**Frozen:** 2026-08-01, before inspection of `order_type`,
`transaction_type`, discharge-relative timing, or discontinuation-chain
results.

## Purpose

Explain the already observed A2 residual in which native
`emar.pharmacy_id` links documented PPI administrations to PPI prescription
rows, while the prescription POE identity differs from the eMAR POE identity
and the linked POE `ordertime` follows administration. This is a diagnostic
extension of the frozen residual-provenance audit. It does not change an
exposure operator, cohort, endpoint, window, whitelist, estimand, model, or
published anchor.

## Frozen population

- Start from the existing 184 A2 residual stays and their 399 qualifying
  strict-positive PPI eMAR events.
- Restrict to the 183 stays with a native `emar.pharmacy_id` link to a mapped
  PPI prescription in `a2_residual_linked_prescription_rows`.
- Preserve the existing 256 distinct `(stay_id, prescription_row_id)` rows as
  the row-level replication denominator.
- Define the primary independent order unit as distinct
  `(subject_id, hadm_id, stay_id, pharmacy_id, prescription_poe_id)`. This
  collapses base/additive prescription rows that share one pharmacy/POE order.
  No drug-name, route, timing, or outcome criterion may be used to deduplicate.

## Frozen diagnostics

1. Link each primary order unit to raw `hosp/poe.csv.gz` by exact
   `(subject_id, hadm_id, prescription_poe_id)` and report linkage completeness
   before interpretation.
2. At both raw-POE-row and primary-order-unit levels, report the complete
   distributions of `order_type`, `order_subtype`, `transaction_type`, and
   `order_status`. Unit-level categories are deterministic sorted concatenations
   of all nonblank values observed for the linked POE identity.
3. For each primary order unit, use the earliest linked POE `ordertime` and
   report its timing relative to first linked eMAR administration, ICU entry,
   hospital admission, and hospital discharge. Report n, median, Q1, Q3,
   minimum, maximum, and these prespecified discharge-relative bins:
   `<-48 h`, `-48 to <-24 h`, `-24 to <0 h`, `0 to <=24 h`, and `>24 h`.
4. Report nonblank `discontinue_of_poe_id` and `discontinued_by_poe_id` at
   row and unit levels. Resolve referenced parent/child POE identities in raw
   POE where available, without recursively expanding beyond one edge.
5. Quantify the prescription-row multiplicity within each primary order unit,
   including the distribution of rows per unit and the drug/route combinations
   in units with more than one prescription row. This explicitly tests the
   base/additive split explanation for the 256-row count.
6. Produce `EXPLAIN` plans and a 20-unit limited test before the full join.
   Abort if a cross product/blockwise nested-loop join appears, if a join
   exceeds the prespecified multiplicity of the raw POE rows sharing the exact
   POE identity, or if any raw MIMIC source changes during execution.

## Interpretation rules

- A concentrated POE category or discharge-relative time pattern may be
  described as a documented mechanism signature, but not as proof of a
  clinical workflow that the available fields do not explicitly identify.
- `ordertime` after administration establishes timestamp non-equivalence; it
  does not establish whether the later entry was retrospective, reconciled,
  renewed, copied, or otherwise generated unless native POE fields support that
  label.
- Headline counts use the primary independent order unit. The 256
  prescription-row units remain visible only to reproduce the earlier audit
  and explain row multiplicity.
- No effect estimate will be selected, refitted, or reinterpreted as a causal
  medication effect.

## Planned outputs

- POE field distributions at raw-row and primary-order-unit levels;
- discharge- and administration-relative timing summaries and bins;
- discontinuation-link summaries;
- prescription-row multiplicity and multirow drug/route combinations;
- a one-row mechanism summary, query plans, checkpoint cardinalities, log,
  manifest, validation table, and Python session information;
- reporting-only updates to the research canon, evidence table, argument map,
  manuscript, Supporting Information, decision log, public reproducibility
  bundle, and first-submission package.
