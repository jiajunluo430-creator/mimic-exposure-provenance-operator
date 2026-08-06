#!/usr/bin/env python3
"""Build the frozen standards comparison and executable semantic-loss table."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "sota_comparison_v0_1_0"
CONTRACT = ROOT / "contracts" / "SOTA_COMPARISON_CONTRACT_v1.0_2026-08-05.md"
OMOP_SUMMARY = ROOT / "outputs" / "omop_evaluation_v0_1_0" / "omop_evaluation_summary.json"
ACCESS_DATE = "2026-08-05"
ALLOWED = {
    "native",
    "partial",
    "extension_required",
    "implementation_dependent",
    "reporting_only",
    "unknown",
    "not_applicable",
}
DIMENSIONS = [
    "source_observability_and_deployment_context",
    "native_record_identity_and_revision_chain",
    "time_origin_window_and_assignment_rule",
    "literal_event_semantics",
    "required_route_and_dose_metadata",
    "explicit_unresolved_or_unmeasurable_state",
    "patient_level_provenance_trace",
    "machine_execution",
    "cross_model_compilation",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path.name}")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def evidence_rows() -> list[dict[str, str]]:
    return [
        {
            "evidence_id": "MEDPROV-1",
            "comparator": "medprov",
            "title": "Frozen executable medication provenance method contract",
            "source_type": "repository_contract",
            "version": "1.0",
            "access_date": ACCESS_DATE,
            "url": "",
            "local_path": "contracts/METHOD_UPGRADE_CONTRACT_v1.0_2026-08-05.md",
            "claim_supported": "The operator schema freezes source, identity, time, event semantics, required metadata, four-state output, trace, and adapters.",
        },
        {
            "evidence_id": "PHEKB-1",
            "comparator": "PheKB",
            "title": "A national resource for validating and disseminating electronic health record-based phenotype algorithms",
            "source_type": "original_peer_reviewed_paper",
            "version": "2016",
            "access_date": ACCESS_DATE,
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC5070514/",
            "local_path": "",
            "claim_supported": "PheKB supports sharing, validation, and transport of phenotype algorithms, whose exact computability depends on the deposited artifact.",
        },
        {
            "evidence_id": "OMOP-1",
            "comparator": "OMOP CDM and ATLAS",
            "title": "OMOP Common Data Model v5.4",
            "source_type": "official_specification",
            "version": "5.4",
            "access_date": ACCESS_DATE,
            "url": "https://ohdsi.github.io/CommonDataModel/cdm54.html",
            "local_path": "",
            "claim_supported": "DRUG_EXPOSURE provides standardized drug, type, time, route, quantity, source value, and visit fields but no required literal administration-state field.",
        },
        {
            "evidence_id": "OMOP-2",
            "comparator": "OMOP CDM and ATLAS",
            "title": "The Book of OHDSI: Defining cohorts",
            "source_type": "official_documentation",
            "version": "current online edition",
            "access_date": ACCESS_DATE,
            "url": "https://ohdsi.github.io/TheBookOfOhdsi/Cohorts.html",
            "local_path": "",
            "claim_supported": "ATLAS-style cohort definitions are machine-executable against OMOP and support temporal inclusion logic.",
        },
        {
            "evidence_id": "FHIR-1",
            "comparator": "HL7 FHIR R4 medications",
            "title": "FHIR R4 Medications Module",
            "source_type": "official_specification",
            "version": "R4",
            "access_date": ACCESS_DATE,
            "url": "https://www.hl7.org/fhir/R4/medications-module.html",
            "local_path": "",
            "claim_supported": "FHIR separates medication request, dispense, and administration resources and defines links among workflow resources.",
        },
        {
            "evidence_id": "FHIR-2",
            "comparator": "HL7 FHIR R4 medications",
            "title": "FHIR R4 MedicationRequest definitions",
            "source_type": "official_specification",
            "version": "R4",
            "access_date": ACCESS_DATE,
            "url": "https://hl7.org/fhir/R4/medicationrequest-definitions.html",
            "local_path": "",
            "claim_supported": "MedicationRequest includes identifiers, authored time, status, dosage, prior-prescription, and encounter elements, many of which are optional.",
        },
        {
            "evidence_id": "FHIR-3",
            "comparator": "HL7 FHIR R4 medications",
            "title": "FHIR R4 MedicationAdministration",
            "source_type": "official_specification",
            "version": "R4",
            "access_date": ACCESS_DATE,
            "url": "https://hl7.org/fhir/R4/medicationadministration.html",
            "local_path": "",
            "claim_supported": "MedicationAdministration represents administration status, effective time, request linkage, dosage, route, method, and dose when populated.",
        },
        {
            "evidence_id": "FHIR-4",
            "comparator": "HL7 FHIR R4 medications",
            "title": "FHIR R4 MedicationDispense",
            "source_type": "official_specification",
            "version": "R4",
            "access_date": ACCESS_DATE,
            "url": "https://hl7.org/fhir/R4/medicationdispense.html",
            "local_path": "",
            "claim_supported": "MedicationDispense represents the supply workflow separately from request and administration.",
        },
        {
            "evidence_id": "CQL-1",
            "comparator": "HL7 CQL",
            "title": "Clinical Quality Language specification",
            "source_type": "official_specification",
            "version": "current published specification",
            "access_date": ACCESS_DATE,
            "url": "https://cql.hl7.org/01-introduction.html",
            "local_path": "",
            "claim_supported": "CQL is a machine-executable expression language with data-model bindings and temporal and clinical logic; source data provenance depends on the bound model and implementation.",
        },
        {
            "evidence_id": "RECORDPE-1",
            "comparator": "RECORD-PE",
            "title": "RECORD-PE reporting guideline",
            "source_type": "original_reporting_statement",
            "version": "2018",
            "access_date": ACCESS_DATE,
            "url": "https://www.equator-network.org/reporting-guidelines/record-pe/",
            "local_path": "",
            "claim_supported": "RECORD-PE specifies reporting expectations for pharmacoepidemiologic studies using routinely collected data; it is not an executable representation.",
        },
        {
            "evidence_id": "STARTRWE-1",
            "comparator": "STaRT-RWE",
            "title": "Structured template and reporting tool for real-world evidence",
            "source_type": "original_peer_reviewed_paper",
            "version": "2021",
            "access_date": ACCESS_DATE,
            "url": "https://www.bmj.com/content/372/bmj.m4856",
            "local_path": "",
            "claim_supported": "STaRT-RWE structures protocol and reporting decisions but does not itself execute EHR medication-source reconciliation.",
        },
        {
            "evidence_id": "HARPER-1",
            "comparator": "HARPER",
            "title": "HARmonized Protocol Template to Enhance Reproducibility",
            "source_type": "original_peer_reviewed_paper",
            "version": "2022",
            "access_date": ACCESS_DATE,
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9771861/",
            "local_path": "",
            "claim_supported": "HARPER improves transparent protocol specification for real-world evidence; it is reporting and design guidance rather than an execution engine.",
        },
    ]


def matrix_rows() -> list[dict[str, str]]:
    definitions: dict[str, dict[str, tuple[str, str, str]]] = {
        "medprov": {
            DIMENSIONS[0]: ("native", "Source role, table, deployment boundary, and observability gate are required operator elements.", "MEDPROV-1"),
            DIMENSIONS[1]: ("native", "Native identifiers, deterministic joins, deduplication, and revision policy are versioned fields.", "MEDPROV-1"),
            DIMENSIONS[2]: ("native", "Time origin, window, precedence, and assignment are frozen before execution.", "MEDPROV-1"),
            DIMENSIONS[3]: ("native", "Literal states are mapped explicitly and excluded literals remain visible.", "MEDPROV-1"),
            DIMENSIONS[4]: ("native", "Required route or dose fields can be declared and fail closed when absent.", "MEDPROV-1"),
            DIMENSIONS[5]: ("native", "Exposed, unexposed, unresolved, and unmeasurable are distinct terminal states.", "MEDPROV-1"),
            DIMENSIONS[6]: ("native", "Execution retains a patient-level provenance trace where data-use controls permit it.", "MEDPROV-1"),
            DIMENSIONS[7]: ("native", "Versioned YAML specifications execute through tested adapters and CLI commands.", "MEDPROV-1"),
            DIMENSIONS[8]: ("partial", "Adapters compile the canonical operator to four evaluated representations, not arbitrary clinical models.", "MEDPROV-1"),
        },
        "PheKB": {
            DIMENSIONS[0]: ("partial", "Algorithms can document data types and sites, but no universal medication-source schema is required.", "PHEKB-1"),
            DIMENSIONS[1]: ("implementation_dependent", "Native identifiers and revision chains depend on each deposited algorithm and site implementation.", "PHEKB-1"),
            DIMENSIONS[2]: ("implementation_dependent", "Temporal logic may be documented or coded, but no fixed cross-source assignment schema is mandated.", "PHEKB-1"),
            DIMENSIONS[3]: ("implementation_dependent", "Literal administration semantics depend on the artifact and local source mapping.", "PHEKB-1"),
            DIMENSIONS[4]: ("implementation_dependent", "Route and dose requirements are phenotype-specific.", "PHEKB-1"),
            DIMENSIONS[5]: ("unknown", "The cited platform description does not require a four-state measurability result.", "PHEKB-1"),
            DIMENSIONS[6]: ("implementation_dependent", "Trace availability depends on deposited code and local execution artifacts.", "PHEKB-1"),
            DIMENSIONS[7]: ("partial", "Some algorithms include executable code, while repository artifacts vary in computability.", "PHEKB-1"),
            DIMENSIONS[8]: ("implementation_dependent", "Transport is a platform goal but compilation across data models is not a universal native service.", "PHEKB-1"),
        },
        "OMOP CDM and ATLAS": {
            DIMENSIONS[0]: ("partial", "DRUG_EXPOSURE type and source values retain some source context but can collapse upstream workflow layers.", "OMOP-1"),
            DIMENSIONS[1]: ("partial", "A row identifier is native; cross-source identity and revision chains require source-specific extensions.", "OMOP-1"),
            DIMENSIONS[2]: ("partial", "Drug dates and cohort temporal criteria are native, but request-to-administration assignment is not standardized.", "OMOP-1;OMOP-2"),
            DIMENSIONS[3]: ("extension_required", "Literal given, held, and not-given states are not required DRUG_EXPOSURE fields.", "OMOP-1"),
            DIMENSIONS[4]: ("partial", "Route, quantity, dose unit, and sig fields exist but are optional and unevenly populated.", "OMOP-1"),
            DIMENSIONS[5]: ("extension_required", "Record absence is not a first-class distinction between unexposed and unmeasurable.", "OMOP-1"),
            DIMENSIONS[6]: ("implementation_dependent", "Cohort execution is auditable, but native source-event traces depend on ETL and result retention.", "OMOP-1;OMOP-2"),
            DIMENSIONS[7]: ("native", "ATLAS cohort definitions compile and execute against OMOP CDM.", "OMOP-2"),
            DIMENSIONS[8]: ("implementation_dependent", "The executable representation targets OMOP; non-OMOP compilation requires a separate mapping or ETL.", "OMOP-2"),
        },
        "HL7 FHIR R4 medications": {
            DIMENSIONS[0]: ("native", "Request, dispense, and administration are separate workflow resources.", "FHIR-1;FHIR-4"),
            DIMENSIONS[1]: ("partial", "Resource identifiers, version metadata, and workflow references exist, but cross-resource linkage is optional.", "FHIR-1;FHIR-2;FHIR-3"),
            DIMENSIONS[2]: ("partial", "Clinical timestamps are native; analytic windows and assignment rules require an external operator.", "FHIR-2;FHIR-3"),
            DIMENSIONS[3]: ("partial", "Administration status and dosage method carry semantics, but source literals and relocation vary by implementation.", "FHIR-3"),
            DIMENSIONS[4]: ("native", "Dosage route, method, and dose are representable, although optional.", "FHIR-2;FHIR-3"),
            DIMENSIONS[5]: ("extension_required", "FHIR statuses do not by themselves encode analytic unmeasurability caused by missing required fields.", "FHIR-2;FHIR-3"),
            DIMENSIONS[6]: ("partial", "References and versioning can support a trace when servers populate and retain them.", "FHIR-1;FHIR-2;FHIR-3"),
            DIMENSIONS[7]: ("implementation_dependent", "FHIR defines interoperable resources, not a medication-exposure estimand executor.", "FHIR-1"),
            DIMENSIONS[8]: ("implementation_dependent", "Resource mapping is standardized, but analytic-operator compilation is outside the medication resources.", "FHIR-1"),
        },
        "HL7 CQL": {
            DIMENSIONS[0]: ("implementation_dependent", "Source observability depends on the bound data model and implementation guide.", "CQL-1"),
            DIMENSIONS[1]: ("implementation_dependent", "Identifiers and revision relationships must be exposed by the selected model.", "CQL-1"),
            DIMENSIONS[2]: ("native", "The language supports temporal expressions and reusable parameterized logic.", "CQL-1"),
            DIMENSIONS[3]: ("implementation_dependent", "Literal event-state semantics depend on data-model bindings and value sets.", "CQL-1"),
            DIMENSIONS[4]: ("implementation_dependent", "Route and dose constraints are executable when the model exposes them.", "CQL-1"),
            DIMENSIONS[5]: ("partial", "Null and uncertainty can be represented, but a required four-state medication measurability contract is not native.", "CQL-1"),
            DIMENSIONS[6]: ("implementation_dependent", "Execution traces depend on the CQL engine and deployment.", "CQL-1"),
            DIMENSIONS[7]: ("native", "CQL is explicitly designed for machine-readable and executable clinical logic.", "CQL-1"),
            DIMENSIONS[8]: ("partial", "The language is reusable across model bindings, but equivalent source semantics still require model-specific libraries.", "CQL-1"),
        },
        "RECORD-PE": {
            DIMENSIONS[0]: ("reporting_only", "The statement asks investigators to report data sources and pharmacoepidemiologic methods.", "RECORDPE-1"),
            DIMENSIONS[1]: ("reporting_only", "Record linkage and coding decisions can be reported but are not executable fields.", "RECORDPE-1"),
            DIMENSIONS[2]: ("reporting_only", "Exposure timing and design choices are reporting items.", "RECORDPE-1"),
            DIMENSIONS[3]: ("reporting_only", "Event definitions can be described but no native literal-state representation is supplied.", "RECORDPE-1"),
            DIMENSIONS[4]: ("reporting_only", "Route and dose definitions can be reported.", "RECORDPE-1"),
            DIMENSIONS[5]: ("unknown", "A four-state source-measurability result is not specified in the cited guidance.", "RECORDPE-1"),
            DIMENSIONS[6]: ("reporting_only", "Provenance decisions may be documented, not emitted as a patient-level execution trace.", "RECORDPE-1"),
            DIMENSIONS[7]: ("not_applicable", "This is a reporting guideline.", "RECORDPE-1"),
            DIMENSIONS[8]: ("not_applicable", "This is a reporting guideline.", "RECORDPE-1"),
        },
        "STaRT-RWE": {
            DIMENSIONS[0]: ("reporting_only", "The template structures data-source and implementation decisions.", "STARTRWE-1"),
            DIMENSIONS[1]: ("reporting_only", "Identity decisions can be specified narratively.", "STARTRWE-1"),
            DIMENSIONS[2]: ("reporting_only", "Time zero, exposure windows, and design choices are protocol fields.", "STARTRWE-1"),
            DIMENSIONS[3]: ("reporting_only", "Event semantics can be declared but are not an executable source map.", "STARTRWE-1"),
            DIMENSIONS[4]: ("reporting_only", "Route and dose constraints can be pre-specified.", "STARTRWE-1"),
            DIMENSIONS[5]: ("unknown", "A first-class four-state medication measurability output is not specified.", "STARTRWE-1"),
            DIMENSIONS[6]: ("reporting_only", "The template improves traceability of decisions rather than patient-level provenance.", "STARTRWE-1"),
            DIMENSIONS[7]: ("not_applicable", "The template does not execute EHR reconciliation.", "STARTRWE-1"),
            DIMENSIONS[8]: ("not_applicable", "The template does not compile operators across data models.", "STARTRWE-1"),
        },
        "HARPER": {
            DIMENSIONS[0]: ("reporting_only", "The protocol template promotes explicit data-source and design reporting.", "HARPER-1"),
            DIMENSIONS[1]: ("reporting_only", "Identity and linkage rules can be specified in protocol text.", "HARPER-1"),
            DIMENSIONS[2]: ("reporting_only", "Temporal design decisions can be pre-specified.", "HARPER-1"),
            DIMENSIONS[3]: ("reporting_only", "Event semantics can be documented but are not compiled.", "HARPER-1"),
            DIMENSIONS[4]: ("reporting_only", "Route and dose requirements can be documented.", "HARPER-1"),
            DIMENSIONS[5]: ("unknown", "A required four-state source-measurability result is not specified.", "HARPER-1"),
            DIMENSIONS[6]: ("reporting_only", "Protocol transparency does not itself create patient-level source traces.", "HARPER-1"),
            DIMENSIONS[7]: ("not_applicable", "This is a harmonized protocol template.", "HARPER-1"),
            DIMENSIONS[8]: ("not_applicable", "This is a harmonized protocol template.", "HARPER-1"),
        },
    }
    rows = [
        {
            "comparator": comparator,
            "dimension": dimension,
            "status": values[dimension][0],
            "rationale": values[dimension][1],
            "evidence_ids": values[dimension][2],
        }
        for comparator, values in definitions.items()
        for dimension in DIMENSIONS
    ]
    if len(rows) != len(definitions) * len(DIMENSIONS):
        raise RuntimeError("Incomplete frozen comparison matrix")
    if any(row["status"] not in ALLOWED for row in rows):
        raise RuntimeError("Invalid comparison status")
    return rows


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    evidence = evidence_rows()
    matrix = matrix_rows()
    evidence_ids = {row["evidence_id"] for row in evidence}
    missing_sources = {
        evidence_id
        for row in matrix
        for evidence_id in row["evidence_ids"].split(";")
        if evidence_id not in evidence_ids
    }
    if missing_sources:
        raise RuntimeError(f"Unknown evidence IDs: {sorted(missing_sources)}")

    omop = json.loads(OMOP_SUMMARY.read_text(encoding="utf-8"))
    headline = omop["headline_findings"]
    executable = [
        {
            "fixture": "synthetic_four_unit_ppi",
            "operator": "ATLAS-style DRUG_EXPOSURE record existence",
            "provenance_extension": "not_used",
            "analysis_units": 4,
            "exposed": headline["synthetic_atlas_exposed_n"],
            "unexposed": 0,
            "unresolved": 0,
            "unmeasurable": 0,
            "semantic_result": "All four records classify as exposed; literal administration state is outside the cohort expression.",
        },
        {
            "fixture": "synthetic_four_unit_ppi",
            "operator": "medprov strict administration",
            "provenance_extension": "present",
            "analysis_units": 4,
            "exposed": headline["synthetic_medprov_exposed_n"],
            "unexposed": headline["synthetic_medprov_unexposed_n"],
            "unresolved": headline["synthetic_medprov_unresolved_n"],
            "unmeasurable": headline["synthetic_medprov_unmeasurable_n"],
            "semantic_result": "The same four records separate into four terminal provenance states.",
        },
        {
            "fixture": "synthetic_four_unit_ppi",
            "operator": "medprov strict administration",
            "provenance_extension": "removed",
            "analysis_units": 4,
            "exposed": 0,
            "unexposed": 0,
            "unresolved": 0,
            "unmeasurable": headline["synthetic_ablation_unmeasurable_n"],
            "semantic_result": "Removing literal event state makes all four units unmeasurable rather than silently unexposed.",
        },
        {
            "fixture": "public_mimic_omop_demo_ppi",
            "operator": "record existence versus strict administration",
            "provenance_extension": "absent_in_release",
            "analysis_units": headline["ppi_person_visit_units_n"],
            "exposed": headline["ppi_person_visit_units_n"],
            "unexposed": 0,
            "unresolved": 0,
            "unmeasurable": headline["real_strict_admin_unmeasurable_n"],
            "semantic_result": "Record existence is executable, but the strict administration construct is structurally unmeasurable without event state.",
        },
    ]
    write_csv(OUTPUT / "sota_evidence_sources.csv", evidence)
    write_csv(OUTPUT / "sota_comparison_matrix.csv", matrix)
    write_csv(OUTPUT / "executable_semantic_loss_comparator.csv", executable)

    summary: dict[str, Any] = {
        "schema_version": "1.0.0",
        "gate": "PASS_BOUNDED_SOTA_COMPARISON",
        "contract": {
            "path": CONTRACT.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(CONTRACT),
        },
        "comparators_n": len({row["comparator"] for row in matrix}),
        "dimensions_n": len(DIMENSIONS),
        "matrix_cells_n": len(matrix),
        "evidence_sources_n": len(evidence),
        "executable_comparator_rows_n": len(executable),
        "novelty_claim": "medprov complements existing standards with a versioned, adapter-aware medication-exposure provenance operator and fail-closed measurability states; it does not replace them",
        "no_superiority_score": True,
    }
    (OUTPUT / "sota_comparison_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT / "SOTA_COMPARISON_REPORT.md").write_text(
        "# Frozen state-of-the-art comparison\n\n"
        "**PASS_BOUNDED_SOTA_COMPARISON**\n\n"
        "The comparison covers eight representations or guidance families across nine frozen dimensions. No numeric superiority score was calculated. Existing standards solve complementary problems: FHIR separates clinical workflow resources, OMOP and ATLAS standardize and execute common-model cohorts, CQL executes clinical logic, PheKB disseminates phenotype algorithms, and RECORD-PE, STaRT-RWE, and HARPER improve reporting or protocol transparency.\n\n"
        "The bounded increment is an explicit medication-exposure provenance contract that fails closed when a required source, identity, event state, route, or dose is unavailable and that compiles through evaluated adapters. On the same four-unit OMOP fixture, record existence classified all four as exposed; a provenance-aware operator separated one exposed, one unexposed, one unresolved, and one unmeasurable unit; removing the event-state extension made all four unmeasurable.\n\n"
        "This is an executable semantic-loss comparison, not a phenotype-accuracy, clinical-validity, or performance benchmark.\n",
        encoding="utf-8",
    )
    output_manifest: list[dict[str, Any]] = [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(OUTPUT.iterdir())
        if path.is_file() and path.name != "manifest_sha256.csv"
    ]
    write_csv(OUTPUT / "manifest_sha256.csv", output_manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
