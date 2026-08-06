from __future__ import annotations

import csv
import gzip
import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

from medprov.adapters import get_adapter
from medprov.adapters.eicu import EicuAdapter
from medprov.adapters.mimic_fhir import MimicFHIRAdapter
from medprov.schema import load_document


def write_gzip_csv(path, fieldnames, rows):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def gzip_csv_bytes(fieldnames, rows):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(text.getvalue().encode("utf-8"))


def write_ndjson(path, resources, compressed=False):
    payload = "".join(json.dumps(resource) + "\n" for resource in resources)
    if compressed:
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(payload)
    else:
        path.write_text(payload, encoding="utf-8")


def strict_fhir_spec(repo_root):
    return deepcopy(
        load_document(repo_root / "examples" / "transport" / "fhir_demo_administration.yaml")
    )


def strict_omop_spec(repo_root):
    spec = deepcopy(
        load_document(repo_root / "examples" / "transport" / "omop_demo_ppi.yaml")
    )
    spec["operator_id"] = "test.omop_execution_branches"
    spec["target_event"] = "documented_administration"
    spec["source_layer"]["source_type"] = "administration"
    spec["identity_rule"].pop("ingredient_filter", None)
    spec["event_semantics_map"] = {
        "positive": ["administered"],
        "negative": ["held", "not given"],
        "excluded": ["flushed"],
        "unresolved": ["<all_other>"],
        "precedence": "source_priority",
        "normalization": {"trim": True, "lowercase": True, "null_token": "<blank>"},
    }
    spec["required_metadata"]["status"] = "required"
    return spec


def make_eicu_archive(path, n=100):
    patients = [
        {
            "patientunitstayid": str(index),
            "hospitalid": str((index - 1) % 10 + 1),
            "unittype": "Med-Surg ICU",
        }
        for index in range(1, n + 1)
    ]
    orders = [
        {
            "medicationid": str(index),
            "patientunitstayid": str(index),
            "drugorderoffset": "0",
            "drugstartoffset": "0",
            "drugname": "Metoclopramide",
            "dosage": "10 mg",
            "routeadmin": "IV",
            "frequency": "q6h",
            "drugstopoffset": "60",
        }
        for index in range(1, n + 1)
    ]
    infusions = [
        {
            "infusiondrugid": str(index),
            "patientunitstayid": str(index),
            "infusionoffset": "10",
            "drugname": "Metoclopramide",
            "drugrate": "1",
            "infusionrate": "",
            "drugamount": "",
            "volumeoffluid": "",
        }
        for index in range(1, n + 1)
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "eicu/patient.csv.gz",
            gzip_csv_bytes(["patientunitstayid", "hospitalid", "unittype"], patients),
        )
        archive.writestr(
            "eicu/medication.csv.gz", gzip_csv_bytes(list(orders[0]), orders)
        )
        archive.writestr(
            "eicu/infusionDrug.csv.gz", gzip_csv_bytes(list(infusions[0]), infusions)
        )
        archive.writestr(
            "eicu/hospital.csv.gz",
            gzip_csv_bytes(
                ["hospitalid"], [{"hospitalid": str(i)} for i in range(1, 11)]
            ),
        )
        archive.writestr(
            "eicu/treatment.csv.gz",
            gzip_csv_bytes(["treatmentid", "treatmentstring"], []),
        )


