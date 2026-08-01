# JAMIA observability extension and calendar-alignment repair v1.0

Frozen: 2026-07-30, after completion of the original frozen analysis and
post-primary descriptive layer, and after a read-only diagnostic identified
that the existing `anchor_era` implementation used the patient
`anchor_year_group` without aligning each ICU stay to `anchor_year`.

Status: **binding before any corrected-era or post-implementation outcome
model**.

This document does not replace the 2026-07-29 frozen contract, medication
whitelist, event semantics, exposure windows, analysis units, anchor cohorts,
covariates, outcomes, or material-effect-change thresholds. Original outputs
remain preserved as an implementation-history snapshot.

## 1. Purpose and transparency boundary

The extension tests a methods-focused sequence suitable for a JAMIA
Research and Applications article:

1. whether the administration layer was observable for a given period;
2. whether residual order-to-documented-administration discordance remained
   after the eMAR implementation period;
3. whether that residual discordance propagated to the two already frozen
   published-style effect estimates.

The extension was motivated after the original results were known. It is a
versioned implementation repair plus post-primary sensitivity analysis, not a
claim of preregistration. No result from the corrected-era outcome models has
been inspected at the time of this freeze.

## 2. Stay-level calendar alignment

MIMIC-IV provides one shifted `anchor_year` and one three-year
`anchor_year_group` per patient. Each ICU stay must be aligned to the anchor
year using its own `intime`.

For every ICU stay:

- `anchor_group_start` is the first four-digit year in
  `anchor_year_group`;
- `anchor_group_end` is the final four-digit year in
  `anchor_year_group`;
- `stay_year_delta = year(intime) - anchor_year`;
- `stay_year_low = anchor_group_start + stay_year_delta`;
- `stay_year_high = anchor_group_end + stay_year_delta`;
- `stay_year_midpoint = anchor_group_start + 1 + stay_year_delta`.

The corrected adjustment variable retains the original three broad eras but
uses the stay-aligned midpoint:

- `2008-2013` when `stay_year_midpoint <= 2013`;
- `2014-2019` when `stay_year_midpoint` is 2014 through 2019;
- `2020-2022` when `stay_year_midpoint >= 2020`.

This is an implementation repair of the already frozen anchor-era covariate,
not a new covariate or subgroup selected by outcome results.

## 3. eMAR deployment eras

The official MIMIC-IV documentation states that eMAR was implemented during
2011-2013. To avoid pretending that a three-year interval supplies an exact
calendar year, deployment eras use the full stay-aligned interval:

- `pre_implementation`: `stay_year_high <= 2010`;
- `implementation_overlap`: every interval not classified as pre or post;
- `post_implementation`: `stay_year_low >= 2014`.

The original all-period estimands remain the frozen primary analyses.
Deployment-era results are labeled post-primary observability analyses.

## 4. Observability measures

The primary infrastructure measure is the proportion of adult ICU stays whose
hospital admission has at least one row anywhere in the complete eMAR table,
reported by deployment era. This is an admission-level data-availability
proxy, not proof that every ordered medication could have been documented.

`any_emar_in_admission` is used only for:

- descriptive coverage;
- conversion and reclassification sensitivity tables.

It must not be used to select the primary post-implementation outcome-model
cohort because conditioning on the presence of any medication administration
record could select on medication intensity, severity, or workflow.

## 5. Frozen post-implementation analyses

All analyses retain the six medication classes, strict whitelist, event
semantics, order unit, POE identity rule, conversion window, lag exclusions,
not-given denominator, two anchor cohorts, outcomes, covariates, and model
families from the original contract.

The complete extension reports, without result-based suppression:

1. adult-stay eMAR observability by deployment era;
2. conversion and first-dose lag by all six classes and deployment era;
3. primary and audit-semantic not-given proportions by all six classes and
   deployment era;
4. the original not-given model with corrected stay-level era in:
   - the complete original cohort;
   - the post-implementation cohort;
5. complete exposure cross-classification for A1 and A2 by deployment era;
6. every already frozen A1/A2 model variant with corrected era in:
   - the complete original cohort;
   - the post-implementation cohort.

Within every paired anchor model, cohort, outcome, covariates, missingness
handling, and follow-up remain identical between the order-defined and
documented-administration-defined fits.

## 6. JAMIA promotion and stop-loss rules

The original material-change rule remains binding:

- direction reversal; or
- absolute log-effect change at least `log(1.25)`; or
- relative absolute log-effect change at least 25%.

JAMIA promotion requires all of the following:

1. calendar reconciliation and row-count gates pass;
2. all six classes remain represented post implementation;
3. both post-implementation anchor pairs contain at least 500 patients and
   converge under both exposure definitions;
4. same-cohort verification passes for every paired fit;
5. at least one post-implementation published-style anchor meets the original
   material-effect-change rule.

If gates 1-4 pass but gate 5 does not, the decision is **BACKUP**: retain the
observability/fidelity findings and target PDS rather than adding drug classes,
anchors, windows, or models.

The decision is **NO-GO for JAMIA**, but not a scientific failure, if calendar
alignment cannot be reconciled, both post-implementation anchor cohorts are
below 500, paired definitions cannot use identical cohorts, or identity
linkage is corrupted.

No significance-based selection is permitted.

## 7. Claim boundary

Allowed:

- eMAR observability varied across the data-generation period;
- pooled order-to-administration conversion combined infrastructure
  availability with residual workflow and semantic discordance;
- post-implementation discordance persisted or attenuated by the measured
  amount;
- exposure reclassification changed or did not materially change paired
  estimates under the frozen rule.

Forbidden:

- eMAR as clinical truth, ingestion, or biological exposure;
- attribution of every nonconversion to a withheld dose;
- causal drug efficacy or safety conclusions;
- external validation using eICU;
- claims that the provenance layers form a strictly nested hierarchy;
- a scalar exposure-fidelity score;
- nomograms, prediction models, machine learning, or SHAP;
- presenting this post-primary extension as prospectively preregistered.

## 8. Output isolation

All new files must remain under:

`<PROJECT_ROOT>`

New tables, model inputs, logs, and manifests are written under
`outputs/jamia_observability/`. New reports are prefixed `12_` or later.
Existing PDS submission assets are not overwritten until the corrected
analysis passes validation and a separate manuscript-revision decision is
recorded.
