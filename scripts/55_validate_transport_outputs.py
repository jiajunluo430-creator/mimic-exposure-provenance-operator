#!/usr/bin/env python3
"""Validate the frozen FHIR, OMOP, and eICU transport output packages."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "transport_validation_v0_1_0"
PACKAGES = {
    "fhir": ROOT / "outputs" / "transport_evaluation_v0_1_0",
    "omop": ROOT / "outputs" / "omop_evaluation_v0_1_0",
    "eicu": ROOT / "outputs" / "eicu_transport_v0_1_0",
}
SUMMARY_FILES = {
    "fhir": "fhir_transport_summary.json",
    "omop": "omop_evaluation_summary.json",
    "eicu": "eicu_transport_summary.json",
}
FORBIDDEN_PATIENT_ID_COLUMNS = {
    "subject_id",
    "hadm_id",
    "stay_id",
    "patientunitstayid",
    "pharmacy_id",
    "poe_id",
    "emar_id",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


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


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected object: {path}")
    return value


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    def check(scope: str, check_id: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append(
            {
                "scope": scope,
                "check_id": check_id,
                "status": "PASS" if passed else "FAIL",
                "observed": observed,
                "expected": expected,
            }
        )

    summaries: dict[str, dict[str, Any]] = {}
    for name, directory in PACKAGES.items():
        summary_path = directory / SUMMARY_FILES[name]
        manifest_path = directory / "manifest_sha256.csv"
        summaries[name] = load_json(summary_path)
        manifest = read_csv(manifest_path)
        manifest_names = {row["file"] for row in manifest}
        actual_names = {
            path.name for path in directory.iterdir() if path.is_file() and path.name != manifest_path.name
        }
        check(name, "manifest_file_set", manifest_names == actual_names, len(manifest_names), len(actual_names))
        manifest_valid = True
        for row in manifest:
            path = directory / row["file"]
            manifest_valid &= (
                path.is_file()
                and path.stat().st_size == int(row["bytes"])
                and sha256_file(path) == row["sha256"].lower()
            )
        check(name, "manifest_hashes_and_sizes", manifest_valid, manifest_valid, True)
        check(
            name,
            "nonempty_outputs",
            all(path.stat().st_size > 0 for path in directory.iterdir() if path.is_file()),
            "all files nonempty",
            "all files nonempty",
        )

        contract = summaries[name]["contract"]
        contract_path = ROOT / contract["path"]
        check(
            name,
            "frozen_contract_hash",
            contract_path.is_file() and sha256_file(contract_path) == contract["sha256"],
            sha256_file(contract_path) if contract_path.is_file() else "missing",
            contract["sha256"],
        )

        csv_headers: list[str] = []
        for path in directory.glob("*.csv"):
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                csv_headers.extend(csv.DictReader(handle).fieldnames or [])
        leaked = sorted(FORBIDDEN_PATIENT_ID_COLUMNS.intersection(csv_headers))
        check(name, "no_patient_identifier_columns", not leaked, "|".join(leaked) or "none", "none")

    fhir = summaries["fhir"]
    fhir_head = fhir["headline_findings"]
    check("fhir", "decision_gate", fhir["gate"] == "PASS_FUNCTIONAL_CROSS_SCHEMA", fhir["gate"], "PASS_FUNCTIONAL_CROSS_SCHEMA")
    check(
        "fhir",
        "dispense_exact_id_class_parity",
        fhir_head["dispense_exact_id_class_matches_n"] == fhir_head["dispense_records_n"],
        fhir_head["dispense_exact_id_class_matches_n"],
        fhir_head["dispense_records_n"],
    )
    check(
        "fhir",
        "request_time_exactness",
        fhir_head["request_pharmacy_time_exact_n"] == fhir_head["request_pharmacy_time_pairs_n"],
        fhir_head["request_pharmacy_time_exact_n"],
        fhir_head["request_pharmacy_time_pairs_n"],
    )
    check(
        "fhir",
        "administration_time_pair_bound",
        fhir_head["admin_first_time_exact_n"] <= fhir_head["admin_first_time_pairs_n"],
        fhir_head["admin_first_time_exact_n"],
        f"<= {fhir_head['admin_first_time_pairs_n']}",
    )

    omop = summaries["omop"]
    omop_head = omop["headline_findings"]
    check("omop", "real_demo_gate", omop["real_demo_gate"] == "EXECUTED_CAPABILITY_SMOKE_TEST", omop["real_demo_gate"], "EXECUTED_CAPABILITY_SMOKE_TEST")
    check("omop", "synthetic_gate", omop["synthetic_gate"] == "PASS_DETERMINISTIC_SEMANTIC_ABLATION", omop["synthetic_gate"], "PASS_DETERMINISTIC_SEMANTIC_ABLATION")
    check(
        "omop",
        "strict_state_missing_is_unmeasurable",
        omop_head["real_strict_admin_unmeasurable_n"] == omop_head["ppi_person_visit_units_n"],
        omop_head["real_strict_admin_unmeasurable_n"],
        omop_head["ppi_person_visit_units_n"],
    )
    semantic_total = sum(
        omop_head[key]
        for key in (
            "synthetic_medprov_exposed_n",
            "synthetic_medprov_unexposed_n",
            "synthetic_medprov_unresolved_n",
            "synthetic_medprov_unmeasurable_n",
        )
    )
    check("omop", "synthetic_four_state_partition", semantic_total == 4, semantic_total, 4)
    check("omop", "atlas_record_existence_exposed", omop_head["synthetic_atlas_exposed_n"] == 4, omop_head["synthetic_atlas_exposed_n"], 4)
    for input_name, expected_hash in omop["inputs"].items():
        candidate = next(
            (
                path
                for base in (ROOT / "examples", ROOT / "tests" / "fixtures")
                for path in base.rglob("*")
                if path.is_file() and sha256_file(path) == expected_hash
            ),
            None,
        )
        check("omop", f"input_hash_{input_name}", candidate is not None, candidate.relative_to(ROOT).as_posix() if candidate else "missing", expected_hash)

    eicu = summaries["eicu"]
    check("eicu", "decision_gate", eicu["gate"] == "EXECUTED_INTERFACE_SEMANTIC_COMPARISON", eicu["gate"], "EXECUTED_INTERFACE_SEMANTIC_COMPARISON")
    count_sum = sum(eicu["counts"][key] for key in ("exposed", "unexposed", "unresolved", "unmeasurable"))
    check("eicu", "four_state_count_conservation", count_sum == eicu["counts"]["analysis_units"], count_sum, eicu["counts"]["analysis_units"])
    gate_rows = read_csv(PACKAGES["eicu"] / "eicu_feasibility_gates.csv")
    passed = sorted(row["medication_class"] for row in gate_rows if truthy(row["gate_pass"]))
    failed = sorted(row["medication_class"] for row in gate_rows if not truthy(row["gate_pass"]))
    check("eicu", "passed_class_list_consistency", passed == sorted(eicu["classes_passed"]), "|".join(passed), "|".join(sorted(eicu["classes_passed"])))
    check("eicu", "failed_class_list_consistency", failed == sorted(eicu["classes_failed"]), "|".join(failed), "|".join(sorted(eicu["classes_failed"])))
    ambiguity_rows = read_csv(PACKAGES["eicu"] / "eicu_ambiguous_identity_labels.csv")
    affected = {
        medication_class
        for row in ambiguity_rows
        if int(row["rows_n"]) > 0
        for medication_class in row["matched_classes"].split("|")
    }
    check("eicu", "ambiguous_classes_fail_closed", affected.issubset(set(failed)), "|".join(sorted(affected)), "subset of failed classes")
    integrity_rows = read_csv(PACKAGES["eicu"] / "eicu_used_member_integrity.csv")
    check("eicu", "zip_member_integrity", all(truthy(row["integrity_pass"]) for row in integrity_rows), sum(truthy(row["integrity_pass"]) for row in integrity_rows), len(integrity_rows))
    spec = eicu["spec"]
    spec_path = ROOT / spec["path"]
    check("eicu", "frozen_spec_hash", spec_path.is_file() and sha256_file(spec_path) == spec["sha256"], sha256_file(spec_path) if spec_path.is_file() else "missing", spec["sha256"])

    failed_checks = [row for row in checks if row["status"] == "FAIL"]
    gate = "PASS_TRANSPORT_PACKAGE_VALIDATION" if not failed_checks else "FAIL_TRANSPORT_PACKAGE_VALIDATION"
    write_csv(OUTPUT / "transport_validation_checks.csv", checks)
    summary: dict[str, Any] = {
        "schema_version": "1.0.0",
        "gate": gate,
        "checks_n": len(checks),
        "passed_n": len(checks) - len(failed_checks),
        "failed_n": len(failed_checks),
        "validated_packages": list(PACKAGES),
        "claim_boundary": "software-output integrity and internal consistency; not clinical validation",
    }
    (OUTPUT / "transport_validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT / "TRANSPORT_VALIDATION_REPORT.md").write_text(
        "# Cross-model transport package validation\n\n"
        f"**{gate}**\n\n"
        f"{summary['passed_n']}/{summary['checks_n']} checks passed. "
        "The checks cover artifact manifests, frozen contracts, aggregate privacy, "
        "and pre-specified cross-model invariants. This is software-output validation, "
        "not clinical external validation.\n",
        encoding="utf-8",
    )
    output_manifest: list[dict[str, Any]] = [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(OUTPUT.iterdir())
        if path.is_file() and path.name != "manifest_sha256.csv"
    ]
    write_csv(OUTPUT / "manifest_sha256.csv", output_manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failed_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
