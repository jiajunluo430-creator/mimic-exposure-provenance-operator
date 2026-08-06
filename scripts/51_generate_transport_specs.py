#!/usr/bin/env python3
"""Generate paired native/FHIR plus OMOP/eICU transport specifications."""

from __future__ import annotations

import argparse
import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "transport"
CODE_LIST = ROOT / "config" / "drug_class_whitelist_v1.0.csv"
FHIR_CONTRACT = ROOT / "contracts" / "FHIR_TRANSPORT_CONTRACT_v1.0_2026-08-05.md"
OMOP_CONTRACT = ROOT / "contracts" / "OMOP_CAPABILITY_CONTRACT_v1.0_2026-08-05.md"
EICU_CONTRACT = ROOT / "contracts" / "EICU_ADAPTER_CONTRACT_v1.0_2026-08-05.md"
GENERATOR = Path(__file__).resolve()
GENERATED_AT = "2026-08-05T00:00:00Z"

CLASSES = [
    "stress_ulcer_prophylaxis",
    "vte_prophylaxis",
    "intra_abdominal_antibiotics",
    "electrolyte_replacement",
    "prokinetic",
    "insulin",
]
PPI = [
    "pantoprazole",
    "omeprazole",
    "lansoprazole",
    "esomeprazole",
    "rabeprazole",
    "dexlansoprazole",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def common_provenance(contract: Path) -> dict[str, Any]:
    return {
        "author": "N1 medication exposure provenance investigators",
        "date": "2026-08-05",
        "contract_path": str(contract.relative_to(ROOT)).replace("\\", "/"),
        "contract_sha256": sha256_file(contract),
        "generator": "scripts/51_generate_transport_specs.py",
        "generator_sha256": sha256_file(GENERATOR),
        "generated_at_utc": GENERATED_AT,
    }


def code_list(classes: list[str], ingredients: list[str] | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "vocabulary": "Frozen RxNorm-referenced name whitelist",
        "vocabulary_version": "drug_class_whitelist_v1.0",
        "code_list": {
            "path": "config/drug_class_whitelist_v1.0.csv",
            "sha256": sha256_file(CODE_LIST),
            "tier": "strict",
        },
        "native_keys": ["subject", "encounter", "native_source_id", "medication_class"],
        "match_mode": "composite",
        "deduplication_unit": ["native_source_id", "medication_class"],
        "revision_handling": "collapse_to_unit",
        "class_filter": classes,
        "negative_match_rule": "apply frozen row-specific negative_regex before class assignment",
    }
    if ingredients is not None:
        value["ingredient_filter"] = ingredients
    return value


def observability(rule: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "rule": rule,
        "deployment_start": None,
        "deployment_end": None,
        "failure_state": "unmeasurable",
    }


def time_window(rule: str) -> dict[str, Any]:
    return {
        "origin": "visit_start",
        "assignment_timestamp": "recorded_time",
        "start_offset_hours": None,
        "end_offset_hours": None,
        "lower_inclusive": True,
        "upper_inclusive": True,
        "grace_before_hours": 0,
        "grace_after_hours": 0,
        "censoring_boundary": "visit_end",
        "window_rule": rule,
    }


def metadata(status: str = "optional") -> dict[str, Any]:
    return {
        "route": "optional",
        "dose": "optional",
        "unit": "optional",
        "frequency": "optional",
        "status": status,
        "missing_policy": "unmeasurable",
        "constraints": [],
    }


def output(profile: str = "event_classification") -> dict[str, Any]:
    return {
        "profile": profile,
        "aggregate_only": True,
        "allow_patient_level": False,
        "trace_level": "aggregate",
        "classifications": ["exposed", "unexposed", "unresolved", "unmeasurable"],
        "formats": ["json", "markdown", "html", "csv"],
    }


def base(operator_id: str, construct: str, target: str, contract: Path) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "operator_id": operator_id,
        "operator_version": "1.0.0",
        "clinical_construct": construct,
        "analysis_unit": "native source record x medication class",
        "target_event": target,
        "data_model": {},
        "provenance": common_provenance(contract),
    }


