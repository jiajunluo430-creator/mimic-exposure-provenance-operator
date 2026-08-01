# JAMIA pre-submission sensitivity addendum v1.0

**Frozen before generating the analyses defined below:** 31 July 2026

## Purpose and status

This addendum responds to an internal pre-submission methods review. It does
not replace the parent medication, semantic, window, cohort, covariate, model,
or material-change contracts. The original source-corrected v1.1 estimates
remain the prespecified primary analyses. Every analysis below is a
reviewer-motivated diagnostic or sensitivity analysis and must be labelled as
such.

The final deliverable remains a first-submission JAMIA package. No response to
reviewers or revision-labelled manuscript will be produced.

## S1. Anchor exposure-operator audit

The analytic cohorts, outcomes, covariates, and follow-up remain unchanged.
For each anchor, report the order operator and two administration operators.

### A1: VTE prophylaxis and in-hospital mortality

- Order-defined exposure: at least one frozen route/dose-eligible heparin or
  enoxaparin order assigned to the ICU stay, as in the primary analysis.
- Strict identity-linked administration: at least one qualifying strict-given
  eMAR event linked by the same `poe_id`, class, stay, and frozen conversion
  window to a qualifying A1 order, as in the primary analysis.
- Broad class-window administration: at least one strict-given VTE-class eMAR
  event during the ICU stay, without requiring POE identity or an eligible
  order. This deliberately broad operator is a linkage sensitivity analysis;
  it is not assumed to distinguish prophylactic from therapeutic use when
  administration route/dose fields are unavailable.

### A2: PPI exposure and 90-day mortality in the operational ICD-sepsis cohort

- Order-defined exposure: at least one frozen PPI order placed by 48 hours
  after ICU entry and active at ICU entry or thereafter, as in the primary
  analysis.
- Strict identity-linked administration: at least one strict-given PPI eMAR
  event linked to a qualifying A2 order by the same `poe_id`, class, stay, and
  frozen conversion window, with the event occurring by 48 hours.
- Broad class-window administration: at least one strict-given PPI eMAR event
  between ICU entry and 48 hours, without requiring a qualifying order, as in
  the primary analysis.

For both anchors, fit the frozen minimal and enriched models under strict and
broad administration operators. Report complete two-by-two exposure
cross-classifications and cell-specific outcome counts and risks. The broad
operator is not eligible to replace the primary operator solely because it
produces a preferred estimate.

## S2. A2 time-varying exposure diagnostic

- Time zero: ICU admission.
- Follow-up: the frozen 90-day follow-up.
- Order onset: the earliest qualifying PPI `ordertime`, falling back to
  prescription start time only if order time is unavailable. An order already
  active at ICU entry begins at time zero. Onset is truncated to the interval
  from 0 to 48 hours.
- Broad administration onset: the first strict-given PPI eMAR `charttime`
  between ICU entry and 48 hours.
- Strict administration onset: the first identity-linked qualifying PPI
  administration defined in S1.
- Patients remain unexposed until the applicable onset and exposed
  thereafter. Events before onset contribute only unexposed time.
- Fit start-stop Cox models using the frozen minimal and enriched covariates,
  Efron ties, and subject-clustered robust variance.

The time-varying result is a bias diagnostic. If the static exposure-source
difference materially contracts, the manuscript must foreground the temporal
assignment component rather than attribute the full difference to record
provenance.

## S3. Paired uncertainty and concordant subsets

- Perform 1,000 paired subject-level bootstrap resamples with seed 20260731.
- In each resample refit both source models on the same sampled subjects.
- Report the percentile 95% interval for
  `delta_log_effect = beta_administration - beta_order`.
- Apply this to the post-implementation primary A1 and A2 models and to the A2
  broad time-varying pair. Failed or nonconverged replicates are retained in
  the audit and excluded from percentile calculation; at least 950 successful
  paired replicates are required.
- Refit each frozen minimal model in the concordant subset (`both` plus
  `neither`) using the common binary exposure. This is descriptive and cannot
  identify a causal mechanism.

The frozen 25% relative-log-change rule remains a descriptive gate. Bootstrap
intervals are reported separately and do not retroactively select analyses.