def test_native_csv_administration_preserves_four_states(repo_root, tmp_path):
    spec = load_document(
        repo_root / "examples" / "transport" / "native_demo_administration.yaml"
    )
    rows = [
        {"emar_id": "e1", "medication": "Pantoprazole", "event_txt": "Administered", "route": "IV"},
        {"emar_id": "e2", "medication": "Insulin regular", "event_txt": "Not Given", "route": "SC"},
        {"emar_id": "e3", "medication": "Metoclopramide", "event_txt": "Flushed", "route": "IV"},
        {"emar_id": "e4", "medication": "Potassium chloride", "event_txt": "", "route": "IV"},
        {"emar_id": "e5", "medication": "Unknown product", "event_txt": "Administered", "route": "IV"},
        {"emar_id": "e6", "medication": "Pantoprazole insulin", "event_txt": "Administered", "route": "IV"},
        {"emar_id": "e1", "medication": "Pantoprazole", "event_txt": "Not Given", "route": "IV"},
        {"emar_id": "e7", "medication": "Heparin flush", "event_txt": "Administered", "route": "IV"},
    ]
    write_gzip_csv(
        tmp_path / "emar.csv.gz", ["emar_id", "medication", "event_txt", "route"], rows
    )

    result = get_adapter("mimic_native").execute(spec, tmp_path)

    assert result.status == "executed"
    assert result.counts["analysis_units"] == 4
    assert result.counts["exposed"] == 1
    assert result.counts["unexposed"] == 1
    assert result.counts["unresolved"] == 2
    assert result.metrics == {
        "identity_unmapped_records": 2,
        "identity_ambiguous_records": 1,
        "excluded_semantics_records": 2,
    }


def test_native_csv_required_route_fails_closed_per_row(repo_root, tmp_path):
    spec = deepcopy(
        load_document(
            repo_root / "examples" / "transport" / "native_demo_administration.yaml"
        )
    )
    spec["required_metadata"]["route"] = "required"
    rows = [
        {"emar_id": "e1", "medication": "Pantoprazole", "event_txt": "Administered", "route": "IV"},
        {"emar_id": "e2", "medication": "Pantoprazole", "event_txt": "Administered", "route": ""},
    ]
    write_gzip_csv(
        tmp_path / "emar.csv.gz", ["emar_id", "medication", "event_txt", "route"], rows
    )

    result = get_adapter("mimic_native").execute(spec, tmp_path)

    assert result.counts["exposed"] == 1
    assert result.counts["unmeasurable"] == 1


@pytest.mark.parametrize(
    ("spec_name", "filename", "name_field"),
    [
        ("native_demo_request.yaml", "prescriptions.csv.gz", "drug"),
        ("native_demo_dispense.yaml", "pharmacy.csv.gz", "medication"),
    ],
)
def test_native_request_and_dispense_are_record_existence_units(
    repo_root, tmp_path, spec_name, filename, name_field
):
    spec = load_document(repo_root / "examples" / "transport" / spec_name)
    rows = [
        {"pharmacy_id": "p1", name_field: "Pantoprazole"},
        {"pharmacy_id": "p1", name_field: "Pantoprazole"},
        {"pharmacy_id": "p2", name_field: "Metoclopramide"},
        {"pharmacy_id": "p3", name_field: "Unknown product"},
    ]
    write_gzip_csv(tmp_path / filename, ["pharmacy_id", name_field], rows)

    result = get_adapter("mimic_native").execute(spec, tmp_path)

    assert result.status == "executed"
    assert result.counts["analysis_units"] == 2
    assert result.counts["exposed"] == 2
    assert result.metrics["identity_unmapped_records"] == 1


def test_native_demo_missing_source_is_explicit(repo_root, tmp_path):
    spec = load_document(
        repo_root / "examples" / "transport" / "native_demo_administration.yaml"
    )
    result = get_adapter("mimic_native").execute(spec, tmp_path)
    assert result.status == "not_executed_data_unavailable"
    assert result.executable is False
    assert "missing" in " ".join(result.warnings).lower()


