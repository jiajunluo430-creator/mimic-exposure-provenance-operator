# Upgrade master contract v1.0

Frozen: 2026-08-05, before any new method-upgrade result was executed.

Status: **binding**. This contract adds software-validation, representation-capability, prespecified-ablation, and reporting-validator evaluations. It does not modify the 2026-07-29 scientific contract.

## 1. Objective and non-objectives

The objective is to develop and evaluate a versioned, machine-executable medication-exposure provenance specification, reference implementation, validator, compiler, executor, reports, and adapter architecture. The method must distinguish syntax, adapter support, measurability, executability, and reproducibility/traceability.

The project will not estimate new treatment efficacy or safety, select definitions by significance, introduce new medication classes, alter A1/A2 models, invent independent coding, or represent eICU/OMOP/FHIR capability as clinical external validation.

## 2. Frozen prior analysis

The following remain immutable and are referenced by their repository files/hashes:

- `analysis_contract_v1.0_2026-07-29.md` and its recorded hash;
- six medication classes and `drug_class_whitelist_v1.0.csv`;
- `event_semantics_v1.0.csv` and audit-sensitivity mapping;
- original and hospital-overlap windows;
- A1/A2 cohorts, outcomes, covariates, models, and material-change rules;
- published-operator codebook and one-coder landscape;
- POE temporal and cross-POE addenda/results.

Existing required parity totals are 264,171 eligible post-deployment order units, 170,890 strict same-POE conversions, and 227,355 broad same-class/window conversions. Integers require exact equality. Frozen model coefficients/effects require absolute numeric tolerance <=1e-10 when recalculated with the same runtime and <=1e-8 across documented compatible runtimes.

## 3. Formal operator

The core operator is O=(S,I,T,E,M):

1. `source_layer`;
2. `identity_rule`;
3. `time_origin_window`;
4. `event_semantics_map`;
5. `required_metadata`.

All five dimensions are required in Draft 2020-12 JSON Schema. Envelope fields may include schema/operator version, clinical construct, analysis unit, target event, adapter/data-model version, vocabulary/code-list version/hash, output specification, and author/date provenance. No sixth weighted dimension or continuous fidelity score is permitted.

The four classification states are `exposed`, `unexposed`, `unresolved`, and `unmeasurable`. Validation states are independently reported as `syntactically_valid`, `adapter_supported`, `measurable`, `executable`, and `reproducible_traceable`.

## 4. Software contract

The package name and CLI are `medprov`. Default commands output aggregate JSON and Markdown/HTML only. Patient/unit identifiers may be retained in a canonical intermediate representation only during explicit local execution and must be excluded by default from release/export paths.

Required commands:

- `medprov validate-spec`;
- `medprov capability`;
- `medprov compile`;
- `medprov execute`;
- `medprov compare`;
- `medprov validate-reporting`;
- `medprov demo`.

Each command must have deterministic output and documented exit codes. A compilation plan must identify source tables/resources, predicates, joins, deduplication unit, time boundaries, metadata gates, unresolved rules, and output fields.

## 5. Native parity evaluation

Input: read-only MIMIC-IV 3.1 native data or the existing materialized read-only DuckDB reference cache. Analysis unit and all definitions remain frozen.

Primary metrics:

- exact total and six-class order/strict/broad counts;
- exact A1/A2 exposure cross-classification and exposure totals;
- exact original and hospital-overlap cohort/exposure counts;
- A1/A2 frozen model inputs and effects within numeric tolerance;
- exact 183-unit POE aggregate trace.

Failure rule: any integer mismatch or out-of-tolerance continuous mismatch fails parity and requires a diagnostic localized to specification, adapter, identity/deduplication, join, event state, or time boundary. Old results may not be changed to force agreement.

## 6. Prespecified ablation and baselines

All of the following will be executed and reported regardless of direction:

1. observability/deployment gate removed;
2. exact native identity replaced by same-class identity;
3. original window replaced by hospital-overlap window;
4. literal event semantics collapsed to given/not-given;
5. required route/dose metadata ignored;
6. table-only baseline;
7. source+class+window baseline;
8. full five-dimensional operator.

Outputs: measurability/execution status; exposed/unexposed/unresolved/unmeasurable counts; Jaccard, positive and negative agreement; reclassification matrix; event-time displacement; metadata retention; failure-reason distribution; and frozen A1/A2 estimate drift where the existing model supports the comparison. No P value selects an ablation.

## 7. Reporting validator

