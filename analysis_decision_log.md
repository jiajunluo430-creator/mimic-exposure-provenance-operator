# N1 analysis decision log

Definitions that change cohort membership, exposure, denominators, or the main
claim are never changed silently.

## D001 — source immutability

- Date: 2026-07-29
- Status: binding
- Decision: MIMIC-IV and eICU source assets are read-only. Every derived file is
  written below this N1 project root.

## D002 — inherited MIMIC administration boundary

- Date: 2026-07-29
- Status: binding
- Decision: inherit ND03 D003/D009. Prescriptions, pharmacy, and POE are orders.
  eMAR is the primary MIMIC administration source only under the frozen event
  semantics and detail override. Inputevents itemid 225925 is audited but does
  not override eMAR.

## D003 — inherited eICU boundary

- Date: 2026-07-29
- Status: binding
- Decision: inherit ND03 D004/D013. eICU is interface-semantic contrast only
  and is not external validation of treatment, timing, dose, or outcome.

## D004 — medication whitelist frozen

- Date: 2026-07-29
- Status: binding before result scan
- Decision: six classes, ingredient RxCUIs, name regexes, negative regexes,
  tiers, routes, and dose rules are frozen in
  `config/drug_class_whitelist_v1.0.csv`.

## D005 — event semantics frozen

- Date: 2026-07-29
- Status: binding before result scan
- Decision: exact event mappings are frozen in
  `config/event_semantics_v1.0.csv`. Flushed, Confirmed, and blank are separate
  and outside the decision denominator.

## D006 — published anchors frozen

- Date: 2026-07-29
- Status: binding before model fitting
- Decision: A1 Muchintala 2025 VTE prophylaxis–hospital mortality and A2 Ma
  2025 prophylactic PPI–90-day mortality are the only primary published
  association anchors. Neither can be replaced because of results.

## D007 — effect-change thresholds frozen

- Date: 2026-07-29
- Status: binding
- Decision: material change is direction reversal, absolute log-effect change
  at least log(1.25), or relative absolute log-effect change at least 25%.
  Statistical significance does not select results.

## D008 — user negative stop-loss retained

- Date: 2026-07-29
- Status: binding
- Decision: if all class conversion estimates exceed 97% and not-given has no
  meaningful severity relationship, finish a negative validity report,
  downgrade journal target, and do not expand classes or relax windows.

## D009 — contract precedes modeling

- Date: 2026-07-29
- Status: verified process fact
- Decision: no medication-result scan or outcome model was run before the
  contract, whitelist, event semantics, association anchors, and gate rules
  above were written.

## D010 — mandatory-audit semantic sensitivity

- Date: 2026-07-29
- Status: separately hashed before every severity/outcome model
- Decision: preserve D005 as the literal primary and all-gate definition.
  Because the required full-table audit identified the explicit vendor
  subtypes `Hold Dose` and `Not Given per Sliding Scale*`, report a locked
  semantic sensitivity adding only those strings. It cannot replace the
  primary, affect GO/BACKUP/NO-GO, or justify class/window expansion. See
  `contracts/semantic_audit_addendum_v1.0_2026-07-29.md`.

## D011 — official OASIS ventilation implementation

- Date: 2026-07-29
- Status: implementation repair before model fitting
- Decision: derive invasive ventilation from the official MIMIC Code
  ventilator-mode/oxygen-device status and 14-hour interval logic. Do not use
  procedureevents itemid 225792 as a substitute for the OASIS ventilation
  component. Vasopressor and RRT intervals remain independently audited organ
  support covariates.

## D012 — bounded native-identity pharmacy recovery

- Date: 2026-07-29
- Status: implementation-only performance repair
- Decision: replace a computationally unbounded within-admission OR join with
  two native-identity hash joins: use `pharmacy_id` when present, otherwise
  `poe_id`. Deterministically retain one earliest pharmacy match per native
  identity. This implements the same frozen recovery precedence while
  preventing a large within-admission candidate cross-product.

## D013 — one-pass frozen ingredient matching

- Date: 2026-07-29
- Status: implementation-only performance repair
- Decision: evaluate each of the 52 strict name regexes once to assign the
  uniquely mapped frozen ingredient for each distinct normalized
  `drug + formulary_drug_cd` name key, then hash that mapping back to source
  rows and map the ingredient to its already frozen class/subclass. This
  replaces per-row repeated evaluation of the same regex set and does not
  alter any regex, negative exclusion, ingredient, class, subclass, tier,
  route, dose, or precedence rule. Native pharmacy/POE semi-joins retain rows
  eligible for pharmacy-name recovery even when their direct name is not a
  match.

