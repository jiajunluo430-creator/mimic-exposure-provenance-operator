# State-of-the-art comparison contract v1.0

Frozen: 2026-08-05, before producing the comparison matrix.

## Purpose

The comparison locates medprov relative to existing phenotype representations, common data models, interoperability resources, executable logic, and reporting/protocol guidance. It demonstrates a bounded method increment and does not claim that medprov replaces any comparator.

## Frozen comparators and evidence hierarchy

Only official specifications, official project documentation, or original peer-reviewed papers are admissible:

1. PheKB and its original transportability paper.
2. OHDSI OMOP CDM v5.4 and ATLAS-style CohortDefinition/Book of OHDSI documentation.
3. HL7 FHIR R4 medication resources (`MedicationRequest`, `MedicationDispense`, `MedicationAdministration`).
4. HL7 Clinical Quality Language, current published normative specification.
5. RECORD-PE original statement.
6. STaRT-RWE original structured-template paper.
7. HARPER original good-practices report.

Current official pages are archived in the evidence table with URL, version, access date, and the exact claim supported. Absence of explicit documentation is classified `unknown`, not `unsupported`.

## Frozen comparison dimensions

1. source observability and deployment context;
2. native record identity and revision chain;
3. time origin, window, and assignment rule;
4. literal event semantics;
5. required route/dose metadata;
6. explicit unresolved or unmeasurable state;
7. patient-level provenance trace;
8. machine execution;
9. cross-model compilation.

Allowed cell values: `native`, `partial`, `extension_required`, `implementation_dependent`, `reporting_only`, `unknown`, and `not_applicable`. Narrative rationale and source are mandatory; no numeric superiority score is computed.

## Frozen executable comparator

The strict A2 PPI operator is expressed as:

- a medprov canonical YAML specification;
- an OMOP/ATLAS-style cohort JSON using `DRUG_EXPOSURE`, visit membership, concept/source-value identity, and temporal criteria;
- a medprov provenance extension carrying literal source role, native identifiers, state semantics, and unmeasurable policy where these are not native cohort criteria.

Both forms execute against the same synthetic OMOP fixture. Report expression completeness, aggregate classifications, fields that cannot be represented natively, and the change after removing the provenance extension. This is an executable semantic-loss comparator, not a benchmark of software speed or phenotype accuracy.

## Frozen novelty statement

The permissible claim is: medprov is a lightweight, versioned, adapter-aware provenance specification for EHR medication exposure that can test measurability before execution, retain an auditable trace after execution, and quantify propagation from simplified definitions to classification and downstream estimates.

Claims that medprov replaces PheKB, OMOP, FHIR, CQL, RECORD-PE, STaRT-RWE, or HARPER are prohibited.
