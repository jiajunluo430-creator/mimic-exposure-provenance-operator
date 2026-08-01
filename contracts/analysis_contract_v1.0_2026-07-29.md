# Frozen analysis contract v1.0

Frozen: 2026-07-29, before any MIMIC medication-result scan or outcome model.

Status: **binding**. Any implementation defect may be repaired without changing
scientific definitions. Any scientific amendment requires a dated addendum,
must preserve the original result, and cannot be justified by statistical
significance.

## 1. Scientific objective and claim boundary

The project estimates measurement disagreement between medication intent
(orders) and documented delivery (eMAR administration). It asks whether that
measurement disagreement changes the direction or magnitude of two
prespecified, already-published MIMIC-IV associations.

Allowed claims:

- order-to-administration conversion, delay, and non-administration patterns;
- associations of held/not-given events with prespecified severity, shift, and
  organ-support variables;
- change in an already-published association when exposure is redefined.

Forbidden claims:

- causal efficacy, harm, optimal treatment, dose recommendation, or treatment
  threshold for any drug;
- selecting a drug class, association, window, subgroup, or model because its
  P value is favorable;
- nomograms, machine learning prediction, SHAP, or outcome-driven feature
  selection.

## 2. Immutable sources and identity rules

- MIMIC-IV 3.1 source root is read-only:
  `${MIMIC_IV_ROOT}`.
- eICU-CRD 2.0 source ZIP is read-only:
  `${EICU_ZIP}`.
- Every derived file must be under
  `<PROJECT_ROOT>`.
- MIMIC identity uses native `subject_id`, `hadm_id`, `stay_id`, `poe_id`,
  `pharmacy_id`, `emar_id`, and `emar_seq`. No inferred identifier is allowed.
- A hospital order intersecting multiple ICU stays is assigned once: to the ICU
  stay containing `ordertime`; if placed during the six hours before an ICU
  entry and active at entry, to that first intersecting ICU stay.

## 3. Frozen medication classes

The authoritative ingredient/RxNorm/name definitions are
`config/drug_class_whitelist_v1.0.csv`. They were obtained independently of
MIMIC result counts. RxNorm CUIs were checked through the US National Library
of Medicine RxNav API on 2026-07-29. MIMIC has no native RxCUI field in these
tables, so raw matching uses the frozen case-insensitive name regular
expressions; RxCUIs are a semantic reference.

All six classes are retained regardless of significance or conversion rate:

1. stress-ulcer prophylaxis agents;
2. pharmacologic VTE prophylaxis agents relevant after GI bleeding;
3. agents commonly used for intra-abdominal infection;
4. electrolyte replacement;
5. prokinetic agents;
6. insulin.

Strict and broad/sensitivity tiers are both frozen now. The broad tier can only
be reported as labeled sensitivity; it cannot replace a failed strict result.
Antibiotic inclusion denotes an agent set, not proof of an intra-abdominal
indication. Prokinetic erythromycin is broad/sensitivity because indication
cannot be inferred from the name alone.

## 4. Order and administration definitions

### 4.1 Order-defined event

Primary order source is `hosp/prescriptions`, joined to `hosp/poe` by native
`poe_id` and to ICU stays by hospital admission and time. A qualifying order:

- matches the strict frozen name whitelist;
- has a nonmissing `poe_id` linked to a POE row for the same subject/admission;
- has an order time during the ICU stay or in the six hours before ICU entry
  while its prescription interval overlaps the ICU stay;
- is not a discontinued/cancelled-only POE transaction before becoming active.

Order identity is one row per `stay_id × drug_class × poe_id`; prescription
revisions and multiple pharmacy rows do not multiply the denominator. Orders
without a valid POE link are audited separately and excluded from the primary
conversion denominator. A sensitivity denominator uses
`stay_id × drug_class × pharmacy_id` when POE is absent; it cannot replace the
primary.

For VTE prophylaxis, strict orders require subcutaneous route and the frozen
prophylactic-dose rule in the whitelist. Heparin flush/lock, dialysis,
continuous therapeutic infusion, ECMO/Impella, and line-maintenance products
are excluded. For the other five classes, route/dose restrictions in the
whitelist are applied where specified.

### 4.2 Administration-defined event

Primary administration source is `hosp/emar`, linked to
`hosp/emar_detail` by `emar_id + emar_seq`. A qualifying administration:

- matches the same strict drug-class whitelist using medication plus product
  description;
- occurs within the assigned ICU stay;
- has a positive event semantic frozen in
  `config/event_semantics_v1.0.csv`;
- is not overridden by any linked detail row with
  `complete_dose_not_given = yes`.