## D014 — checkpointed Stage 02 v2 after legacy plan failure

- Date: 2026-07-29
- Status: implementation-only repair after production audit
- Decision: retain the abandoned multi-hour query as an implementation
  failure audit. Replace its two conditional `BLOCKWISE_NL_JOIN` operators
  with separate guarded equality paths, deduplicate prescriptions before
  downstream work, aggregate eMAR to one row per
  `stay_id × drug_class × poe_id`, and checkpoint every materialization.
  The frozen whitelist, analysis unit, windows, event semantics, and
  estimands are unchanged.

## D015 — VTE rule expressed at the contract-specified layer

- Date: 2026-07-29
- Status: implementation correction before severity/outcome modeling
- Decision: express the frozen order-side SC/SQ/subcutaneous contains rule
  with DuckDB `regexp_matches`; DuckDB 1.5.3 returned zero matches for the
  legacy `SIMILAR TO '%(sc|sq|subcut)%'` expression despite source route
  `SC`. Apply the route/prophylactic-dose rule only to the strict VTE order
  as specified in contract section 4.1. Do not add an eMAR route or numeric
  dose requirement to section 4.2 actual administration; those fields remain
  availability audits. No route, dose, drug, window, or outcome rule changed.

## D016 — explicit gzip schemas for production scans

- Date: 2026-07-29
- Status: implementation-only performance safeguard
- Decision: replace full-file automatic type inference with explicit
  all-VARCHAR source schemas followed by the same `TRY_CAST` projections for
  Stage 02 prescriptions/pharmacy/eMAR keys and Stage 03 ICU source scans.
  This changes parsing implementation only and prevents repeated full gzip
  inference passes; source files remain read-only.

## D017 — comprehensive post-primary exploratory layer

- Date: 2026-07-29
- Status: locked after the frozen primary analysis passed validation
- Decision: permit a submission-oriented exploratory layer covering all six
  frozen classes, both frozen anchors, and every already fitted model variant.
  Report exposure agreement, discordance, semantic-sensitivity uplift, and
  movement on the log-effect scale without significance-based selection.
  This layer is explicitly descriptive, does not alter any frozen definition,
  and cannot be used to claim new drug efficacy or safety. See
  `contracts/post_primary_exploratory_addendum_2026-07-29.md`.

## D018 — stay-level calendar-alignment repair

- Date: 2026-07-30
- Status: binding before corrected-era models
- Decision: the existing `anchor_era` implementation assigned the patient's
  unaligned `anchor_year_group` to every ICU stay. MIMIC-IV requires each stay
  to be aligned by `year(intime) - anchor_year`. Repair the already frozen era
  covariate using the stay-aligned midpoint while retaining the original broad
  categories. Preserve prior outputs as implementation history and write all
  corrected outputs separately.

## D019 — observability precedes fidelity

- Date: 2026-07-30
- Status: post-primary extension frozen before new outcome models
- Decision: distinguish administration-layer observability from residual
  order-to-documented-administration fidelity. Define pre, implementation-
  overlap, and post-implementation periods using the full stay-aligned
  three-year interval. Report pooled results and all eras; do not reinterpret
  every nonconversion as a withheld dose.

## D020 — any-eMAR admission proxy is descriptive only

- Date: 2026-07-30
- Status: binding
- Decision: the presence of any full-table eMAR row in an admission may
  describe interface availability and support descriptive sensitivity tables,
  but it cannot select an outcome-model cohort because it may depend on
  medication intensity, severity, or clinical workflow.

## D021 — JAMIA promotion uses the original material-change rule

- Date: 2026-07-30
- Status: frozen before corrected-era or post-implementation outcome models
- Decision: retain both anchors and every frozen model variant. Promote the
  JAMIA route only if all reconciliation/same-cohort gates pass and at least
  one post-implementation published-style anchor meets the original D007
  material-change rule. Otherwise retain PDS as BACKUP without adding classes,
  anchors, windows, or models. See
  `contracts/jamia_observability_addendum_v1.0_2026-07-30.md`.