def semantics(role: str, representation: str) -> dict[str, Any]:
    if role == "order":
        positive = (
            ["active", "on-hold", "cancelled", "completed", "stopped", "draft"]
            if representation == "fhir"
            else ["record_exists"]
        )
        negative = ["entered-in-error"] if representation == "fhir" else []
        unresolved = ["unknown", "<blank>"] if representation == "fhir" else []
        excluded: list[str] = []
    elif role == "dispense":
        positive = ["completed"] if representation == "fhir" else ["record_exists"]
        negative = ["declined", "entered-in-error"] if representation == "fhir" else []
        unresolved = (
            ["preparation", "in-progress", "cancelled", "on-hold", "unknown", "<blank>"]
            if representation == "fhir"
            else []
        )
        excluded = []
    else:
        if representation == "fhir":
            positive = ["completed"]
            negative = ["not-done", "entered-in-error"]
            excluded = []
            unresolved = ["in-progress", "on-hold", "stopped", "unknown", "<blank>"]
        else:
            positive = [
                "administered",
                "delayed administered",
                "partial administered",
                "applied",
                "started",
            ]
            negative = ["not given", "held", "refused"]
            excluded = ["flushed", "confirmed", "<blank>"]
            unresolved = ["<all_other>"]
    return {
        "positive": positive,
        "negative": negative,
        "excluded": excluded,
        "unresolved": unresolved,
        "precedence": "source_priority",
        "normalization": {"trim": True, "lowercase": True, "null_token": "<blank>"},
    }


def paired_medication_specs() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    roles = {
        "request": ("order", "order", "hosp/prescriptions", "MedicationRequest"),
        "dispense": ("dispense", "dispense", "hosp/pharmacy", "MedicationDispense"),
        "administration": (
            "documented_administration",
            "administration",
            "hosp/emar",
            "MedicationAdministration",
        ),
    }
    for label, (target, source_type, native_source, fhir_source) in roles.items():
        construct = f"matched_demo_six_class_{label}_exposure"
        native = base(f"transport.native_demo_{label}", construct, target, FHIR_CONTRACT)
        native.update(
            {
                "data_model": {
                    "adapter": "mimic_native",
                    "model_name": "MIMIC-IV native",
                    "model_version": "2.2-demo-matched",
                },
                "source_layer": {
                    "tables_or_resources": [native_source],
                    "source_type": source_type,
                    "observability_gate": observability(
                        "all records in the official MIMIC-IV demo v2.2 source"
                    ),
                },
                "identity_rule": code_list(CLASSES),
                "time_origin_window": time_window(
                    "whole linked hospital encounter in the matched public demo"
                ),
                "event_semantics_map": semantics(source_type, "native"),
                "required_metadata": metadata(
                    "required" if source_type == "administration" else "optional"
                ),
                "output_specification": output(),
            }
        )
        fhir = deepcopy(native)
        fhir["operator_id"] = f"transport.fhir_demo_{label}"
        fhir["data_model"] = {
            "adapter": "mimic_fhir",
            "model_name": "MIMIC-IV-on-FHIR",
            "model_version": "2.1.0-demo-matched",
        }
        fhir["source_layer"]["tables_or_resources"] = [fhir_source, "Medication"]
        fhir["source_layer"]["observability_gate"]["rule"] = (
            "all resources in the official MIMIC-IV-on-FHIR demo v2.1.0"
        )
        fhir["event_semantics_map"] = semantics(source_type, "fhir")
        result[f"native_demo_{label}.yaml"] = native
        result[f"fhir_demo_{label}.yaml"] = fhir
    return result


