# FHIR transport contract v1.0

Frozen: 2026-08-05, before downloading or executing the matched demo.

## Purpose and claim boundary

This evaluation tests whether the same medication-exposure provenance specification can be executed across a relational MIMIC-IV representation and its version-matched FHIR representation. It is a functional cross-schema evaluation on a 100-patient public demo, not full-dataset transport validation and not clinical external validation.

The full MIMIC-IV v3.1 reference results must not be compared patient-for-patient with MIMIC-IV-on-FHIR v2.1, because the latter was derived from MIMIC-IV v2.2.

## Frozen data gate

- Native representation: MIMIC-IV Clinical Database Demo v2.2, DOI `10.13026/dp1f-ex47`.
- FHIR representation: MIMIC-IV Clinical Database Demo on FHIR v2.1.0, DOI `10.13026/vphg-y548`.
- The FHIR demo explicitly identifies native demo v2.2 as its parent dataset.
- Population: all subjects in the public matched demo; no sampling by results.
- Relevant native sources: `prescriptions`, `pharmacy`, `emar`, `emar_detail`, `poe`, `admissions`, and `icustays` when present.
- Relevant FHIR resources: `MedicationRequest`, `MedicationDispense`, `MedicationAdministration`, `Medication`, `Encounter`, and `Patient`. `MedicationAdministrationICU` is reported separately and is not silently merged with hospital eMAR administration.
- Official SHA256 lists and local file hashes are captured before execution. A hash mismatch is a data-integrity failure.

If either matched representation is unavailable, real-data status is `NOT_EXECUTED_DATA_UNAVAILABLE`; synthetic adapter tests may still run but cannot replace the real-data result.

## Frozen medication identity

- The six pre-existing medication classes and the strict-tier name/RxNorm whitelist in `config/drug_class_whitelist_v1.0.csv` are used without additions.
- Native identity uses the same strict regular expressions against the pre-specified source name fields.
- FHIR identity resolves `medicationReference` to `Medication` when present, otherwise uses `medicationCodeableConcept`; all coding systems, codes, displays, and source references are retained in the provenance trace.
- Class mapping is evaluated, not tuned, after seeing results. Unmapped or multiply mapped medication identities are `unresolved`, not negative.

## Frozen source roles and event semantics

| Source | Role | Positive | Negative | Unresolved |
|---|---|---|---|---|
| Native `prescriptions` / FHIR `MedicationRequest` | order-like intention | record exists and is not entered-in-error | entered-in-error | missing/unknown resource status or unresolved medication |
| Native `pharmacy` / FHIR `MedicationDispense` | dispense/verification-like | `completed` or native record exists | `declined`, `entered-in-error` | other/missing status or unresolved medication |
| Native `emar` / FHIR `MedicationAdministration` | documented administration | native strict eMAR positive semantics; FHIR `completed` | native strict negative semantics; FHIR `not-done`, `entered-in-error` | all other statuses, blank/ambiguous semantics, or unresolved medication |

Dispense is never treated as administration. `Flushed`, `Confirmed`, and blank native `event_txt` remain separate unresolved classes and are not included in a strict-administration denominator.

## Frozen analysis units and time

- Record-level unit: one native source record or one FHIR resource, deduplicated by the native identifier retained in that representation when available.
- Patient-level unit: subject by medication class.
- Encounter-level unit: hospital encounter by medication class.
- Whole-record source coverage is primary for record parity.
- For patient/encounter exposure comparison, any qualifying record during the linked hospital encounter is counted. No outcome-dependent landmark is introduced.
- Event-time displacement is calculated only for pairs with a deterministic retained native identifier and two valid timestamps; otherwise it is `not_evaluable`.

## Frozen evaluation metrics

For each source role and medication class report:

1. specification validation and execution status;
2. native and FHIR record counts;
3. deterministic native-identifier retention and exact matched-record proportion;
4. ingredient/class mapping retention;
5. route, dose, unit, frequency, status, subject, encounter, and event-time availability;
6. subject-class and encounter-class exposure Jaccard similarity;
7. event-time displacement among deterministic pairs;
8. unresolved and unmeasurable reason counts;
9. wall-clock runtime and peak process memory when measurable;
10. whether each of the five dimensions was preserved, transformed, merged, extension-carried, or lost.

Exact parity is claimed only for a metric whose mapping is deterministic and whose denominators are identical. A discrepancy is first classified as version mismatch, resource/profile mapping, source-field loss, adapter defect, or unresolved; it is not labeled a FHIR error by default.

## Frozen gates

- `PASS_FUNCTIONAL_CROSS_SCHEMA`: both matched demos execute; all three medication resource roles are discovered; at least one frozen class is represented; and all comparison metrics or explicit `not_evaluable` reasons are emitted without patient-level release.
- `PARTIAL_FUNCTIONAL_CROSS_SCHEMA`: execution succeeds but one or more roles/classes are structurally absent or identity/time pairing is not evaluable.
- `FAIL_ADAPTER`: matched data are present but parsing, resource resolution, or deterministic execution fails.
- `NOT_EXECUTED_DATA_UNAVAILABLE`: a matched representation is absent.

No threshold is based on favorable exposure agreement.

## Privacy and release

Only aggregate tables, code, hashes, and non-patient examples may enter the public release. Downloaded demo files and any patient-, encounter-, or native-record-level trace remain under ignored `local_data/` or `outputs/local/` paths.
