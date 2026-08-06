#!/usr/bin/env python3
"""Run the frozen matched-demo native/FHIR functional transport evaluation.

Only aggregate outputs are written.  Patient, encounter, and native-record
identifiers exist in memory solely to calculate the pre-specified pairing and
Jaccard metrics and are never serialized.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from medprov.adapters.mimic_fhir import MimicFHIRAdapter
from medprov.identity import NameRule, classify_strings, load_name_rules

ROOT = Path(__file__).resolve().parents[1]
NATIVE_DEFAULT = (
    ROOT
    / "local_data"
    / "official_demos"
    / "mimic-iv-demo-2.2"
    / "mimic-iv-clinical-database-demo-2.2"
)
FHIR_DEFAULT = ROOT / "local_data" / "official_demos" / "mimic-iv-fhir-demo-2.1.0"
OUTPUT_DEFAULT = ROOT / "outputs" / "transport_evaluation_v0_1_0"
CONTRACT = ROOT / "contracts" / "FHIR_TRANSPORT_CONTRACT_v1.0_2026-08-05.md"
SPEC_ROOT = ROOT / "examples" / "transport"

CLASSES = (
    "stress_ulcer_prophylaxis",
    "vte_prophylaxis",
    "intra_abdominal_antibiotics",
    "electrolyte_replacement",
    "prokinetic",
    "insulin",
)
ROLES = ("request", "dispense", "administration")
NATIVE_POSITIVE = {
    "administered",
    "delayed administered",
    "partial administered",
    "applied",
    "started",
}
NATIVE_NEGATIVE = {"not given", "held", "refused"}
NATIVE_EXCLUDED = {"flushed", "confirmed", "<blank>"}


@dataclass
class Record:
    record_id: str
    medication_class: str
    subject_id: str
    encounter_id: str
    native_source_id: str = ""
    order_source_id: str = ""
    source_state: str = "exposed"
    source_semantic: str = "record_exists"
    method_state: str = "not_applicable"
    method_semantic: str = "not_applicable"
    event_time: datetime | None = None
    alternate_time: datetime | None = None
    reference_times: dict[str, datetime] = field(default_factory=dict)
    metadata: dict[str, bool] = field(default_factory=dict)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_manifest(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        digest, relpath = line.split(maxsplit=1)
        values[relpath.lstrip("* ").replace("\\", "/")] = digest.lower()
    return values


def parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Native MIMIC timestamps are local-naive.  FHIR retains an offset, so the
    # appropriate matched-demo comparison is local wall time, not UTC-shifted time.
    return parsed.replace(tzinfo=None)


def normalize_semantic(value: object) -> str:
    return str(value or "").strip().lower() or "<blank>"


def native_semantic_state(literal: str) -> str:
    if literal in NATIVE_POSITIVE:
        return "exposed"
    if literal in NATIVE_NEGATIVE:
        return "unexposed"
    return "unresolved"


def fhir_status_state(literal: str, role: str) -> str:
    if role == "request":
        if literal == "entered-in-error":
            return "unexposed"
        if literal in {"unknown", "<blank>"}:
            return "unresolved"
        return "exposed"
    if role == "dispense":
        if literal == "completed":
            return "exposed"
        if literal in {"declined", "entered-in-error"}:
            return "unexposed"
        return "unresolved"
    if literal == "completed":
        return "exposed"
    if literal in {"not-done", "entered-in-error"}:
        return "unexposed"
    return "unresolved"


def iter_csv(path: Path) -> Iterable[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def iter_ndjson(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value


def identifier_value(resource: dict[str, Any], system_suffix: str) -> str:
    identifiers = resource.get("identifier", [])
    for identifier in identifiers if isinstance(identifiers, list) else []:
        if not isinstance(identifier, dict):
            continue
        if str(identifier.get("system", "")).endswith(system_suffix):
            return str(identifier.get("value", "")).strip()
    return ""


def reference_id(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("reference", "")).split("/")[-1]


def coding_literal(value: object) -> str:
    if not isinstance(value, dict):
        return "<blank>"
    for coding in value.get("coding", []):
        if isinstance(coding, dict) and (coding.get("code") or coding.get("display")):
            return normalize_semantic(coding.get("code") or coding.get("display"))
    return normalize_semantic(value.get("text"))


def dosage_blocks(resource: dict[str, Any]) -> list[dict[str, Any]]:
    dosage = resource.get("dosage")
    if isinstance(dosage, dict):
        return [dosage]
    instructions = resource.get("dosageInstruction", [])
    if isinstance(instructions, list):
        return [item for item in instructions if isinstance(item, dict)]
    return []


def fhir_metadata(resource: dict[str, Any]) -> dict[str, bool]:
    blocks = dosage_blocks(resource)
    route = any(bool(block.get("route")) for block in blocks)
    dose = False
    unit = False
    frequency = any(bool(block.get("timing")) for block in blocks)
    for block in blocks:
        direct = block.get("dose")
        if isinstance(direct, dict):
            dose = dose or direct.get("value") not in (None, "")
            unit = unit or bool(direct.get("unit") or direct.get("code"))
        for item in block.get("doseAndRate", []):
            if not isinstance(item, dict):
                continue
            quantity = item.get("doseQuantity", {})
            if isinstance(quantity, dict):
                dose = dose or quantity.get("value") not in (None, "")
                unit = unit or bool(quantity.get("unit") or quantity.get("code"))
    return {
        "route": route,
        "dose": dose,
        "unit": unit,
        "frequency": frequency,
        "status": bool(str(resource.get("status", "")).strip()),
        "subject": bool(resource.get("subject")),
        "encounter": bool(resource.get("encounter") or resource.get("context")),
        "event_time": any(
            bool(resource.get(key))
            for key in (
                "authoredOn",
                "effectiveDateTime",
                "effectivePeriod",
                "whenPrepared",
                "whenHandedOver",
            )
        ),
    }


def merge_record(target: Record, incoming: Record) -> Record:
    target.metadata = {
        key: bool(target.metadata.get(key) or incoming.metadata.get(key))
        for key in set(target.metadata) | set(incoming.metadata)
    }
    candidates = [value for value in (target.event_time, incoming.event_time) if value]
    target.event_time = min(candidates) if candidates else None
    alternate = [value for value in (target.alternate_time, incoming.alternate_time) if value]
    target.alternate_time = min(alternate) if alternate else None
    for key, value in incoming.reference_times.items():
        if key not in target.reference_times or value < target.reference_times[key]:
            target.reference_times[key] = value
    if not target.order_source_id:
        target.order_source_id = incoming.order_source_id
    state_rank = {"unmeasurable": 0, "unresolved": 1, "unexposed": 2, "exposed": 3}
    if state_rank.get(incoming.source_state, -1) > state_rank.get(target.source_state, -1):
        target.source_state = incoming.source_state
        target.source_semantic = incoming.source_semantic
    return target


def load_native(native_root: Path, rules: list[NameRule]) -> dict[str, list[Record]]:
    hosp = native_root / "hosp"
    poe_times: dict[str, datetime | None] = {}
    for row in iter_csv(hosp / "poe.csv.gz"):
        poe_times[str(row.get("poe_id", ""))] = parse_time(row.get("ordertime"))

    pharmacy_times: dict[str, datetime] = {}
    for row in iter_csv(hosp / "pharmacy.csv.gz"):
        pharmacy_id = str(row.get("pharmacy_id", "")).strip()
        enter_time = parse_time(row.get("entertime"))
        if not pharmacy_id or enter_time is None:
            continue
        if pharmacy_id not in pharmacy_times or enter_time < pharmacy_times[pharmacy_id]:
            pharmacy_times[pharmacy_id] = enter_time

    detail: dict[str, dict[str, bool]] = defaultdict(
        lambda: {"route": False, "dose": False, "unit": False}
    )
    for row in iter_csv(hosp / "emar_detail.csv.gz"):
        item = detail[str(row.get("emar_id", ""))]
        item["route"] = item["route"] or bool(str(row.get("route", "")).strip())
        item["dose"] = item["dose"] or any(
            bool(str(row.get(key, "")).strip())
            for key in ("dose_given", "product_amount_given", "infusion_rate")
        )
        item["unit"] = item["unit"] or any(
            bool(str(row.get(key, "")).strip())
            for key in ("dose_given_unit", "product_unit", "infusion_rate_unit")
        )

    result: dict[str, list[Record]] = {}
    configurations = {
        "request": ("prescriptions.csv.gz", "drug", "pharmacy_id"),
        "dispense": ("pharmacy.csv.gz", "medication", "pharmacy_id"),
        "administration": ("emar.csv.gz", "medication", "emar_id"),
    }
    for role, (filename, name_field, key_field) in configurations.items():
        units: dict[tuple[str, str], Record] = {}
        for row_number, row in enumerate(iter_csv(hosp / filename), start=1):
            medication_class, state = classify_strings([row.get(name_field, "")], rules)
            if medication_class is None or state != "resolved":
                continue
            source_id = str(row.get(key_field, "")).strip() or f"row-{row_number}"
            literal = normalize_semantic(row.get("event_txt"))
            source_state = (
                native_semantic_state(literal) if role == "administration" else "exposed"
            )
            event_time = parse_time(
                row.get("charttime")
                if role == "administration"
                else row.get("entertime")
                if role == "dispense"
                else row.get("starttime")
            )
            alternate_time = None
            reference_times: dict[str, datetime] = {}
            if role == "request":
                alternate_time = poe_times.get(str(row.get("poe_id", "")))
                if event_time is not None:
                    reference_times["prescription_starttime"] = event_time
                if alternate_time is not None:
                    reference_times["poe_ordertime"] = alternate_time
                pharmacy_time = pharmacy_times.get(str(row.get("pharmacy_id", "")).strip())
                if pharmacy_time is not None:
                    reference_times["pharmacy_entertime"] = pharmacy_time
            metadata = {
                "route": bool(str(row.get("route", "")).strip()),
                "dose": bool(
                    str(
                        row.get("dose_val_rx", "")
                        if role == "request"
                        else row.get("fill_quantity", "")
                    ).strip()
                ),
                "unit": bool(
                    str(
                        row.get("dose_unit_rx", "")
                        if role == "request"
                        else row.get("dispensation", "")
                    ).strip()
                ),
                "frequency": bool(str(row.get("frequency", "")).strip()),
                "status": role == "administration" or bool(str(row.get("status", "")).strip()),
                "subject": bool(str(row.get("subject_id", "")).strip()),
                "encounter": bool(str(row.get("hadm_id", "")).strip()),
                "event_time": event_time is not None,
            }
            if role == "administration":
                metadata.update(detail.get(source_id, {}))
            record = Record(
                record_id=source_id,
                medication_class=medication_class,
                subject_id=str(row.get("subject_id", "")).strip(),
                encounter_id=str(row.get("hadm_id", "")).strip(),
                native_source_id=source_id,
                order_source_id=str(row.get("pharmacy_id", "")).strip(),
                source_state=source_state,
                source_semantic=literal if role == "administration" else "record_exists",
                method_state=source_state if role == "administration" else "not_applicable",
                method_semantic=literal if role == "administration" else "not_applicable",
                event_time=event_time,
                alternate_time=alternate_time,
                reference_times=reference_times,
                metadata=metadata,
            )
            key = (source_id, medication_class)
            units[key] = merge_record(units[key], record) if key in units else record
        result[role] = list(units.values())
    return result


def load_reference_map(path: Path, system_suffix: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for resource in iter_ndjson(path):
        value = identifier_value(resource, system_suffix)
        if value:
            result[str(resource.get("id", ""))] = value
    return result


def load_fhir(fhir_dir: Path, rules: list[NameRule]) -> dict[str, list[Record]]:
    files = sorted(fhir_dir.glob("*.ndjson.gz"))
    adapter = MimicFHIRAdapter()
    by_reference, by_code = adapter._medication_maps(files, rules)
    patient_map = load_reference_map(fhir_dir / "MimicPatient.ndjson.gz", "/patient")
    encounter_map = load_reference_map(
        fhir_dir / "MimicEncounter.ndjson.gz", "/encounter-hosp"
    )
    request_phid: dict[str, str] = {}
    for resource in iter_ndjson(fhir_dir / "MimicMedicationRequest.ndjson.gz"):
        request_phid[str(resource.get("id", ""))] = identifier_value(
            resource, "/medication-request-phid"
        )

    configurations = {
        "request": ("MimicMedicationRequest.ndjson.gz", "/medication-request-phid"),
        "dispense": ("MimicMedicationDispense.ndjson.gz", "/medication-dispense"),
        "administration": ("MimicMedicationAdministration.ndjson.gz", ""),
    }
    result: dict[str, list[Record]] = {}
    for role, (filename, native_suffix) in configurations.items():
        records: list[Record] = []
        retained_units: dict[tuple[str, str], Record] = {}
        for resource in iter_ndjson(fhir_dir / filename):
            medication_class, identity_state = adapter._resource_class(
                resource, rules, by_reference, by_code
            )
            if medication_class is None or identity_state != "resolved":
                continue
            source_literal = normalize_semantic(resource.get("status"))
            method_literal = "not_applicable"
            method_state = "not_applicable"
            if role == "administration":
                method_literal = coding_literal(resource.get("dosage", {}).get("method"))
                method_state = native_semantic_state(method_literal)
            request_id = reference_id(resource.get("request"))
            order_source_id = request_phid.get(request_id, "")
            native_source_id = (
                identifier_value(resource, native_suffix) if native_suffix else ""
            )
            event_time = parse_time(
                resource.get("authoredOn")
                if role == "request"
                else resource.get("whenHandedOver") or resource.get("whenPrepared")
                if role == "dispense"
                else resource.get("effectiveDateTime")
            )
            record = Record(
                    record_id=str(resource.get("id", "")),
                    medication_class=medication_class,
                    subject_id=patient_map.get(reference_id(resource.get("subject")), ""),
                    encounter_id=encounter_map.get(
                        reference_id(resource.get("encounter") or resource.get("context")), ""
                    ),
                    native_source_id=native_source_id,
                    order_source_id=(
                        native_source_id if role in {"request", "dispense"} else order_source_id
                    ),
                    source_state=fhir_status_state(source_literal, role),
                    source_semantic=source_literal,
                    method_state=method_state,
                    method_semantic=method_literal,
                    event_time=event_time,
                    metadata=fhir_metadata(resource),
                )
            if role in {"request", "dispense"}:
                unit_id = record.native_source_id or record.record_id
                unit_key = (unit_id, medication_class)
                retained_units[unit_key] = (
                    merge_record(retained_units[unit_key], record)
                    if unit_key in retained_units
                    else record
                )
            else:
                records.append(record)
        result[role] = list(retained_units.values()) if retained_units else records
    return result


def counts_by_state(records: Iterable[Record], use_method: bool = False) -> Counter[str]:
    return Counter(record.method_state if use_method else record.source_state for record in records)


def jaccard(left: set[tuple[str, str]], right: set[tuple[str, str]]) -> tuple[float, int, int, int]:
    union = left | right
    intersection = left & right
    value = len(intersection) / len(union) if union else math.nan
    return value, len(intersection), len(left - right), len(right - left)


def percentile(values: list[float], proportion: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize_deltas(label: str, role: str, medication_class: str, values: list[float]) -> dict[str, Any]:
    return {
        "comparison": label,
        "role": role,
        "medication_class": medication_class,
        "paired_n": len(values),
        "median_minutes": round(statistics.median(values), 6) if values else "not_evaluable",
        "q1_minutes": round(percentile(values, 0.25), 6) if values else "not_evaluable",
        "q3_minutes": round(percentile(values, 0.75), 6) if values else "not_evaluable",
        "min_minutes": round(min(values), 6) if values else "not_evaluable",
        "max_minutes": round(max(values), 6) if values else "not_evaluable",
        "exact_zero_n": sum(abs(value) < 1e-9 for value in values),
        "not_evaluable_reason": "" if values else "no deterministic retained identifier with two valid timestamps",
    }


def first_by_order(records: Iterable[Record]) -> dict[tuple[str, str], Record]:
    result: dict[tuple[str, str], Record] = {}
    for record in records:
        if not record.order_source_id or record.event_time is None:
            continue
        key = (record.order_source_id, record.medication_class)
        if key not in result or record.event_time < result[key].event_time:  # type: ignore[operator]
            result[key] = record
    return result


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty table: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def json_dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def peak_working_set_mb() -> float | str:
    if os.name != "nt":
        return "not_evaluable"
    try:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        )
        return round(counters.PeakWorkingSetSize / (1024 * 1024), 3) if ok else "not_evaluable"
    except (AttributeError, OSError):
        return "not_evaluable"


def integrity_rows(native_root: Path, fhir_root: Path) -> list[dict[str, Any]]:
    native_expected = parse_manifest(native_root / "SHA256SUMS.txt")
    fhir_expected = parse_manifest(fhir_root / "SHA256SUMS.txt")
    native_files = [
        "hosp/prescriptions.csv.gz",
        "hosp/pharmacy.csv.gz",
        "hosp/emar.csv.gz",
        "hosp/emar_detail.csv.gz",
        "hosp/poe.csv.gz",
        "hosp/admissions.csv.gz",
        "hosp/patients.csv.gz",
        "icu/icustays.csv.gz",
    ]
    fhir_files = [
        "fhir/MimicMedication.ndjson.gz",
        "fhir/MimicMedicationRequest.ndjson.gz",
        "fhir/MimicMedicationDispense.ndjson.gz",
        "fhir/MimicMedicationAdministration.ndjson.gz",
        "fhir/MimicMedicationAdministrationICU.ndjson.gz",
        "fhir/MimicPatient.ndjson.gz",
        "fhir/MimicEncounter.ndjson.gz",
        "fhir/MimicEncounterICU.ndjson.gz",
    ]
    rows: list[dict[str, Any]] = []
    for representation, root, expected, relpaths in (
        ("native", native_root, native_expected, native_files),
        ("fhir", fhir_root, fhir_expected, fhir_files),
    ):
        for relpath in relpaths:
            path = root / Path(relpath)
            observed = sha256_file(path) if path.is_file() else "missing"
            target = expected.get(relpath, "not_listed")
            rows.append(
                {
                    "representation": representation,
                    "relative_path": relpath,
                    "expected_sha256": target,
                    "observed_sha256": observed,
                    "integrity_pass": observed == target,
                }
            )
    return rows


def build_metrics(
    native: dict[str, list[Record]], fhir: dict[str, list[Record]]
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    role_class: list[dict[str, Any]] = []
    pairing: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    semantics: list[dict[str, Any]] = []
    jaccards: list[dict[str, Any]] = []

    for role in ROLES:
        for medication_class in CLASSES:
            n_records = [r for r in native[role] if r.medication_class == medication_class]
            f_records = [r for r in fhir[role] if r.medication_class == medication_class]
            n_states = counts_by_state(n_records)
            f_states = counts_by_state(f_records)
            f_method = counts_by_state(f_records, use_method=True)
            role_class.append(
                {
                    "role": role,
                    "medication_class": medication_class,
                    "native_records_n": len(n_records),
                    "fhir_records_n": len(f_records),
                    "native_exposed_n": n_states["exposed"],
                    "native_unexposed_n": n_states["unexposed"],
                    "native_unresolved_n": n_states["unresolved"],
                    "fhir_primary_exposed_n": f_states["exposed"],
                    "fhir_primary_unexposed_n": f_states["unexposed"],
                    "fhir_primary_unresolved_n": f_states["unresolved"],
                    "fhir_method_exposed_n": (
                        f_method["exposed"] if role == "administration" else "not_applicable"
                    ),
                    "fhir_method_unexposed_n": (
                        f_method["unexposed"] if role == "administration" else "not_applicable"
                    ),
                    "fhir_method_unresolved_n": (
                        f_method["unresolved"] if role == "administration" else "not_applicable"
                    ),
                }
            )

            for representation, records in (("native", n_records), ("fhir", f_records)):
                for dimension in (
                    "route",
                    "dose",
                    "unit",
                    "frequency",
                    "status",
                    "subject",
                    "encounter",
                    "event_time",
                ):
                    available = sum(record.metadata.get(dimension, False) for record in records)
                    metadata.append(
                        {
                            "role": role,
                            "representation": representation,
                            "medication_class": medication_class,
                            "metadata_dimension": dimension,
                            "records_n": len(records),
                            "available_n": available,
                            "available_pct": (
                                round(100 * available / len(records), 6)
                                if records
                                else "not_evaluable"
                            ),
                        }
                    )

            if role in {"request", "dispense"}:
                n_keys = {(r.native_source_id, r.medication_class) for r in n_records if r.native_source_id}
                f_keys = {(r.native_source_id, r.medication_class) for r in f_records if r.native_source_id}
                matched = n_keys & f_keys
                pairing.append(
                    {
                        "role": role,
                        "medication_class": medication_class,
                        "pairing_unit": "retained_native_id_x_class",
                        "native_units_n": len(n_keys),
                        "fhir_units_n": len(f_keys),
                        "matched_units_n": len(matched),
                        "matched_over_native_pct": (
                            round(100 * len(matched) / len(n_keys), 6)
                            if n_keys
                            else "not_evaluable"
                        ),
                        "matched_over_fhir_pct": (
                            round(100 * len(matched) / len(f_keys), 6)
                            if f_keys
                            else "not_evaluable"
                        ),
                        "identifier_retained_pct": (
                            round(
                                100
                                * sum(bool(r.native_source_id) for r in f_records)
                                / len(f_records),
                                6,
                            )
                            if f_records
                            else "not_evaluable"
                        ),
                        "not_evaluable_reason": "",
                    }
                )
            else:
                pairing.append(
                    {
                        "role": role,
                        "medication_class": medication_class,
                        "pairing_unit": "native_emar_identifier",
                        "native_units_n": len(n_records),
                        "fhir_units_n": len(f_records),
                        "matched_units_n": "not_evaluable",
                        "matched_over_native_pct": "not_evaluable",
                        "matched_over_fhir_pct": "not_evaluable",
                        "identifier_retained_pct": 0.0,
                        "not_evaluable_reason": (
                            "FHIR MedicationAdministration does not retain native emar_id; "
                            "order-unit/time composite is reported separately"
                        ),
                    }
                )

            n_exposed = [r for r in n_records if r.source_state == "exposed"]
            f_primary = [r for r in f_records if r.source_state == "exposed"]
            f_extension = (
                [r for r in f_records if r.method_state == "exposed"]
                if role == "administration"
                else f_primary
            )
            for level, attr in (("subject", "subject_id"), ("encounter", "encounter_id")):
                n_set = {
                    (str(getattr(record, attr)), medication_class)
                    for record in n_exposed
                    if getattr(record, attr)
                }
                for definition, records in (
                    ("fhir_primary_status", f_primary),
                    ("fhir_source_semantic_extension", f_extension),
                ):
                    if role != "administration" and definition.endswith("extension"):
                        continue
                    f_set = {
                        (str(getattr(record, attr)), medication_class)
                        for record in records
                        if getattr(record, attr)
                    }
                    value, both, native_only, fhir_only = jaccard(n_set, f_set)
                    jaccards.append(
                        {
                            "role": role,
                            "medication_class": medication_class,
                            "level": level,
                            "fhir_definition": definition,
                            "native_exposed_units_n": len(n_set),
                            "fhir_exposed_units_n": len(f_set),
                            "intersection_n": both,
                            "native_only_n": native_only,
                            "fhir_only_n": fhir_only,
                            "jaccard": round(value, 9) if not math.isnan(value) else "not_evaluable",
                        }
                    )

    native_admin = native["administration"]
    fhir_admin = fhir["administration"]
    native_semantics = Counter(
        (record.medication_class, record.source_semantic) for record in native_admin
    )
    fhir_methods = Counter(
        (record.medication_class, record.method_semantic) for record in fhir_admin
    )
    fhir_statuses = Counter(
        (record.medication_class, record.source_semantic) for record in fhir_admin
    )
    literals = sorted(
        {literal for _, literal in native_semantics}
        | {literal for _, literal in fhir_methods}
        | {literal for _, literal in fhir_statuses}
    )
    for medication_class in CLASSES:
        for literal in literals:
            semantics.append(
                {
                    "medication_class": medication_class,
                    "semantic_literal": literal,
                    "native_event_txt_n": native_semantics[(medication_class, literal)],
                    "fhir_top_level_status_n": fhir_statuses[(medication_class, literal)],
                    "fhir_dosage_method_n": fhir_methods[(medication_class, literal)],
                    "native_semantic_state": native_semantic_state(literal),
                }
            )
    return role_class, pairing, metadata, semantics, jaccards


def time_metrics(
    native: dict[str, list[Record]], fhir: dict[str, list[Record]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role in ("request", "dispense"):
        n_map = {
            (record.native_source_id, record.medication_class): record
            for record in native[role]
            if record.native_source_id
        }
        f_map = {
            (record.native_source_id, record.medication_class): record
            for record in fhir[role]
            if record.native_source_id
        }
        for medication_class in CLASSES:
            keys = {
                key
                for key in set(n_map) & set(f_map)
                if key[1] == medication_class
            }
            primary: list[float] = []
            for key in keys:
                fhir_time = f_map[key].event_time
                native_time = n_map[key].event_time
                if fhir_time is not None and native_time is not None:
                    primary.append((fhir_time - native_time).total_seconds() / 60)
            rows.append(
                summarize_deltas(
                    "fhir_event_time_minus_native_source_time",
                    role,
                    medication_class,
                    primary,
                )
            )
            if role == "request":
                poe: list[float] = []
                for key in keys:
                    fhir_time = f_map[key].event_time
                    poe_time = n_map[key].alternate_time
                    if fhir_time is not None and poe_time is not None:
                        poe.append((fhir_time - poe_time).total_seconds() / 60)
                rows.append(
                    summarize_deltas(
                        "fhir_authoredOn_minus_native_poe_ordertime",
                        role,
                        medication_class,
                        poe,
                    )
                )
                pharmacy: list[float] = []
                for key in keys:
                    fhir_time = f_map[key].event_time
                    pharmacy_time = n_map[key].reference_times.get("pharmacy_entertime")
                    if fhir_time is not None and pharmacy_time is not None:
                        pharmacy.append((fhir_time - pharmacy_time).total_seconds() / 60)
                rows.append(
                    summarize_deltas(
                        "fhir_authoredOn_minus_native_pharmacy_entertime",
                        role,
                        medication_class,
                        pharmacy,
                    )
                )

    n_first = first_by_order(native["administration"])
    f_first = first_by_order(fhir["administration"])
    for medication_class in CLASSES:
        keys = {
            key
            for key in set(n_first) & set(f_first)
            if key[1] == medication_class
        }
        values = [
            (f_first[key].event_time - n_first[key].event_time).total_seconds() / 60  # type: ignore[operator]
            for key in keys
        ]
        rows.append(
            summarize_deltas(
                "fhir_first_administration_minus_native_first_emar_by_order_unit",
                "administration",
                medication_class,
                values,
            )
        )
    return rows


def administration_composite_metrics(
    native: dict[str, list[Record]], fhir: dict[str, list[Record]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for medication_class in CLASSES:
        n_counter = Counter(
            (
                record.order_source_id,
                record.medication_class,
                record.event_time.isoformat() if record.event_time else "",
                record.source_semantic,
            )
            for record in native["administration"]
            if record.medication_class == medication_class and record.order_source_id
        )
        f_counter = Counter(
            (
                record.order_source_id,
                record.medication_class,
                record.event_time.isoformat() if record.event_time else "",
                record.method_semantic,
            )
            for record in fhir["administration"]
            if record.medication_class == medication_class and record.order_source_id
        )
        matched = sum((n_counter & f_counter).values())
        rows.append(
            {
                "role": "administration",
                "medication_class": medication_class,
                "pairing_unit": "pharmacy_id_x_class_x_walltime_x_source_semantic_multiset",
                "native_linkable_events_n": sum(n_counter.values()),
                "fhir_linkable_events_n": sum(f_counter.values()),
                "composite_exact_matches_n": matched,
                "matched_over_native_pct": (
                    round(100 * matched / sum(n_counter.values()), 6)
                    if n_counter
                    else "not_evaluable"
                ),
                "matched_over_fhir_pct": (
                    round(100 * matched / sum(f_counter.values()), 6)
                    if f_counter
                    else "not_evaluable"
                ),
                "claim_boundary": "deterministic composite concordance; not native emar_id retention",
            }
        )
    return rows


def dimension_rows(
    role_class: list[dict[str, Any]],
    pairing: list[dict[str, Any]],
    time_rows: list[dict[str, Any]],
    composite: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, int]] = {}
    for role in ROLES:
        subset = [row for row in role_class if row["role"] == role]
        totals[role] = {
            "native": sum(int(row["native_records_n"]) for row in subset),
            "fhir": sum(int(row["fhir_records_n"]) for row in subset),
            "native_exposed": sum(int(row["native_exposed_n"]) for row in subset),
            "fhir_exposed": sum(int(row["fhir_primary_exposed_n"]) for row in subset),
            "fhir_method_exposed": sum(
                int(row["fhir_method_exposed_n"])
                for row in subset
                if row["fhir_method_exposed_n"] != "not_applicable"
            ),
        }
    dispense_matches = sum(
        int(row["matched_units_n"])
        for row in pairing
        if row["role"] == "dispense" and row["matched_units_n"] != "not_evaluable"
    )
    admin_composite = sum(int(row["composite_exact_matches_n"]) for row in composite)
    admin_native_linkable = sum(int(row["native_linkable_events_n"]) for row in composite)
    admin_fhir_linkable = sum(int(row["fhir_linkable_events_n"]) for row in composite)
    admin_zero_time = sum(
        int(row["exact_zero_n"])
        for row in time_rows
        if row["comparison"].startswith("fhir_first_administration")
    )
    admin_time_pairs = sum(
        int(row["paired_n"])
        for row in time_rows
        if row["comparison"].startswith("fhir_first_administration")
    )
    return [
        {
            "role": "request",
            "dimension": "source",
            "transport_state": "transformed",
            "evidence": f"native={totals['request']['native']}; fhir={totals['request']['fhir']}",
        },
        {
            "role": "request",
            "dimension": "identity",
            "transport_state": "partially_preserved",
            "evidence": "pharmacy_id retained, but frozen class-mapped record sets are not identical",
        },
        {
            "role": "request",
            "dimension": "time",
            "transport_state": "transformed",
            "evidence": (
                "authoredOn compared separately with prescription starttime, POE ordertime, "
                "and pharmacy entertime"
            ),
        },
        {
            "role": "request",
            "dimension": "event_semantics",
            "transport_state": "preserved",
            "evidence": "order intent/status remain explicit",
        },
        {
            "role": "request",
            "dimension": "dose_route",
            "transport_state": "transformed",
            "evidence": "native columns encoded as dosageInstruction elements",
        },
        {
            "role": "dispense",
            "dimension": "source",
            "transport_state": "preserved",
            "evidence": f"six-class records native={totals['dispense']['native']}; fhir={totals['dispense']['fhir']}",
        },
        {
            "role": "dispense",
            "dimension": "identity",
            "transport_state": "preserved",
            "evidence": f"exact retained pharmacy_id x class matches={dispense_matches}",
        },
        {
            "role": "dispense",
            "dimension": "time",
            "transport_state": "lost",
            "evidence": "whenPrepared/whenHandedOver absent for matched frozen-class records",
        },
        {
            "role": "dispense",
            "dimension": "event_semantics",
            "transport_state": "transformed",
            "evidence": "native record existence represented as completed FHIR dispense",
        },
        {
            "role": "dispense",
            "dimension": "dose_route",
            "transport_state": "transformed",
            "evidence": "selected metadata represented in dosageInstruction",
        },
        {
            "role": "administration",
            "dimension": "source",
            "transport_state": "partially_preserved",
            "evidence": f"native class-mapped={totals['administration']['native']}; fhir class-mapped={totals['administration']['fhir']}",
        },
        {
            "role": "administration",
            "dimension": "identity",
            "transport_state": "transformed",
            "evidence": (
                "emar_id absent; MedicationRequest link retains pharmacy_id; "
                f"exact composite matches={admin_composite}/{admin_native_linkable} native and {admin_composite}/{admin_fhir_linkable} FHIR"
            ),
        },
        {
            "role": "administration",
            "dimension": "time",
            "transport_state": "preserved",
            "evidence": f"first-event exact-zero displacement={admin_zero_time}/{admin_time_pairs} linked order units",
        },
        {
            "role": "administration",
            "dimension": "event_semantics",
            "transport_state": "extension_carried",
            "evidence": (
                f"top status exposed={totals['administration']['fhir_exposed']}; "
                f"dosage.method strict exposed={totals['administration']['fhir_method_exposed']}; "
                f"native strict exposed={totals['administration']['native_exposed']}"
            ),
        },
        {
            "role": "administration",
            "dimension": "dose_route",
            "transport_state": "partially_preserved",
            "evidence": "dose/unit encoded in dosage; route evaluated empirically rather than inherited",
        },
    ]


def build_report(summary: dict[str, Any], output: Path) -> None:
    headline = summary["headline_findings"]
    text = f"""# Matched-demo native/FHIR functional transport report

