# eICU adapter contract v1.0

Frozen: 2026-08-05, before streaming the eICU v2.0 source files.

## Purpose and boundary

This evaluation asks which frozen medication-exposure provenance dimensions are observable across eICU hospitals and whether same-class/window reconciliation is feasible. eICU has no MIMIC eMAR-equivalent layer or native medication-to-infusion cross-source key. Results are capability and transportability evidence, not external validation and not outcome-effect replication.

## Frozen data and classes

- Data: local read-only `eicu-collaborative-research-database-2.0.zip`.
- Classes: the same six frozen classes and strict-tier label rules in `config/drug_class_whitelist_v1.0.csv`.
- No class, label, negative regex, threshold, or time window may change after inspecting counts.
- Source files are streamed from the ZIP; no patient/stay rows enter the release.

## Frozen source semantics

- `medication`: order/planned-start-like evidence only.
- `infusionDrug`: administration-like only when all are true: a strict drug-specific label match; valid `patientunitstayid`; valid numeric `infusionoffset`; and at least one strictly positive numeric value among `drugrate`, `infusionrate`, `drugamount`, or `volumeoffluid`.
- `treatment`: documentation-only capability; it cannot establish order or administration.
- `intakeOutput`: excluded from medication exposure because no additional frozen construct has been specified.
- A record satisfying no positive administration-like value is unresolved, not not-given.

## Frozen analysis units

- Order unit: unique `medicationid` after class mapping, with duplicate rows collapsed by `medicationid`.
- Administration-like event: unique `infusiondrugid` after class mapping and numeric gate.
- Reconciliation unit: `patientunitstayid` by drug class by order unit.
- Hospital is mapped through `patient.patientunitstayid -> patient.hospitalid`; unit type is retained for aggregate heterogeneity reporting.

## Frozen timing and reconciliation

- Order interval start: `drugstartoffset` when numeric, otherwise `drugorderoffset` when numeric.
- Order interval stop: numeric `drugstopoffset` only when it is not earlier than the chosen start.
- A time-valid order requires both valid start and valid stop. No stop time is imputed.
- An administration-like event reconciles to an order only when it has the same stay and class and its `infusionoffset` lies in `[order_start - 120 minutes, order_stop + 360 minutes]`.
- More than one qualifying order is resolved to the closest nonfuture start; ties remain unresolved.
- This is explicitly `same_class_window`, never exact identity validation.

## Frozen feasibility gate, evaluated separately by class

Reclassification is run only if all are met:

1. at least 100 unique time-valid order units;
2. at least 100 administration-like events;
3. at least 10 hospitals with both an eligible order and administration-like evidence;
4. at least 80% of class-mapped order units have a valid start and stop;
5. identity mapping is unambiguous under the frozen strict label rules.

Failure of a class gate is a capability result and cannot be rescued by adding classes or relaxing rules.

## Frozen outputs

- Source observability, row and unique-unit counts.
- Completeness of order/start/stop offset, route, dose, rate/value, and frequency.
- Identity vocabulary and label mapping coverage.
- Native cross-source key availability (`false` by design).
- Feasibility gate results by class.
- If a class passes: order-to-administration-like conversion, unmatched and unresolved proportions, first time displacement, and hospital-level heterogeneity.
- Hospital/unit cells with fewer than 10 analysis units are suppressed; no patient or stay identifiers are released.
- No outcome models are fit.

## Interpretation

Variation across hospitals is interpreted as interface/source observability heterogeneity. It is not evidence of clinical quality, adherence, effectiveness, or safety.