Actual administration does **not** require a numeric dose because that would
selectively discard otherwise documented administrations. Dose availability is
audited separately. `dose_given` plus unit is the primary dose field;
`product_amount_given` is reported separately; `dose_due` is never substituted
as an administered dose.

`prescriptions`, `pharmacy`, and `poe` are order/intent sources and can never
define actual administration. `inputevents` is audited for dictionary-to-fact
table orphans but is not the primary administration source.

### 4.3 Event semantic denominator

The exact mapping is frozen in `config/event_semantics_v1.0.csv`.

- Strict given: Administered, Delayed Administered, Partial Administered,
  Applied, or Started.
- Not given: Not Given, Held, or Refused, plus any row overridden by
  `complete_dose_not_given = yes`.
- `Flushed`, `Confirmed`, and blank/null `event_txt` are three separate
  categories and never enter the given/not-given denominator.
- Every other value is reported as `other_excluded`; it is not silently mapped.

## 5. Primary estimands

### 5.1 Order-to-administration conversion

For each of the six strict drug classes:

`conversion = eligible linked order clusters with >=1 linked strict
administration / all eligible linked order clusters`.

The administration must share `poe_id`, drug class, and ICU stay, and occur no
earlier than 2 hours before POE order time and no later than the earliest of
prescription stop time plus 6 hours or ICU outtime. Negative-lag matches from
-2 to <0 hours are retained as documentation-timing anomalies and excluded
from the lag distribution, but count as linked conversions. Wilson 95%
confidence intervals are reported. No class is dropped for a low count; classes
with fewer than 500 eligible orders are labeled descriptive-only.

### 5.2 First-dose lag

Among converted orders, lag is:

`first linked qualifying eMAR charttime − POE ordertime`.

Report N, median, IQR, P10, P90, P95, zero/negative anomaly count, and >24-hour
count by class. The inferential lag distribution excludes negative lags and
lags over seven days; excluded tails remain in a separate audit table.

### 5.3 Held/not-given proportion and correlates

For each class:

`not-given proportion = not-given decision events /
(strict-given + not-given decision events)`.

Report exact event-text and available detail-field reason distributions. The
prespecified row-level logistic model uses not-given versus given as outcome
with:

- first-day OASIS per standard deviation and a missing-component count;
- shift: day 07:00–18:59 versus night 19:00–06:59, based on deidentified local
  `charttime`;
- active invasive ventilation, vasopressor infusion, and RRT at event time;
- drug class, age, sex, emergency admission, ICU care unit, and anchor-era
  adjustment.

Standard errors are clustered by `stay_id`. Report adjusted odds ratios and
95% confidence intervals. Class-specific rates are mandatory; class-specific
models are descriptive and cannot be selected by P value.

OASIS follows the MIMIC Code v3.0.0 first-day specification. If a component is
missing, its score contribution is zero as in the official SQL, while the
number of missing components is retained and reported.

## 6. Mandatory full-table audits

Before fitting any outcome model:

1. Scan the **entire** `hosp/emar.csv.gz`, not a sample. Report total rows,
   exact `event_txt` distribution, nonmissing `poe_id`, and successful POE
   same-subject/same-admission link coverage. The distribution must reconcile
   exactly to the full-table row count.
2. Scan all linked `emar_detail` rows for whitelisted medication events. Report
   `dose_given` availability, unit availability, `product_amount_given`,
   route, `complete_dose_not_given`, `reason_for_no_barcode`,
   `administration_type`, and whether any dedicated not-given reason exists.
3. Compare all `d_items` rows linked to event tables with fact-table counts.
   Produce the complete “dictionary item exists but fact table has zero rows”
   list for the relevant interfaces and explicitly reproduce inputevents
   itemid 225925 (Potassium Phosphate).
4. Keep Flushed, Confirmed, and blank/null `event_txt` separate and outside all
   given/not-given denominators.

Any `ignore_errors` CSV option is prohibited for row-count reconciliation.
Parse failures must stop the audit rather than discard rows.

## 7. Prespecified published-association re-estimations

The purpose is exposure-definition sensitivity, not replication prestige and
not a new causal claim. Both anchors are retained regardless of their results.
The same cohort and covariates are used for order-defined and
administration-defined fits.

### A1. VTE prophylaxis and in-hospital mortality

Anchor: Muchintala R, et al. *Missed Venous Thromboembolism Prophylaxis in ICU
Patients: A Retrospective Cohort Study Using MIMIC-IV*. Cureus. 2025;
17:e86370. PMID 40688991; PMCID PMC12276787; DOI 10.7759/cureus.86370.

Published association: an order was used as a proxy for administration;
heparin/enoxaparin prophylaxis was associated with lower in-hospital mortality
(adjusted OR 0.35, 95% CI 0.34–0.37).

Frozen re-estimation:

