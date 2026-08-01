# JAMIA prereview upgrade addendum v1.0

**Frozen before generating any result defined below:** 31 July 2026

## Purpose and status

This addendum responds to a second internal prereview of the clean first-
submission package. It preserves the parent contract, six medication classes,
name dictionaries, event semantics, anchor cohorts, outcomes, covariates, and
material-change rules. The original ICU-order-window analyses remain the
prespecified primary analyses. The analyses below are labelled diagnostic,
sensitivity, or reporting audits and cannot replace an unfavorable primary
result.

The final deliverable remains a clean first-submission JAMIA package. No
reviewer response, revision label, tracked-change file, or prereview text will
enter the submission archive.

## U1. A2 order-window decomposition

The A2 cohort, 90-day outcome, exclusions, and covariates remain unchanged.
In addition to the original order operator, construct a hospital-overlap order
sensitivity using strict PPI name mappings only.

A hospital-overlap order unit must:

- belong to the same `subject_id` and `hadm_id` as the index ICU stay;
- have a nonmissing `poe_id` that resolves to the same patient and admission;
- have prescription start at or before ICU entry plus 48 hours and stop at or
  after ICU entry; and
- have POE order time, or prescription start when POE time is unavailable, at
  or before ICU entry plus 48 hours.

No lower bound on POE order time is imposed, so an order placed on a ward more
than six hours before ICU entry can qualify if its prescription interval
overlaps the A2 exposure window. Deduplicate to one row per
`stay_id × PPI × poe_id`. A hospital-overlap order already active at ICU entry
has onset zero; otherwise onset is the later of ICU entry and prescription
start/POE order time.

Construct a hospital-overlap strict administration operator by linking a
strict-positive PPI eMAR event to one of these order units by the same
`subject_id`, `hadm_id`, `stay_id`, and `poe_id`, with the event between ICU
entry and the earlier of ICU entry plus 48 hours or ICU discharge. Retain the
unchanged broad same-class 48-hour administration operator.

Report the original order/strict/broad results and the hospital-overlap
order/strict/broad sensitivity side by side. Fit the same minimal and enriched
static and time-varying Cox models. For patients who are broad-administration
positive but original-order negative, assign one mutually exclusive provenance
category in this hierarchy:

1. same-POE hospital-overlap PPI order outside the original order window;
2. different-POE hospital-overlap PPI order in the admission;
3. eMAR POE missing or not identity-resolvable;
4. no hospital-overlap PPI order record in the admission.

The intended inference is to partition order-window coverage from POE-identity
resolution. Neither the original nor expanded operator is treated as
biological ground truth.

## U2. A1 administration metadata and provenance audit

Retain the original strict identity-linked and deliberately broad A1
administration operators. Add an available-metadata-constrained broad
sensitivity among strict-positive heparin/enoxaparin eMAR events during the ICU
stay:

- if route is present, it must match subcutaneous, SC, or SQ notation; missing
  route does not exclude an event;
- if both numeric administered dose and unit are present, UFH must be 5000
  units per dose and enoxaparin must be 20–60 mg per dose; missing dose or unit
  does not exclude an event; and
- frozen negative name expressions remain in force.

Report, by all six classes and specifically for A1, event-level availability of
`dose_given`, dose unit, and route. This arm tests what can be recovered from
available administration metadata; it is not called fully route/dose eligible
when either field is missing.

For the first broad A1 event in every original administration-only patient,
report medication, metadata availability/pass status, eMAR POE resolvability,
same-POE VTE prescription evidence in the admission, any VTE prescription in
the ICU stay, and any VTE prescription in the admission. Assign one mutually
exclusive provenance category in this hierarchy:

1. observed route or dose inconsistent with the frozen prophylaxis rule;
2. same-POE VTE prescription present but outside original A1 eligibility;
3. different-POE VTE order assigned to the ICU stay;
4. VTE prescription present elsewhere in the admission;
5. eMAR POE missing or not identity-resolvable;
6. no mapped VTE prescription record in the admission.

Complete outcome cells and minimal/enriched effects are reported for the new
metadata-constrained operator. If route observability is insufficient, that is
reported as a source-schema finding rather than repaired by name or window
expansion.

## U3. Coding asymmetry and RxNorm-reference validation

Correct manuscript wording to state that source strings are matched by frozen
regular expressions annotated to RxNorm ingredient concepts; MIMIC-IV does not
natively expose an RxCUI in the audited medication tables.