def test_fhir_execution_covers_identity_semantics_metadata_and_dedup(repo_root, tmp_path):
    spec = strict_fhir_spec(repo_root)
    spec["required_metadata"]["route"] = "required"
    medications = [
        {
            "resourceType": "Medication",
            "id": "m1",
            "code": {"text": "Pantoprazole"},
            "identifier": [{"system": "urn:test", "value": "ppi-code"}],
        }
    ]
    administrations = [
        {
            "resourceType": "MedicationAdministration",
            "id": "a1",
            "status": "completed",
            "medicationReference": {"reference": "Medication/m1"},
            "dosage": {"route": {"text": "IV"}},
        },
        {
            "resourceType": "MedicationAdministration",
            "id": "a2",
            "status": "not-done",
            "medicationCodeableConcept": {"text": "Insulin regular"},
            "dosage": {"route": {"text": "SC"}},
        },
        {
            "resourceType": "MedicationAdministration",
            "id": "a3",
            "status": "in-progress",
            "medprovMedicationClass": "prokinetic",
            "dosage": {"route": {"text": "IV"}},
        },
        {
            "resourceType": "MedicationAdministration",
            "id": "a4",
            "status": "completed",
            "medprovMedicationClass": "electrolyte_replacement",
        },
        {
            "resourceType": "MedicationAdministration",
            "id": "a1",
            "status": "not-done",
            "medicationReference": {"reference": "Medication/m1"},
            "dosage": {"route": {"text": "IV"}},
        },
        {
            "resourceType": "MedicationAdministration",
            "id": "a5",
            "status": "completed",
            "medicationCodeableConcept": {"text": "Pantoprazole insulin"},
            "dosage": {"route": {"text": "IV"}},
        },
        {
            "resourceType": "MedicationAdministration",
            "id": "a6",
            "status": "completed",
            "medicationCodeableConcept": {"text": "Unknown product"},
            "dosage": {"route": {"text": "IV"}},
        },
    ]
    write_ndjson(tmp_path / "Medication.ndjson", medications)
    write_ndjson(tmp_path / "MedicationAdministration.ndjson.gz", administrations, compressed=True)

    result = get_adapter("mimic_fhir").execute(spec, tmp_path)

    assert result.status == "executed"
    assert result.counts["analysis_units"] == 5
    assert result.counts["exposed"] == 1
    assert result.counts["unexposed"] == 1
    assert result.counts["unresolved"] == 2
    assert result.counts["unmeasurable"] == 1
    assert result.metrics == {
        "identity_unmapped_records": 1,
        "identity_ambiguous_records": 1,
        "excluded_semantics_records": 0,
    }


def test_fhir_version_gate_is_fail_closed(repo_root, tmp_path):
    spec = strict_fhir_spec(repo_root)
    spec["data_model"]["model_version"] = "3.0-unmatched"
    write_ndjson(
        tmp_path / "MedicationAdministration.ndjson",
        [
            {
                "resourceType": "MedicationAdministration",
                "id": "a1",
                "status": "completed",
                "medprovMedicationClass": "stress_ulcer_prophylaxis",
            }
        ],
    )
    result = get_adapter("mimic_fhir").execute(spec, tmp_path)
    assert result.status == "not_executed_version_mismatch"
    assert result.executable is False


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("MimicMedicationAdministrationICU.ndjson", "MedicationAdministrationICU"),
        ("MedicationAdministration.ndjson", "MedicationAdministration"),
        ("MedicationRequest.ndjson", "MedicationRequest"),
        ("MedicationDispense.ndjson", "MedicationDispense"),
        ("Patient.ndjson", None),
    ],
)
def test_fhir_filename_profile_detection(filename, expected):
    assert MimicFHIRAdapter._event_profile_from_filename(Path(filename)) == expected


@pytest.mark.parametrize(
    ("logical", "resource", "expected"),
    [
        ("status", {"status": "completed"}, True),
        ("status", {"status": ""}, False),
        ("route", {"dosage": {"route": {"text": "IV"}}}, True),
        ("dose", {"dosage": {"dose": {"value": 1}}}, True),
        ("unit", {"dosage": {"dose": {"unit": "mg"}}}, True),
        ("unit", {"dosage": {"doseAndRate": [{"doseQuantity": {"code": "mg"}}]}}, True),
        ("frequency", {"dosageInstruction": [{"timing": {"repeat": {"frequency": 1}}}]}, True),
        ("unknown", {}, False),
    ],
)
def test_fhir_required_metadata_detection(logical, resource, expected):
    assert MimicFHIRAdapter._has_required(resource, logical) is expected


