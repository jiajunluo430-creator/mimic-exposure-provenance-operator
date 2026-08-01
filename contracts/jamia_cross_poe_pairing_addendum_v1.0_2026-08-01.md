# JAMIA cross-POE pairing addendum v1.0

**Frozen:** 2026-08-01, after the prescription-POE field audit but before
inspection of raw eMAR-POE timing or paired POE-chain results.

## Purpose and boundary

The frozen POE temporal-mechanism audit established that the 256 linked PPI
prescription rows collapse to 183 independent `(stay_id, pharmacy_id,
prescription_poe_id)` units; all linked prescription POEs are `Medications /
New`, and their timestamps follow documented administration but do not cluster
at discharge. This addendum tests the remaining native-key explanation: whether
the eMAR POE identifies an earlier POE node while the same `pharmacy_id` points
to a later prescription/pharmacy POE node.

This remains a reporting-only diagnostic. It does not change any frozen
exposure, cohort, window, whitelist, outcome, model, or estimand.

## Frozen units and joins

- Begin with the 183 primary order units from the POE temporal-mechanism audit.
- Within each unit, enumerate every distinct nonblank `emar_poe_id` from the
  already frozen native `pharmacy_id`-linked residual rows.
- Link eMAR POEs and prescription POEs separately to raw `hosp/poe.csv.gz` by
  exact `(subject_id, hadm_id, poe_id)` equality. Report linkage and
  multiplicity before interpretation.
- Link each eMAR POE to mapped prescription and raw pharmacy records elsewhere
  in the same admission by exact POE equality; report whether the resolved
  `pharmacy_id` equals or differs from the eMAR event's recorded
  `pharmacy_id`.

## Frozen diagnostics

1. Paired counts of unique eMAR POEs and prescription POEs per primary unit.
2. For both POE roles, complete `order_type`, `transaction_type`, and
   `order_status` distributions.
3. Earliest POE `ordertime` relative to first linked administration and the
   paired difference `prescription-POE ordertime minus eMAR-POE ordertime`,
   summarized by n, median, Q1, Q3, minimum, and maximum.
4. Cross-reference checks for either POE naming the other in
   `discontinue_of_poe_id` or `discontinued_by_poe_id`.
5. Exact-POE prescription/pharmacy resolution for eMAR POEs, including
   same-versus-different `pharmacy_id`.
6. `EXPLAIN` and a 20-unit pilot must precede the full raw POE scan. Cross
   products and blockwise nested-loop joins are forbidden. Raw source size and
   modification time must be identical before and after execution.

## Interpretation rules

- An earlier eMAR POE plus a later pharmacy/prescription POE under the same
  eMAR-recorded `pharmacy_id` may be described as cross-layer POE reassignment
  or non-equivalence. It may not be labeled retrospective entry, renewal,
  medication reconciliation, or copied-forward ordering unless native fields
  explicitly establish that mechanism.
- If no direct POE-chain reference exists, state that the mismatch mechanism is
  localized to cross-layer identifiers/timestamps but its generating workflow
  remains unresolved.
- All outputs must be aggregate and patient-free outside the internal DuckDB
  cache.