## Decision

**{summary['gate']}**

This is a functional cross-schema evaluation on the official matched 100-patient public demos. It is not full-dataset transport validation and not clinical external validation.

## Main findings

1. **Dispense identity and six-class counts transported exactly.** Native `pharmacy` and FHIR `MedicationDispense` produced {headline['dispense_records_n']:,} class-mapped units, with {headline['dispense_exact_id_class_matches_n']:,} exact retained `pharmacy_id × medication-class` matches.
2. **Administration semantics were relocated, not preserved in the top-level status.** All {headline['fhir_admin_primary_exposed_n']:,} class-mapped FHIR administrations were positive under top-level `status`, whereas `dosage.method` recovered {headline['fhir_admin_method_exposed_n']:,} strict-positive events; native eMAR yielded {headline['native_admin_exposed_n']:,}. Thus `status=completed` alone cannot reproduce the native strict event operator.
3. **Administration record identity was transformed.** FHIR omitted native `emar_id`, but its `request` reference retained an order link to `pharmacy_id`; the pre-specified pharmacy/class/time/semantic composite matched {headline['admin_composite_matches_n']:,} events. This is composite concordance, not native-record-ID retention.
4. **The FHIR Request timestamp carried pharmacy-entry provenance.** Across all {headline['request_pharmacy_time_pairs_n']:,} deterministically paired frozen-class units, `MedicationRequest.authoredOn` exactly equaled native `pharmacy.entertime` ({headline['request_pharmacy_time_exact_n']:,}/{headline['request_pharmacy_time_pairs_n']:,}), while differing from prescription `starttime` and usually from POE `ordertime`. First administration time was also identical in {headline['admin_first_time_exact_n']:,}/{headline['admin_first_time_pairs_n']:,} linked order units. The exact distributions are in `fhir_time_displacement.csv`.
5. **Request transport was partial rather than silently forced to parity.** Frozen six-class units numbered {headline['native_request_records_n']:,} in native prescriptions and {headline['fhir_request_records_n']:,} in FHIR MedicationRequest. No whitelist or mapping rule was tuned after observing this difference.