@pytest.mark.parametrize(
    ("resource", "expected"),
    [
        (
            {
                "resourceType": "MedicationRequest",
                "id": "fallback",
                "identifier": [
                    {
                        "system": "http://mimic.mit.edu/fhir/mimic/identifier/medication-request-phid",
                        "value": "native-request",
                    }
                ],
            },
            "native-request",
        ),
        (
            {
                "resourceType": "MedicationDispense",
                "id": "fallback",
                "identifier": [
                    {
                        "system": "http://mimic.mit.edu/fhir/mimic/identifier/medication-dispense",
                        "value": "native-dispense",
                    }
                ],
            },
            "native-dispense",
        ),
        ({"resourceType": "MedicationAdministration", "id": "admin-id"}, "admin-id"),
    ],
)
def test_fhir_native_unit_identifier(resource, expected):
    assert MimicFHIRAdapter._native_unit_id(resource) == expected


def test_fhir_code_mapping_can_resolve_or_detect_ambiguity():
    rules = []
    by_reference = {"m1": ("stress_ulcer_prophylaxis", "resolved")}
    by_code = {
        ("urn:test", "one"): {"insulin"},
        ("urn:test", "many"): {"insulin", "prokinetic"},
    }
    reference = {
        "medicationReference": {"reference": "Medication/m1"},
    }
    code = {
        "medicationCodeableConcept": {
            "coding": [{"system": "urn:test", "code": "one"}]
        }
    }
    ambiguous = {
        "medicationCodeableConcept": {
            "coding": [{"system": "urn:test", "code": "many"}]
        }
    }
    unmapped = {
        "medicationCodeableConcept": {
            "coding": [{"system": "urn:test", "code": "none"}]
        }
    }
    assert MimicFHIRAdapter._resource_class(reference, rules, by_reference, by_code) == (
        "stress_ulcer_prophylaxis",
        "resolved",
    )
    assert MimicFHIRAdapter._resource_class(code, rules, by_reference, by_code) == (
        "insulin",
        "resolved",
    )
    assert MimicFHIRAdapter._resource_class(ambiguous, rules, by_reference, by_code) == (
        None,
        "ambiguous",
    )
    assert MimicFHIRAdapter._resource_class(unmapped, rules, by_reference, by_code) == (
        None,
        "unmapped",
    )


def test_eicu_adapter_executes_the_constructed_positive_control(repo_root, tmp_path):
    archive = tmp_path / "eicu-positive-control.zip"
    make_eicu_archive(archive)
    spec = load_document(
        repo_root / "examples" / "transport" / "eicu_six_class_reconciliation.yaml"
    )

    result = get_adapter("eicu").execute(spec, archive)

    assert result.status == "executed"
    assert result.counts["exposed"] == 100
    assert result.metrics["interpretation"].startswith("Interface semantic comparison")


def test_eicu_exact_cross_source_key_is_explicitly_unmeasurable(repo_root, tmp_path):
    archive = tmp_path / "eicu-exact-key.zip"
    make_eicu_archive(archive, n=1)
    spec = deepcopy(
        load_document(
            repo_root / "examples" / "transport" / "eicu_six_class_reconciliation.yaml"
        )
    )
    spec["identity_rule"]["match_mode"] = "exact_native_key"

    adapter = get_adapter("eicu")
    capability = adapter.capability(spec, archive)
    result = adapter.execute(spec, archive)

    assert capability.supported is False
    assert capability.dimension_status["identity_rule"] == "unsupported_exact_cross_source_identity"
    assert result.status == "unmeasurable"
    assert result.executable is False