Input: the existing 40-study human-coded table plus public identifiers and short evidence locations. The primary validator reads structured records only. It will reproduce dimension-level counts and the complete-executable-operator count, with expected checkpoints including 7/40 named native source, 2/40 executable identity, and 0/40 complete operator after expanded source review.

Any mismatch triggers mapping diagnosis; the historical counts are not edited to fit the software. Optional text assistance is labeled experimental and cannot determine primary outcomes.

Second-coder agreement is `AUTHOR_ACTION_REQUIRED_SECOND_CODER` until a genuinely independent completed worksheet is provided. Software may provide import and agreement calculations but may not populate that worksheet.

## 8. FHIR data/version gate

Exact cross-representation parity requires matched MIMIC-IV native 2.2 and MIMIC-IV-on-FHIR 2.1, or a matched demo. Native 3.1 versus FHIR derived from 2.2 cannot be called exact parity.

At freeze, matched native/FHIR data are locally absent. The pre-result status is `NOT_EXECUTED_DATA_UNAVAILABLE`; adapter implementation, synthetic fixtures, official metadata review, and unit tests remain in scope. If data later become available, the sample is all available data or a subject-ID hash sample with seed 20260805 fixed before results.

## 9. OMOP capability gate

The OMOP adapter will support `DRUG_EXPOSURE` and relevant source fields. Synthetic round-trip tests will identify retained, extension-required, and lost provenance. The 100-person MIMIC-IV OMOP demo, if obtained, is a smoke/capability test only. At freeze it is locally absent; clinical external validation and outcome modeling are prohibited.

## 10. eICU capability/transportability

Input: read-only eICU-CRD 2.0 ZIP. The six frozen classes remain unchanged.

- `medication`: order/planned-start-like;
- `infusionDrug`: administration-like only with drug-specific label, positive numeric rate/value, and valid offset;
- `treatment`: documentation only;
- `intakeOutput`: used only for an explicitly matching clinical construct, never as generic administration.

Required feasibility outputs are source observability, time/route/dose/rate/frequency availability, identity mapping, native-key availability, and hospital/unit heterogeneity. Patient-level same-class/window reconciliation requires >=100 eligible analysis units, >=10 hospitals, valid time, and interpretable identity. Without a native key, it is not exact identity validation. No eICU A1/A2 outcome model is permitted.

## 11. State-of-the-art comparison

Only official specifications or original papers will be used for PheKB/computable phenotypes, OMOP/ATLAS, FHIR medication resources, CQL when relevant, and RECORD-PE/STaRT-RWE/HARPER. The matrix will distinguish native support, extension required, unknown, and not applicable for source observability, native identity/revision, time assignment, literal semantics, metadata requirements, unresolved/unmeasurable states, trace, execution, and cross-model compilation.

At least one frozen operator will be rendered into an executable or machine-readable comparator representation. Missing explicit documentation is `unknown`, not unsupported. medprov is positioned as a provenance supplement, not a replacement.

## 12. Software/release validation

Required gates include schema cases, all examples, synthetic end-to-end execution, CLI exit codes, deterministic outputs, adapter capability, real-data local parity, restricted-data/secret/absolute-path scans, Windows/POSIX path checks, build of wheel/sdist, and a release manifest hash.

External push, release, DOI, preprint, or submission is prohibited without separate authorization. Local commits and build artifacts are permitted. Version target is `0.1.0` unless validation justifies a higher version.

## 13. Manuscript and journal decision

The new manuscript is a method-development/evaluation paper. MIMIC is the reference implementation; the 40-study validator and A1/A2 are validation/use-case components. Results must lead with specification/software validation, parity, ablation, and cross-model capability.

Target selection follows hard evidence gates:

- JBI only if package/schema/CLI, exact parity, ablation, real comparator, and at least one meaningful beyond-MIMIC execution evaluation are substantially complete;
- otherwise IJMI if method, validator, parity, and application evaluation are complete;
- otherwise JAMIA Open or BMC MIDM for a practical open-source tool with weaker transport evidence;
- PDS if software/method validation is not achieved but measurement propagation remains complete.

No acceptance probability or impact factor substitutes for scope fit.

## 14. Stop rules

- Do not download or materialize large external data when disk headroom or version mismatch makes the planned evaluation unsafe.
- Do not re-run completed raw scans unless integrity/parity fails.
- Mark missing matched data `NOT_EXECUTED_DATA_UNAVAILABLE` and continue synthetic/adapter work.
- Mark missing independent recoding `AUTHOR_ACTION_REQUIRED_SECOND_CODER` and continue.
- Preserve all failed, negative, unresolved, and unmeasurable outputs.
- Stop manuscript claims at the strongest completed evidence; do not fill missing method validation with prose.