def additional_specs() -> dict[str, dict[str, Any]]:
    omop = base(
        "transport.omop_demo_ppi",
        "omop_demo_ppi_drug_record_capability",
        "documentation",
        OMOP_CONTRACT,
    )
    omop.update(
        {
            "analysis_unit": "person_id x visit_occurrence_id x medication class",
            "data_model": {
                "adapter": "omop",
                "model_name": "OMOP CDM",
                "model_version": "v0.9-demo-observed-schema",
            },
            "source_layer": {
                "tables_or_resources": ["DRUG_EXPOSURE"],
                "source_type": "mixed",
                "observability_gate": observability(
                    "official 100-patient v0.9 demo; capability only"
                ),
            },
            "identity_rule": code_list(["stress_ulcer_prophylaxis"], PPI),
            "time_origin_window": time_window(
                "drug exposure start during linked visit; no imputed end"
            ),
            "event_semantics_map": {
                "positive": ["record_exists"],
                "negative": [],
                "excluded": [],
                "unresolved": ["source_role_not_specific"],
                "precedence": "source_priority",
                "normalization": {"trim": True, "lowercase": True, "null_token": "<blank>"},
            },
            "required_metadata": metadata("optional"),
            "output_specification": output("capability_only"),
        }
    )
    omop_strict = deepcopy(omop)
    omop_strict["operator_id"] = "transport.omop_synthetic_ppi_administration"
    omop_strict["clinical_construct"] = "synthetic_ppi_strict_documented_administration"
    omop_strict["target_event"] = "documented_administration"
    omop_strict["data_model"]["model_version"] = "synthetic-v1"
    omop_strict["source_layer"]["source_type"] = "administration"
    omop_strict["source_layer"]["observability_gate"]["rule"] = (
        "frozen synthetic OMOP fixture with optional medprov_event_state extension"
    )
    omop_strict["event_semantics_map"] = semantics("administration", "native")
    omop_strict["required_metadata"] = metadata("required")
    omop_strict["output_specification"] = output("event_classification")
    eicu = base(
        "transport.eicu_six_class_reconciliation",
        "eicu_six_class_same_class_window_reconciliation",
        "reconciliation",
        EICU_CONTRACT,
    )
    eicu.update(
        {
            "analysis_unit": "patientunitstayid x medication class x medicationid",
            "data_model": {
                "adapter": "eicu",
                "model_name": "eICU-CRD",
                "model_version": "2.0",
            },
            "source_layer": {
                "tables_or_resources": ["medication", "infusionDrug", "patient", "hospital"],
                "source_type": "reconciliation",
                "observability_gate": observability(
                    "class-specific frozen gate of >=100 valid orders, >=100 administration-like "
                    "events, >=10 hospitals with both sources, and >=80% valid order intervals"
                ),
            },
            "identity_rule": code_list(CLASSES),
            "time_origin_window": {
                "origin": "custom",
                "assignment_timestamp": "custom",
                "start_offset_hours": -2,
                "end_offset_hours": None,
                "lower_inclusive": True,
                "upper_inclusive": True,
                "grace_before_hours": 2,
                "grace_after_hours": 6,
                "censoring_boundary": "custom",
                "window_rule": (
                    "same stay and class; infusionoffset in [order_start-120 minutes, "
                    "order_stop+360 minutes]; no stop imputation"
                ),
            },
            "event_semantics_map": {
                "positive": ["drug-specific label and positive numeric rate/value"],
                "negative": [],
                "excluded": ["treatment documentation"],
                "unresolved": ["nonpositive or missing rate/value", "missing offset"],
                "precedence": "source_priority",
                "normalization": {"trim": True, "lowercase": True, "null_token": "<blank>"},
            },
            "required_metadata": metadata("optional"),
            "output_specification": output("capability_only"),
        }
    )
    return {
        "omop_demo_ppi.yaml": omop,
        "omop_synthetic_ppi_administration.yaml": omop_strict,
        "eicu_six_class_reconciliation.yaml": eicu,
    }


def specifications() -> dict[str, dict[str, Any]]:
    return {**paired_medication_specs(), **additional_specs()}


def write_specs(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, document in specifications().items():
        path = output_dir / filename
        rendered = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
        path.write_text(
            "# AUTO-GENERATED by scripts/51_generate_transport_specs.py; do not edit manually.\n"
            + rendered,
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    for path in write_specs(args.out.resolve()):
        print(f"WROTE {path} sha256={sha256_file(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