- adults with exactly one ICU stay in the data and valid hospital outcome;
- exposure any strict subcutaneous prophylactic UFH/enoxaparin during the ICU
  stay, defined once from orders and once from strict eMAR administration;
- outcome in-hospital death;
- logistic model adjusted for continuous age, sex, and emergency admission,
  matching the published minimal model;
- enriched sensitivity additionally adjusts OASIS and first-day organ support;
  it cannot replace the minimal model.

### A2. Prophylactic PPI and 90-day mortality in sepsis

Anchor: Ma C, et al. *Prophylactic proton pump inhibitor use and all-cause
mortality in adult sepsis patients: a retrospective analysis based on the
MIMIC-IV database*. Front Pharmacol. 2025;16:1545533. PMID 40612738; PMCID
PMC12223537; DOI 10.3389/fphar.2025.1545533.

Published association: prophylactic PPI use was associated with increased
90-day all-cause mortality.

Frozen re-estimation:

- adults, first ICU stay per subject, ICD-coded sepsis
  (`ICD-10 A40*`, `A41*`, `R65.2*`; `ICD-9 038*`, `99591`, `99592`, `78552`);
- exclude diagnoses for active acid-suppression treatment: ICD-10 K20*, K21*,
  K25*–K29*, K22.6, K92.0–K92.2, I85.0*; ICD-9 530.1*, 530.81, 531*–535*,
  578*;
- exposure any strict PPI (not H2RA/sucralfate) active or ordered/administered
  from ICU entry through 48 hours, defined once from orders and once from strict
  eMAR;
- outcome death within 90 days from ICU entry, censoring at 90 days;
- Cox model adjusted for continuous age, sex, emergency admission, and anchor
  era; enriched sensitivity additionally adjusts OASIS and first-day organ
  support;
- a prespecified 48-hour landmark analysis among patients alive/in hospital at
  48 hours is reported as an immortal-time-bias diagnostic, never selected in
  place of the published-style result.

The A2 ICD cohort is a transparent operational re-estimation, not a claim of
exactly reproducing the paper’s Sepsis-3 cohort.

### Effect-change estimands for A1 and A2

Report:

- exposure prevalence under both definitions and cross-classification;
- order-defined and administration-defined effect estimates on the log scale;
- absolute and percent change in log effect;
- ratio of odds ratios or hazard ratios;
- whether the point-estimate direction crosses the null;
- confidence intervals for both fits.

A material exposure-definition change is prespecified as at least one of:

- point-estimate direction reversal;
- absolute log-effect change >= log(1.25);
- relative absolute log-effect change >=25%.

Statistical significance is not a selection rule.

## 8. eICU boundary

eICU is an interface-semantic contrast only. Following ND03 decisions D004 and
D013:

- `medication` is order/planned-start evidence;
- `treatment` is documentation;
- `infusionDrug` and `intakeOutput` may be administration-like only when a
  drug-specific label, positive numeric value/rate, and valid offset coexist;
- eICU cannot be called external validation of treatment, timing, dose, or
  outcome associations in this project.

The supplied eICU whitelist is parsed in full and summarized by source, role,
tier, row count, and stay count. No MIMIC/eICU effect comparison is fitted.

## 9. Multiplicity, missingness, and reporting

- Six classes and two anchors form frozen families; none may be removed.
- Confidence intervals are descriptive. A Benjamini–Hochberg table is supplied
  for the prespecified not-given correlates, but promotion is based on effect
  size and validity gates, not significance.
- Missing OASIS components are explicitly counted. No outcome-driven complete
  case restriction is allowed.
- All negative results, low-count classes, unmatched orders, ambiguous event
  text, temporal anomalies, and failed models remain in machine-readable
  output.

## 10. Stop-loss and final decision

User-mandated negative stop-loss:

If **all six** strict class conversion estimates are >97% and not-given has no
meaningful severity association, complete the negative validity report,
downgrade the journal target, and do not expand classes or relax windows.

“Meaningful severity association” is frozen as adjusted OASIS OR per SD >=1.15
or <=0.87 with a 95% CI excluding 1. This threshold governs story
classification only; it does not select drug classes.

Final labels:

- **GO**: mandatory audits pass, at least one material measurement discrepancy
  exists, and at least one of the two published associations has a material
  exposure-definition change.
- **BACKUP**: audits pass but association effects are not materially changed,
  including the user-mandated all-conversion->97% negative-validity scenario.
- **NO-GO**: a fatal measurement failure prevents valid estimation (unreadable
  full tables, unreconcilable row counts, systematic identity corruption, POE
  link coverage <50% in both anchor classes, or both anchor cohorts below 500
  with <1% exposure under either definition).

No unfavorable scientific result alone is a NO-GO.

