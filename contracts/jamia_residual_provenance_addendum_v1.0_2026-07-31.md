# JAMIA residual-provenance diagnostic addendum v1.0

**Frozen before generating any result defined below:** 31 July 2026

## Purpose and status

This addendum closes residual validation gaps identified after the joint
provenance-operator analysis. It preserves every parent contract, the six
medication classes, frozen name/RxNorm annotations, event-state mappings,
original and diagnostic windows, A1 and A2 cohorts, outcomes, covariates,
model families, bootstrap rules, and material-change definitions. Nothing in
this addendum can replace or selectively suppress a parent result.

The addendum has four scientific purposes: trace the A2 residual
administration-only cell through pharmacy and prescription records; quantify
route availability on the order side using the same frozen classes; separate
A1 source-layer construct measurability from A2 operator sensitivity; and
make the published-operator coding scope and codebook auditable. It also
defines a patient-free public-code release. The final deliverable remains a
clean first-submission package.

## R1. A2 residual administration-only trace

The trace population is fixed as the 184 A2 stays already assigned to
`no_hospital_overlap_ppi_order_in_admission` in the v2.0
`a2_window_provenance` table. This label means that no PPI prescription with
valid POE identity met the previously frozen hospital-overlap eligibility
operator; it does not by itself establish that no PPI prescription existed
anywhere in the hospitalization.

For those stays, identify all strict-positive PPI eMAR events from ICU entry
through the earlier of ICU entry plus 48 hours or ICU discharge. Deduplicate
to native `emar_id × emar_seq`. Retain the first qualifying event as the
patient-level index event, but use all qualifying events for medication-string
and link-coverage summaries.

Trace each native event through these separately audited paths, always
requiring the same `subject_id` and `hadm_id`:

1. direct eMAR `pharmacy_id` to any raw pharmacy row;
2. direct eMAR `pharmacy_id` to a pharmacy row mapped to PPI by the frozen
   dictionary;
3. direct eMAR `pharmacy_id` to any prescription row;
4. direct eMAR `pharmacy_id` to a prescription row mapped to PPI by the
   frozen dictionary;
5. pharmacy-row `poe_id` to a prescription row with the same native `poe_id`;
6. any frozen-dictionary PPI prescription anywhere in the admission,
   irrespective of ICU-window eligibility.

Because pharmacy and prescription records are not assumed one-to-one, each
large source is first filtered to the 184-stay key set and aggregated to one
row per native event or stay before paths are joined. An EXPLAIN plan and a
limited-key pilot must show no cross product or blockwise nested-loop join.

Assign each stay once through the following hierarchy, using any qualifying
eMAR event in the stay:

1. `direct_pharmacy_id_to_ppi_prescription`;
2. `pharmacy_poe_to_ppi_prescription`;
3. `ppi_prescription_elsewhere_in_admission`;
4. `ppi_pharmacy_record_without_ppi_prescription`;
5. `pharmacy_record_without_mapped_ppi_prescription`;
6. `no_resolved_pharmacy_record_or_ppi_prescription`.

Report patient counts and 90-day mortality for the mutually exclusive groups,
but do not interpret mortality causally. Also report event-level counts for
every link path, the top ten exact `emar.medication` strings by event count
with patient coverage and frozen ingredient assignment, and the top ten
nonblank product descriptions. Exact strings remain an implementation audit,
not an independent coded terminology validation. If ambiguous strings appear,
they must be disclosed and investigated before any manuscript claim that the
residual cell represents a structural provenance break.

No result from this trace changes the original or hospital-overlap exposure
operators or refits the A2 outcome model. Its purpose is to explain the
residual cell and bound possible eMAR-side name-mapping error.

## R2. Order-side route availability and source asymmetry

Using the frozen `prescription_candidates` table, report by medication class:

- name-mapped prescription rows;
- nonblank native `prescriptions.route` rows and percentage;
- distinct native route values; and
- for VTE prophylaxis, the percentage matching subcutaneous, SC, or SQ
  notation.

Repeat route availability at the frozen `eligible_order_clusters` unit so the
order-side conclusion is not driven by prescription revision multiplicity.
Present the prescription-row result beside strict-positive eMAR route
availability. Missing route is never imputed across source layers.

For A1, the construct is described as not fully measurable on a source layer
only if the frozen route-dependent prophylaxis definition is observable on the
order side and unavailable on strict-positive eMAR events. This wording does
not imply that all medication exposure or biological delivery is unmeasurable.
The existing dose-constrained result remains reported; it cannot substitute
for unavailable route.

