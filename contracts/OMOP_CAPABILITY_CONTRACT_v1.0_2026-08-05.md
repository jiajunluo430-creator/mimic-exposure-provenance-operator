# OMOP capability contract v1.0

Frozen: 2026-08-05, before executing the OMOP demo or synthetic semantic-loss test.

## Purpose and claim boundary

This phase evaluates expression and execution capability for medication-exposure provenance in OMOP CDM. It is an adapter smoke test and semantic-loss demonstration, not external clinical validation and not patient-level parity with the MIMIC-IV v3.1 reference implementation.

## Frozen inputs

- Primary executable comparator: a synthetic canonical fixture generated from a frozen A2 proton-pump-inhibitor operator.
- Real-data smoke test, if accessible: MIMIC-IV demo data in OMOP CDM v0.9, DOI `10.13026/p1f5-7x35`, all 100 demo patients.
- Official limitation retained: v0.9 populates drug exposure from `prescriptions` and `pharmacy`; it does not use `emar`/`emar_detail` for additional medication detail and does not incorporate `inputevents`.
- OMOP CDM reference: v5.4 `DRUG_EXPOSURE` specification. The older demo schema is inspected as observed and is not silently upgraded.

## Frozen operator

- Medication class: stress-ulcer-prophylaxis PPI strict ingredients from `config/drug_class_whitelist_v1.0.csv`.
- Source role: documented drug-exposure record, with `drug_type_concept_id` and source fields retained as provenance; it must not be relabeled as administration unless source type and literal semantics support that interpretation.
- Analysis unit: `person_id` by `visit_occurrence_id` by medication class.
- Time: `drug_exposure_start_datetime` (or date only when datetime is absent) during the visit; end time is retained but not imputed.
- Identity: standard `drug_concept_id` when nonzero plus `drug_source_concept_id` and `drug_source_value`; source-value matching remains visible.
- Required state semantics: literal administration/non-administration state is extension-required unless present in an explicit `medprov_event_state` field. Absence produces `unmeasurable` for a strict administration operator, not unexposed.

## Frozen fields assessed

`drug_exposure_id`, `person_id`, `drug_concept_id`, `drug_exposure_start_datetime`, `drug_exposure_end_datetime`, `drug_type_concept_id`, `route_concept_id`, `route_source_value`, `quantity`, `dose_unit_source_value`, `sig`, `provider_id`, `visit_occurrence_id`, `visit_detail_id`, `drug_source_value`, and `drug_source_concept_id`.

Source order identifiers, native revision chains, literal eMAR state, not-given reason, and full source provenance are reported as native, source-field-carried, extension-required, unknown, or absent based on actual data and official documentation.

## Frozen evaluations

1. Synthetic round trip: canonical operator -> OMOP/ATLAS-style cohort JSON plus medprov provenance extension -> execution -> aggregate classification.
2. Extension ablation: rerun without provenance extension and quantify records that become unresolved or unmeasurable.
3. Real v0.9 smoke test: schema/field completeness, source-type distribution, six-class strict label observability, execution status, and aggregate counts only.
4. No treatment-effect models and no external clinical effect comparison.

## Frozen gates

- Synthetic adapter gate: deterministic execution, no silent loss, and explicit unresolved/unmeasurable output.
- Real demo gate: `EXECUTED_CAPABILITY_SMOKE_TEST` if `DRUG_EXPOSURE` is available and readable; otherwise `NOT_EXECUTED_DATA_UNAVAILABLE`.
- `OMOP validation` and `external validation` are prohibited labels for this phase.

Downloaded demo data and row-level traces remain outside the public release.
