# JAMIA observability source correction v1.1

Frozen: 2026-07-30, after the v1.0 observability outputs were inspected but
before any result using the corrected 2014–2016 eMAR deployment interval was
generated or inspected.

Status: **binding source correction before v1.1 pre-model extraction and
outcome modeling**.

This document supersedes only Section 3 (eMAR deployment eras) of
`jamia_observability_addendum_v1.0_2026-07-30.md`. It does not change the
2026-07-29 primary analysis contract, medication classes, name whitelists,
event semantics, exposure windows, analysis units, anchor cohorts, outcomes,
covariates, model families, or material-effect-change threshold.

## 1. Reason for the correction

The v1.0 addendum incorrectly stated that the MIMIC-IV eMAR system was
implemented during 2011–2013. That interval is one of the MIMIC-IV
`anchor_year_group` values, not the documented eMAR deployment interval.

The MIMIC-IV data descriptor states that the barcode eMAR system was deployed
throughout Beth Israel Deaconess Medical Center during 2014–2016 and that all
units had deployment by 2016:

Johnson AEW, Bulgarelli L, Shen L, et al. MIMIC-IV, a freely accessible
electronic health record dataset. *Scientific Data*. 2023;10:1.
doi:10.1038/s41597-022-01899-x.

The correction is therefore source-driven. It was not selected because of the
direction, magnitude, or statistical significance of a v1.1 result. No v1.1
result existed when this document was frozen.

## 2. Corrected deployment-era definitions

Stay-level calendar alignment remains exactly as specified in v1.0:

- `stay_year_delta = year(intime) - anchor_year`;
- `stay_year_low = anchor_group_start + stay_year_delta`;
- `stay_year_high = anchor_group_end + stay_year_delta`;
- `stay_year_midpoint = anchor_group_start + 1 + stay_year_delta`.

Because MIMIC-IV supplies a three-year interval rather than an exact calendar
year, deployment eras use the entire aligned interval:

- `pre_implementation`: `stay_year_high <= 2013`;
- `implementation_overlap`: every interval not classified as pre or post;
- `post_implementation`: `stay_year_low >= 2017`.

These definitions prevent an interval overlapping 2014–2016 from being called
pre- or post-implementation.

## 3. Analytic boundary

The original all-period estimates remain the primary frozen analyses. The
v1.1 post-implementation analyses are post-primary observability
sensitivities. They must retain every analytic definition in Sections 4–7 of
the v1.0 addendum, including:

- all six frozen medication classes;
- strict name whitelists and event semantics;
- the frozen order unit, POE identity rule, and conversion window;
- the frozen first-dose lag exclusions and not-given denominator;
- both published-style anchor cohorts and every already fitted model variant;
- identical cohorts, outcomes, covariates, missingness handling, and follow-up
  within each order-versus-administration model pair;
- no `any_emar_in_admission` filter in an outcome-model cohort;
- no causal drug-effect claim and no eICU external-validation claim.

## 4. Promotion and stop-loss rule

The v1.0 JAMIA promotion rule remains binding. JAMIA promotion requires:

1. calendar and full-eMAR reconciliation;
2. all six classes represented after 2016;
3. both post-implementation anchor pairs containing at least 500 patients and
   converging under both exposure definitions;
4. same-cohort verification for every paired fit;
5. at least one post-implementation published-style anchor meeting the frozen
   material-change rule.

If gates 1–4 pass but gate 5 does not, the decision is **BACKUP_PDS**. No drug
class, anchor, time window, event semantic, covariate, or model may be added to
recover a JAMIA-positive result.

## 5. Versioned output isolation

The v1.0 outputs and their analytic validation are retained unchanged as an
implementation-history snapshot under:

`outputs/jamia_observability/`

All v1.1 tables, model inputs, logs, and manifests must be written under:

`outputs/jamia_observability_v1_1/`

The v1.0 deployment-era outputs must be described as a source-definition
implementation failure, not as a statistical failure.