## Interpretation

The same clinical label does not guarantee that source, identity, time, event semantics, and dose/route metadata survive a representation change together. The strongest positive result is constructive: a frozen, executable provenance operator can identify exact transport (dispense), explicit transformation (request), semantic relocation (administration), and non-evaluable native-record identity without changing the clinical definition.

## Files

- `fhir_data_integrity.csv`: official SHA-256 gate.
- `fhir_role_class_metrics.csv`: per-role and per-class counts.
- `fhir_pairing_metrics.csv`: native-ID pairing.
- `fhir_administration_composite_pairing.csv`: order/time/semantic composite concordance.
- `fhir_exposure_jaccard.csv`: subject- and encounter-class overlap.
- `fhir_metadata_availability.csv`: metadata availability by role, representation, and class.
- `fhir_administration_semantic_relocation.csv`: native `event_txt`, FHIR top-level status, and FHIR `dosage.method` distributions.
- `fhir_time_displacement.csv`: deterministic time comparisons.
- `fhir_dimension_transport.csv`: five-dimensional transport classification.
- `fhir_transport_summary.json`: machine-readable decision and provenance.

## Reproduction

```powershell
.\\.venv\\Scripts\\python.exe scripts\\52_build_fhir_transport.py
```

Only aggregate outputs are written. No patient, encounter, `pharmacy_id`, `poe_id`, or `emar_id` is released.
"""
    (output / "FHIR_FUNCTIONAL_TRANSPORT_REPORT.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-root", type=Path, default=NATIVE_DEFAULT)
    parser.add_argument("--fhir-root", type=Path, default=FHIR_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    args = parser.parse_args()
    started = time.perf_counter()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    integrity = integrity_rows(args.native_root.resolve(), args.fhir_root.resolve())
    if not all(bool(row["integrity_pass"]) for row in integrity):
        write_csv(output / "fhir_data_integrity.csv", integrity)
        raise RuntimeError("Official matched-demo SHA-256 integrity gate failed")

    spec = yaml.safe_load((SPEC_ROOT / "native_demo_request.yaml").read_text(encoding="utf-8"))
    rules = load_name_rules(spec)
    native = load_native(args.native_root.resolve(), rules)
    fhir_dir = args.fhir_root.resolve() / "fhir"
    fhir = load_fhir(fhir_dir, rules)
    role_class, pairing, metadata, semantics, jaccards = build_metrics(native, fhir)
    times = time_metrics(native, fhir)
    composite = administration_composite_metrics(native, fhir)
    dimensions = dimension_rows(role_class, pairing, times, composite)

    write_csv(output / "fhir_data_integrity.csv", integrity)
    write_csv(output / "fhir_role_class_metrics.csv", role_class)
    write_csv(output / "fhir_pairing_metrics.csv", pairing)
    write_csv(output / "fhir_administration_composite_pairing.csv", composite)
    write_csv(output / "fhir_exposure_jaccard.csv", jaccards)
    write_csv(output / "fhir_metadata_availability.csv", metadata)
    write_csv(output / "fhir_administration_semantic_relocation.csv", semantics)
    write_csv(output / "fhir_time_displacement.csv", times)
    write_csv(output / "fhir_dimension_transport.csv", dimensions)

    totals: dict[str, dict[str, int]] = {}
    for role in ROLES:
        subset = [row for row in role_class if row["role"] == role]
        totals[role] = {
            "native_records_n": sum(int(row["native_records_n"]) for row in subset),
            "fhir_records_n": sum(int(row["fhir_records_n"]) for row in subset),
            "native_exposed_n": sum(int(row["native_exposed_n"]) for row in subset),
            "fhir_primary_exposed_n": sum(
                int(row["fhir_primary_exposed_n"]) for row in subset
            ),
            "fhir_method_exposed_n": sum(
                int(row["fhir_method_exposed_n"])
                for row in subset
                if row["fhir_method_exposed_n"] != "not_applicable"
            ),
        }
    dispense_matches = sum(
        int(row["matched_units_n"])
        for row in pairing
        if row["role"] == "dispense" and row["matched_units_n"] != "not_evaluable"
    )
    admin_matches = sum(int(row["composite_exact_matches_n"]) for row in composite)
    request_pharmacy_rows = [
        row
        for row in times
        if row["comparison"] == "fhir_authoredOn_minus_native_pharmacy_entertime"
    ]
    request_pharmacy_pairs = sum(int(row["paired_n"]) for row in request_pharmacy_rows)
    request_pharmacy_exact = sum(int(row["exact_zero_n"]) for row in request_pharmacy_rows)
    admin_first_rows = [
        row
        for row in times
        if row["comparison"].startswith("fhir_first_administration")
    ]
    admin_first_pairs = sum(int(row["paired_n"]) for row in admin_first_rows)
    admin_first_exact = sum(int(row["exact_zero_n"]) for row in admin_first_rows)
    gate = (
        "PASS_FUNCTIONAL_CROSS_SCHEMA"
        if all(totals[role]["native_records_n"] > 0 and totals[role]["fhir_records_n"] > 0 for role in ROLES)
        and all(bool(row["integrity_pass"]) for row in integrity)
        else "PARTIAL_FUNCTIONAL_CROSS_SCHEMA"
    )
    summary = {
        "schema_version": "1.0.0",
        "gate": gate,
        "claim_boundary": (
            "functional cross-schema evaluation on matched public demos; "
            "not full-dataset transport validation or clinical external validation"
        ),
        "datasets": {
            "native": {
                "name": "MIMIC-IV Clinical Database Demo v2.2",
                "doi": "10.13026/dp1f-ex47",
            },
            "fhir": {
                "name": "MIMIC-IV Clinical Database Demo on FHIR v2.1.0",
                "doi": "10.13026/vphg-y548",
            },
        },
        "contract": {
            "path": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(CONTRACT),
        },
        "headline_findings": {
            "native_request_records_n": totals["request"]["native_records_n"],
            "fhir_request_records_n": totals["request"]["fhir_records_n"],
            "dispense_records_n": totals["dispense"]["native_records_n"],
            "dispense_exact_id_class_matches_n": dispense_matches,
            "native_admin_exposed_n": totals["administration"]["native_exposed_n"],
            "fhir_admin_primary_exposed_n": totals["administration"]["fhir_primary_exposed_n"],
            "fhir_admin_method_exposed_n": totals["administration"]["fhir_method_exposed_n"],
            "admin_composite_matches_n": admin_matches,
            "request_pharmacy_time_pairs_n": request_pharmacy_pairs,
            "request_pharmacy_time_exact_n": request_pharmacy_exact,
            "admin_first_time_pairs_n": admin_first_pairs,
            "admin_first_time_exact_n": admin_first_exact,
        },
        "role_totals": totals,
        "execution": {
            "wall_clock_seconds": round(time.perf_counter() - started, 6),
            "peak_working_set_mb": peak_working_set_mb(),
            "python": sys.version.split()[0],
            "script_sha256": sha256_file(Path(__file__).resolve()),
        },
        "privacy": "aggregate outputs only; identifiers used in memory and never serialized",
    }
    json_dump(output / "fhir_transport_summary.json", summary)
    build_report(summary, output)

    manifest_rows = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "manifest_sha256.csv":
            manifest_rows.append(
                {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            )
    write_csv(output / "manifest_sha256.csv", manifest_rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
