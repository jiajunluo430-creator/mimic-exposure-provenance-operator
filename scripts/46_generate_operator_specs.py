#!/usr/bin/env python3
"""Generate the seven frozen medication-exposure operator examples.

The examples are derived from the binding analysis contract, drug-class
whitelist, and event-semantics mapping.  They are deliberately generated rather
than hand-copied so a code-list or generator change produces a visible hash
change in every affected operator.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "analysis_contract_v1.0_2026-07-29.md"
CODE_LIST = ROOT / "config" / "drug_class_whitelist_v1.0.csv"
SEMANTICS = ROOT / "config" / "event_semantics_v1.0.csv"
GENERATOR = Path(__file__).resolve()
DEFAULT_OUTPUT = ROOT / "examples"
GENERATION_DATE = "2026-08-05"
GENERATION_TIME = "2026-08-05T00:00:00Z"

EXPECTED_CLASSES = (
    "stress_ulcer_prophylaxis",
    "vte_prophylaxis",
    "intra_abdominal_antibiotics",
    "electrolyte_replacement",
    "prokinetic",
    "insulin",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_whitelist() -> tuple[list[str], list[str]]:
    with CODE_LIST.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    strict_classes = list(
        dict.fromkeys(row["drug_class"] for row in rows if row["tier"] == "strict")
    )
    if tuple(strict_classes) != EXPECTED_CLASSES:
        raise RuntimeError(
            "Frozen strict class gate failed: "
            f"observed={strict_classes!r}, expected={list(EXPECTED_CLASSES)!r}"
        )
    ppi = list(
        dict.fromkeys(
            row["ingredient"]
            for row in rows
            if row["drug_class"] == "stress_ulcer_prophylaxis"
            and row["subclass"] == "PPI"
            and row["tier"] == "strict"
        )
    )
    if not ppi:
        raise RuntimeError("No strict PPI ingredients found in frozen whitelist")
    return strict_classes, ppi


def read_semantics() -> dict[str, list[str]]:
    grouped = {"positive": [], "negative": [], "excluded": [], "unresolved": []}
    with SEMANTICS.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            value = row["normalized_event_txt"]
            category = row["category"]
            if category == "given_strict":
                grouped["positive"].append(value)
            elif category == "not_given":
                grouped["negative"].append(value)
            elif category in {"flushed", "confirmed", "blank"}:
                grouped["excluded"].append(value)
            else:
                grouped["unresolved"].append(value)
    required_excluded = {"flushed", "confirmed", "<blank>"}
    if not required_excluded.issubset(grouped["excluded"]):
        raise RuntimeError("Frozen separate-category semantic gate failed")
    return grouped


def provenance() -> dict[str, Any]:
    return {
        "author": "N1 medication exposure provenance investigators",
        "date": GENERATION_DATE,
        "contract_path": "contracts/analysis_contract_v1.0_2026-07-29.md",
        "contract_sha256": sha256_file(CONTRACT),
        "generator": "scripts/46_generate_operator_specs.py",
        "generator_sha256": sha256_file(GENERATOR),
        "generated_at_utc": GENERATION_TIME,
    }


def event_map(kind: str, frozen: dict[str, list[str]]) -> dict[str, Any]:
    if kind == "administration":
        return {
            **deepcopy(frozen),
            "precedence": "detail_override",
            "normalization": {"trim": True, "lowercase": True, "null_token": "<blank>"},
        }
    return {
        "positive": ["active_order"],
        "negative": ["cancelled", "discontinued_before_active"],
        "excluded": [],
        "unresolved": ["missing_or_unlinked_poe"],
        "precedence": "source_priority",
        "normalization": {"trim": True, "lowercase": True, "null_token": "<blank>"},
    }


def metadata(
    *,
    route: str = "optional",
    dose: str = "optional",
    unit: str = "optional",
    frequency: str = "ignored",
    status: str = "required",
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "route": route,
        "dose": dose,
        "unit": unit,
        "frequency": frequency,
        "status": status,
        "missing_policy": "unmeasurable",
        "constraints": constraints or [],
    }


def window(
    *,
    origin: str,
    assignment: str,
    start: float | None,
    end: float | None,
    censor: str,
    rule: str,
    before: float = 0,
    after: float = 0,
) -> dict[str, Any]:
    return {
        "origin": origin,
        "assignment_timestamp": assignment,
        "start_offset_hours": start,
        "end_offset_hours": end,
        "lower_inclusive": True,
        "upper_inclusive": True,
        "grace_before_hours": before,
        "grace_after_hours": after,
        "censoring_boundary": censor,
        "window_rule": rule,
    }


def source(
    tables: list[str],
    source_type: str,
    rule: str,
    *,
    enabled: bool = True,
    failure_state: str = "unmeasurable",
) -> dict[str, Any]:
    return {
        "tables_or_resources": tables,
        "source_type": source_type,
        "observability_gate": {
            "enabled": enabled,
            "rule": rule,
            "deployment_start": "2014-02-06" if enabled else None,
            "deployment_end": None,
            "failure_state": failure_state,
        },
    }


def identity(
    classes: list[str],
    *,
    tier: str,
    keys: list[str],
    match_mode: str,
    unit: list[str],
    ingredients: list[str] | None = None,
    negative_rule: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "vocabulary": "Frozen RxNorm-referenced name whitelist",
        "vocabulary_version": "drug_class_whitelist_v1.0",
        "code_list": {
            "path": "config/drug_class_whitelist_v1.0.csv",
            "sha256": sha256_file(CODE_LIST),
            "tier": tier,
        },
        "native_keys": keys,
        "match_mode": match_mode,
        "deduplication_unit": unit,
        "revision_handling": "collapse_to_unit",
        "class_filter": classes,
        "negative_match_rule": negative_rule,
    }
    if ingredients is not None:
        value["ingredient_filter"] = ingredients
    return value


def output(profile: str) -> dict[str, Any]:
    return {
        "profile": profile,
        "aggregate_only": True,
        "allow_patient_level": False,
        "trace_level": "aggregate",
        "classifications": ["exposed", "unexposed", "unresolved", "unmeasurable"],
        "formats": ["json", "markdown", "html", "csv"],
    }


def base(operator_id: str, construct: str, target: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "operator_id": operator_id,
        "operator_version": "1.0.0",
        "clinical_construct": construct,
        "analysis_unit": "stay_id x medication class",
        "target_event": target,
        "data_model": {
            "adapter": "mimic_native",
            "model_name": "MIMIC-IV native",
            "model_version": "3.1",
        },
        "provenance": provenance(),
    }


def specifications() -> dict[str, dict[str, Any]]:
    classes, ppis = read_whitelist()
    semantics = read_semantics()
    mixed_tables = [
        "hosp/prescriptions",
        "hosp/poe",
        "hosp/emar",
        "hosp/emar_detail",
        "icu/icustays",
    ]
    order_tables = ["hosp/prescriptions", "hosp/poe", "icu/icustays"]
    admin_tables = ["hosp/emar", "hosp/emar_detail", "icu/icustays"]

    strict = base(
        "mimic.strict_same_poe",
        "six_class_order_to_documented_administration_conversion",
        "documented_administration",
    )
    strict.update(
        {
            "analysis_unit": "stay_id x drug_class x poe_id",
            "source_layer": source(
                mixed_tables,
                "mixed",
                "eMAR-observable ICU stay; linked prescription has valid same-subject/admission POE",
            ),
            "identity_rule": identity(
                classes,
                tier="strict",
                keys=["subject_id", "hadm_id", "stay_id", "poe_id", "drug_class"],
                match_mode="exact_native_key",
                unit=["stay_id", "drug_class", "poe_id"],
            ),
            "time_origin_window": window(
                origin="poe_ordertime",
                assignment="charttime",
                start=-2,
                end=None,
                censor="prescription_stop",
                rule="Administration shares ICU stay, drug class, and poe_id; charttime is >= ordertime-2h and <= min(stoptime+6h, ICU outtime)",
                after=6,
            ),
            "event_semantics_map": event_map("administration", semantics),
            "required_metadata": metadata(status="required"),
            "output_specification": output("six_class_conversion"),
        }
    )

    broad = deepcopy(strict)
    broad["operator_id"] = "mimic.broad_same_class"
    broad["clinical_construct"] = (
        "six_class_same_class_window_documented_administration_sensitivity"
    )
    broad["identity_rule"] = identity(
        classes,
        tier="mixed",
        keys=["subject_id", "hadm_id", "stay_id", "drug_class"],
        match_mode="same_class_window",
        unit=["stay_id", "drug_class", "poe_id"],
    )
    broad["time_origin_window"]["window_rule"] = (
        "Sensitivity only: administration shares ICU stay and drug class; same order-specific "
        "-2h to min(stoptime+6h, ICU outtime) window; native poe_id identity is not required"
    )

    a1_order = base("a1.vte_order", "a1_vte_prophylaxis_order_exposure", "order")
    a1_order.update(
        {
            "source_layer": source(
                order_tables, "order", "ICU stay is in the frozen eMAR-observable era"
            ),
            "identity_rule": identity(
                ["vte_prophylaxis"],
                tier="strict",
                keys=["subject_id", "hadm_id", "stay_id", "poe_id", "drug_class"],
                match_mode="exact_native_key",
                unit=["stay_id", "drug_class", "poe_id"],
                negative_rule="exclude flush/lock, dialysis, therapeutic infusion, ECMO/Impella, and line-maintenance products",
            ),
            "time_origin_window": window(
                origin="icu_intime",
                assignment="ordertime",
                start=-6,
                end=None,
                censor="icu_outtime",
                rule="Ordertime during ICU or up to 6h before ICU when prescription remains active at ICU entry; exposure at any time through ICU outtime",
                before=6,
            ),
            "event_semantics_map": event_map("order", semantics),
            "required_metadata": metadata(
                route="required",
                dose="required",
                unit="required",
                status="optional",
                constraints=["subcutaneous-compatible route", "frozen prophylactic-dose rule"],
            ),
            "output_specification": output("anchor_exposure"),
        }
    )

    a1_admin = base(
        "a1.vte_admin_route_required",
        "a1_vte_prophylaxis_administration_exposure_route_required",
        "documented_administration",
    )
    a1_admin.update(
        {
            "source_layer": source(
                admin_tables, "administration", "ICU stay is in the frozen eMAR-observable era"
            ),
            "identity_rule": identity(
                ["vte_prophylaxis"],
                tier="strict",
                keys=["subject_id", "hadm_id", "stay_id", "poe_id", "drug_class"],
                match_mode="exact_native_key",
                unit=["stay_id", "drug_class", "poe_id"],
                negative_rule="exclude flush/lock, dialysis, therapeutic infusion, ECMO/Impella, and line-maintenance products",
            ),
            "time_origin_window": window(
                origin="icu_intime",
                assignment="charttime",
                start=0,
                end=None,
                censor="icu_outtime",
                rule="Strict documented administration during ICU stay",
            ),
            "event_semantics_map": event_map("administration", semantics),
            "required_metadata": metadata(
                route="required",
                dose="optional",
                unit="optional",
                status="required",
                constraints=["subcutaneous-compatible route is required by the clinical construct"],
            ),
            "output_specification": output("anchor_exposure"),
        }
    )

    def a2_order_spec(operator_id: str, construct: str, hospital_overlap: bool) -> dict[str, Any]:
        spec = base(operator_id, construct, "order")
        if hospital_overlap:
            time_spec = window(
                origin="icu_intime",
                assignment="starttime",
                start=None,
                end=48,
                censor="hospital_discharge",
                rule="PPI prescription starttime <= ICU intime+48h, stoptime (or ICU outtime) >= ICU intime, and first POE ordertime (or starttime) <= ICU intime+48h",
            )
        else:
            time_spec = window(
                origin="icu_intime",
                assignment="ordertime",
                start=-6,
                end=48,
                censor="icu_outtime",
                rule="Frozen eligible linked order cluster with ordertime <= ICU intime+48h and prescription stoptime (or ICU outtime) >= ICU intime",
                before=6,
            )
        spec.update(
            {
                "source_layer": source(
                    order_tables, "order", "ICU stay is in the frozen eMAR-observable era"
                ),
                "identity_rule": identity(
                    ["stress_ulcer_prophylaxis"],
                    tier="strict",
                    keys=["subject_id", "hadm_id", "stay_id", "poe_id", "drug_class"],
                    match_mode="exact_native_key",
                    unit=["stay_id", "drug_class", "poe_id"],
                    ingredients=ppis,
                ),
                "time_origin_window": time_spec,
                "event_semantics_map": event_map("order", semantics),
                "required_metadata": metadata(status="optional"),
                "output_specification": output("anchor_exposure"),
            }
        )
        return spec

    a2_original = a2_order_spec(
        "a2.ppi_original_order", "a2_ppi_original_icu_window_order_exposure", False
    )
    a2_hospital = a2_order_spec(
        "a2.ppi_hospital_overlap_order", "a2_ppi_hospital_overlap_order_exposure", True
    )

    a2_admin = base(
        "a2.ppi_strict_admin",
        "a2_ppi_strict_administration_exposure",
        "documented_administration",
    )
    a2_admin.update(
        {
            "source_layer": source(
                admin_tables, "administration", "ICU stay is in the frozen eMAR-observable era"
            ),
            "identity_rule": identity(
                ["stress_ulcer_prophylaxis"],
                tier="strict",
                keys=["subject_id", "hadm_id", "stay_id", "poe_id", "drug_class"],
                match_mode="exact_native_key",
                unit=["stay_id", "drug_class", "poe_id"],
                ingredients=ppis,
            ),
            "time_origin_window": window(
                origin="icu_intime",
                assignment="charttime",
                start=0,
                end=48,
                censor="icu_outtime",
                rule="Strict PPI administration charttime between ICU intime and min(ICU outtime, ICU intime+48h)",
            ),
            "event_semantics_map": event_map("administration", semantics),
            "required_metadata": metadata(status="required"),
            "output_specification": output("anchor_exposure"),
        }
    )

    return {
        "mimic_strict_same_poe.yaml": strict,
        "mimic_broad_same_class.yaml": broad,
        "a1_vte_order.yaml": a1_order,
        "a1_vte_admin_route_required.yaml": a1_admin,
        "a2_ppi_original_order.yaml": a2_original,
        "a2_ppi_hospital_overlap_order.yaml": a2_hospital,
        "a2_ppi_strict_admin.yaml": a2_admin,
    }


def write_specs(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename, document in specifications().items():
        path = output_dir / filename
        rendered = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
        path.write_text(
            "# AUTO-GENERATED by scripts/46_generate_operator_specs.py; do not edit manually.\n"
            + rendered,
            encoding="utf-8",
            newline="\n",
        )
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    for path in write_specs(args.out.resolve()):
        print(f"WROTE {path} sha256={sha256_file(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