def test_eicu_member_discovery_supports_directory_zip_and_absence(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "medication.csv.gz").write_bytes(b"placeholder")
    archive = tmp_path / "members.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("eicu/patient.csv.gz", b"placeholder")

    assert EicuAdapter._members(None) == []
    assert EicuAdapter._members(tmp_path / "missing") == []
    assert EicuAdapter._members(extracted) == ["medication.csv.gz"]
    assert EicuAdapter._members(archive) == ["eicu/patient.csv.gz"]


@pytest.mark.parametrize(
    ("adapter_name", "spec_name", "implementation_key"),
    [
        ("mimic_native", "native_demo_administration.yaml", "raw_csv_execution"),
        ("mimic_fhir", "fhir_demo_administration.yaml", "resources"),
        ("eicu", "eicu_six_class_reconciliation.yaml", "streaming_zip"),
    ],
)
def test_transport_specs_compile_to_aggregate_traceable_plans(
    repo_root, adapter_name, spec_name, implementation_key
):
    spec = load_document(repo_root / "examples" / "transport" / spec_name)
    plan = get_adapter(adapter_name).compile(spec, None)
    assert plan.adapter == adapter_name
    assert plan.operator_id == spec["operator_id"]
    assert plan.aggregate_only is True
    assert plan.output_profile == spec["output_specification"]["profile"]
    assert implementation_key in plan.implementation


def test_omop_execution_resolves_concepts_and_preserves_failure_states(repo_root, tmp_path):
    spec = strict_omop_spec(repo_root)
    fieldnames = [
        "drug_exposure_id",
        "person_id",
        "visit_occurrence_id",
        "drug_concept_id",
        "drug_source_concept_id",
        "drug_source_value",
        "medprov_class",
        "medprov_event_state",
    ]
    rows = [
        {"drug_exposure_id": "1", "person_id": "1", "visit_occurrence_id": "10", "drug_concept_id": "40790", "drug_source_concept_id": "", "drug_source_value": "", "medprov_class": "", "medprov_event_state": "administered"},
        {"drug_exposure_id": "2", "person_id": "1", "visit_occurrence_id": "10", "drug_concept_id": "", "drug_source_concept_id": "", "drug_source_value": "Pantoprazole", "medprov_class": "stress_ulcer_prophylaxis", "medprov_event_state": "held"},
        {"drug_exposure_id": "3", "person_id": "2", "visit_occurrence_id": "20", "drug_concept_id": "", "drug_source_concept_id": "", "drug_source_value": "Pantoprazole", "medprov_class": "stress_ulcer_prophylaxis", "medprov_event_state": "unknown"},
        {"drug_exposure_id": "4", "person_id": "3", "visit_occurrence_id": "30", "drug_concept_id": "", "drug_source_concept_id": "", "drug_source_value": "Pantoprazole", "medprov_class": "stress_ulcer_prophylaxis", "medprov_event_state": ""},
        {"drug_exposure_id": "5", "person_id": "4", "visit_occurrence_id": "40", "drug_concept_id": "", "drug_source_concept_id": "", "drug_source_value": "Unknown product", "medprov_class": "", "medprov_event_state": "administered"},
        {"drug_exposure_id": "6", "person_id": "", "visit_occurrence_id": "", "drug_concept_id": "", "drug_source_concept_id": "", "drug_source_value": "Pantoprazole", "medprov_class": "stress_ulcer_prophylaxis", "medprov_event_state": "administered"},
    ]
    with (tmp_path / "DRUG_EXPOSURE.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with (tmp_path / "concept.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["concept_id", "concept_name"])
        writer.writeheader()
        writer.writerow({"concept_id": "40790", "concept_name": "Pantoprazole"})

    result = get_adapter("omop").execute(spec, tmp_path)

    assert result.status == "executed"
    assert result.counts == {
        "analysis_units": 4,
        "exposed": 2,
        "unexposed": 0,
        "unresolved": 1,
        "unmeasurable": 1,
    }
    assert result.metrics["matched_source_rows"] == 5
    assert result.metrics["identity_unmapped_rows"] == 1
    assert result.metrics["concept_dictionary_available"] is True