## S4. Nonconversion mechanism audit

Population: all nonconverted post-implementation eligible order units under
the frozen strict identity-linked definition.

Each unit is assigned once, in the following fixed hierarchy:

1. **Cancellation/discontinuation evidence:** POE status or transaction text
   contains `cancel`, `discontinu`, `inactive`, or `dc`; a POE
   `discontinue_of_poe_id`/`discontinued_by_poe_id` is present; or pharmacy
   status contains `cancel`, `discontinu`, `inactive`, `stop`, or `dc`.
2. **Conditional/PRN/one-time protocol evidence:** pharmacy `sliding_scale`
   is affirmative; pharmacy frequency or POE order type/subtype contains
   `prn`, `as needed`, `once`, `one time`, `stat`, `sliding`, `conditional`,
   or `protocol`; or the frozen prescription field `doses_per_24_hrs` contains
   `prn` or `as needed`.
3. **Same-class event without qualifying identity link:** a strict-given eMAR
   event of the same drug class occurs within the original order-specific
   conversion window, but no qualifying strict identity-linked event exists.
4. **No same-class event in the frozen window:** none of the above and no
   strict-given same-class eMAR event occurs within the original window.

The categories describe available record evidence, not clinical
appropriateness, adherence, or true nonadministration. Report counts and
percentages overall and by the six frozen classes.

Also report a broad class-window conversion sensitivity. To prevent a
many-to-many join, eMAR strict-given times must first be aggregated to one
`stay_id × drug_class` row; each order is then tested against the aggregated
time list. The query plan must contain a bounded equality join and must not
contain a cross product or event-level many-to-many materialization.

## S5. Semantic three-state audit

For insulin, report mutually exclusive event states:

1. strict documented administration;
2. protocol-dependent nonindication, defined only by exact event text
   beginning `Not Given per Sliding Scale`;
3. other frozen not-given documentation, excluding state 2.

`Hold Dose`, `Flushed`, `Confirmed`, blank event text, and all other states
remain separately reported and outside this three-state denominator unless
already included by the parent primary definition. The manuscript must not
describe state 2 as a failed administration.

## S6. Precision, workflow heterogeneity, and calendar sensitivity

- Replace simple Wilson intervals for order-unit conversion with 1,000
  subject-cluster bootstrap percentile intervals, seed 20260731. Point
  estimates remain unchanged.
- Fit the frozen post-implementation not-given model separately in each of the
  six medication classes under primary and semantic-audit mappings. Report all
  class-specific coefficients; do not select by statistical significance.
- For A2, define three deidentification-aware calendar groups:
  `pre_2020_certain` when `stay_year_high <= 2019`, `crosses_2020_boundary`
  when the interval spans 2020, and `year_2020_plus_certain` when
  `stay_year_low >= 2020`. Fit the frozen minimal source models within all
  groups and an exposure-by-group interaction model. These are calendar
  sensitivity analyses, not exact COVID-status analyses.

## S7. Reporting additions without new outcome selection

- Add a complete participant flow from raw ICU stays to valid adult stays and
  through both anchor cohorts.
- State that the medication dictionary was frozen at RxNorm ingredient level;
  source-name regular expressions are implementation crosswalks, not the
  conceptual vocabulary.
- Provide a schema-translation table showing how the four audit stages can be
  represented with source-provenance fields such as OMOP
  `DRUG_EXPOSURE.drug_type_concept_id`. This is a conceptual mapping only and
  does not claim OMOP execution or external validation.
- Contextualize the PPI diagnostic against randomized critical-care evidence
  only as cross-design context. Do not call a trial estimate ground truth and
  do not infer PPI efficacy, safety, or causal validity from proximity to the
  null.

## Prohibited adaptations

- No additional drug classes or outcome anchors may be added after viewing
  the primary results.
- No replacement of the two prespecified anchors with more favorable or
  higher-impact examples.
- No eICU external-validation claim or expansion beyond the parent D004/D013
  interface-semantic boundary.
- No Sepsis-3 substitution without a separately frozen derivation contract and
  complete local derived inputs.
- No causal drug-effect conclusion, prediction model, ML, SHAP, nomogram, or
  significance-driven selection.