## R3. Identity and time are independent operator dimensions

All seven frozen static comparisons remain in the main table. Add an explicit
`Order window` column separating original ICU eligibility from hospital-
overlap eligibility. State proactively that original-window identity-aligned
A2 estimates were similar, whereas the hospital-overlap order versus strict-
administration paired delta-log interval did not cross zero. The allowed
interpretation is that identity alignment is necessary but not sufficient:
time eligibility can independently change the intended-exposure population
and recreate source differences.

A1 and A2 serve different demonstrations:

- A1: source-layer construct measurability when route is required but absent
  on one layer;
- A2: operator sensitivity across identity and time, followed by residual
  pharmacy/prescription provenance tracing.

Neither anchor estimates a new causal drug effect or ranks one source as a
universal gold standard.

## R4. Published-operator coding scope and codebook

Retain the frozen PubMed query, randomized order, eligibility rules, seed, and
40-study sample. Publish a dimension-level codebook specifying positive,
negative, and indeterminate rules for source, native table, executable
identity, time origin/window, native event semantics, dose/route, and complete
operator status.

For each included study, audit these evidence locations when publicly linked
and retrievable:

1. main open full text;
2. article-linked supplementary files; and
3. article-linked public code repository or executable appendix.

Record which locations were available and searched. Recode a dimension only
when literal executable evidence is found; clinical drug names or narrative
phrases remain insufficient for database identity or event semantics. Report
the open-full-text restriction and state that excluding 86 non-open records
could bias reporting completeness upward or downward.

The current 40-study coding remains single-primary-coder work unless a named
human coauthor independently applies the frozen codebook. Prepare a blinded
recoding worksheet covering all 40 studies and all coded dimensions. Do not
report Cohen kappa, percent agreement, or dual-coder status until a second
human coder returns completed decisions. AI-assisted checking is not an
independent human coder.

## R5. Manuscript space and reporting

Keep the Research and Applications main text at or below 4000 words. New A2
trace and A1 source-asymmetry results are added by replacing repetitive
Discussion text. Preserve the statement that incomplete Sepsis-3 and OMOP
inputs were not replaced with partial substitutes.

The abstract and opening Discussion must lead with the field-level reporting
gap and the joint-operator result, then distinguish A1 measurability from A2
operator sensitivity. Do not use identity-aligned similarity as a global
reassurance claim.

## R6. Patient-free public repository

Create a new repository independent of the unrelated parent NHANES remote.
The public release may contain contracts, frozen dictionaries, executable
scripts, aggregate tables, manifests, query plans, session information,
figure source files, and documentation. It must exclude raw MIMIC-IV/eICU
files, DuckDB databases, compressed source tables, model-input cohorts,
stay-/patient-level derived rows, credentials, tokens, local absolute paths,
and small disclosive cells not already approved for aggregate release.

Generate a release manifest with SHA-256 for every public file and run an
explicit forbidden-file and identifier scan before publishing. Add the
verified repository URL to Data Availability, the title page, cover letter,
supporting information, and completion note only after the remote upload
succeeds.

## R7. Ethics and administrative wording

Use source-level MIMIC-IV ethics language supported by the dataset publication
and PhysioNet access model: approved data sharing, waiver of individual
informed consent for the deidentified resource, credentialed access, and no
direct patient contact in this secondary analysis. Do not invent a local IRB
approval, exemption number, or signed institutional determination.

Do not invent missing author degrees, telephone numbers, or postal details.
JAMIA title-page requirements and portal author confirmation remain an
administrative completion task; a separate signed all-author approval letter
is not created unless requested by the journal or institution.

## Prohibited adaptations

- Do not change the six classes, frozen dictionaries, event semantics,
  original windows, anchor cohorts, outcomes, covariates, or model selection.
- Do not promote the residual trace into a new effectiveness or safety study.
- Do not infer that a linked pharmacy row proves administration, ingestion, or
  biological exposure.
- Do not claim independent eMAR terminology validation from string review.
- Do not claim dual coding or inter-rater reliability without a completed
  second-human coding file.
- Do not upload patient-level, stay-level, raw licensed, or credential-bearing
  material to the public repository.
- Do not add prediction, machine learning, SHAP, a nomogram, new drug classes,
  new outcomes, or significance-selected analyses.