Audit nonzero NDC availability among name-mapped prescription rows by the six
classes. eMAR schema availability of standardized drug codes is reported
separately. NDC is not used to redefine any exposure.

For an external terminology check, query the official RxNav NDC service for
unique nonzero NDCs in descending row-frequency order until either 95% of
NDC-bearing mapped prescription rows is covered or 2000 unique NDCs have been
queried. Report API mapping success and agreement between the returned RxNorm
ingredient/class and the frozen name-derived ingredient/class among
successfully mapped rows. Unmapped or obsolete NDCs are an availability
category, not assumed disagreements. Preserve the raw query date, endpoint,
status, response, and code-level counts.

## U4. Structured published-operator landscape audit

Search PubMed through 31 July 2026 using the frozen query:

`("MIMIC-IV"[Title/Abstract]) AND (drug[Title/Abstract] OR medication[Title/Abstract] OR pharmaco*[Title/Abstract] OR antibiotic*[Title/Abstract] OR insulin[Title/Abstract] OR anticoag*[Title/Abstract] OR heparin[Title/Abstract] OR "proton pump"[Title/Abstract] OR PPI[Title/Abstract])`

Include English original observational MIMIC-IV studies in which a patient-
level medication variable defines an exposure group or time-varying exposure
for an association with a clinical outcome. Exclude prediction-only studies,
medication-error/reconciliation studies without an exposure-outcome estimate,
pure utilization descriptions, non-MIMIC-IV analyses, reviews, protocols, and
studies whose MIMIC-IV medication implementation cannot be separated.

Code every eligible open full text when 40 or fewer are found. If more than 40
are eligible, select 40 by a reproducible simple random sample with seed
20260731. Target at least 20 studies. Code source table, identity/linkage rule,
time origin/window, event semantics, route/dose criteria, and whether enough
detail is reported to reproduce the exposure operator. Unreported dimensions
remain `not reported`; they are never inferred to be broad. Report only
descriptive proportions for this structured sample and do not call it a
systematic review or a prevalence estimate for all MIMIC studies.

## U5. Paired uncertainty and model reporting

Use 1000 paired subject-level bootstrap resamples with seed 20260731 and a
minimum of 950 successful paired fits. Every minimal or enriched anchor-model
comparison promoted to a main or supporting results table receives a paired
percentile interval for
`beta_administration − beta_order`, with the applicable order operator held
fixed. This includes original strict and broad comparisons, A1
metadata-constrained broad comparison, and A2 hospital-overlap strict/broad
static and time-varying comparisons. Failed replicates remain auditable.

Move the four original concordant-subset minimal estimates into the main
operator table. Provide all 60 prespecified class-specific workflow estimates
in a supporting forest plot and state that they are descriptive and not
multiplicity-selected.

## U6. Calendar and materiality wording

Report point estimates and confidence intervals for the certainly pre-2020 and
certainly 2020-or-later A2 calendar strata. Interaction tests are described as
low-power diagnostics that cannot exclude a period effect. They are not used
as evidence of no COVID-era influence.

The frozen 0.87–1.15 effect-size gate applies only to the prespecified OASIS
severity association. For insulin night shift, describe the semantic-audit OR
of 1.034 as attenuated into a near-null range, not as a clinically meaningful
reversal.

## U7. Sepsis-3 and OMOP feasibility boundary

Before attempting Sepsis-3 or OMOP execution, inventory local inputs. A
Sepsis-3 sensitivity may run only from a complete, versioned official derived
table or from a separately frozen complete derivation; a partial proxy is
prohibited. OMOP execution may be claimed only if a local versioned ETL and
`DRUG_EXPOSURE` output are actually available. If these inputs are absent,
record nonexecution as a feasibility boundary and retain transparent ICD-
sepsis and conceptual OMOP wording without treating absence as a scientific
negative result.

## Prohibited adaptations

- Do not alter or replace the original six classes, frozen windows, event
  semantics, two anchors, outcomes, or primary estimates.
- Do not select literature studies, NDCs, operators, or model rows because
  their results support the preferred story.
- Do not infer a causal drug effect, true ingestion, or universal superiority
  of order or administration records.
- Do not call eICU an external validation or an unexecuted OMOP mapping an
  implementation.
- Do not add prediction, machine learning, SHAP, a nomogram, or new outcome
  anchors.
