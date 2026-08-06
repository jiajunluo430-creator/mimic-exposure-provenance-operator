#!/usr/bin/env python3
"""Build the frozen OMOP capability, semantic-loss, and comparator evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from medprov.adapters import get_adapter
from medprov.identity import classify_strings, load_name_rules
from medprov.schema import load_document

ROOT = Path(__file__).resolve().parents[1]
OMOP_RELEASE_DEFAULT = (
    ROOT
    / "local_data"
    / "official_demos"
    / "mimic-iv-demo-omop-0.9"
    / "mimic-iv-demo-data-in-the-omop-common-data-model-0.9"
)
OUTPUT_DEFAULT = ROOT / "outputs" / "omop_evaluation_v0_1_0"
CONTRACT = ROOT / "contracts" / "OMOP_CAPABILITY_CONTRACT_v1.0_2026-08-05.md"
DOC_SPEC = ROOT / "examples" / "transport" / "omop_demo_ppi.yaml"
STRICT_SPEC = ROOT / "examples" / "transport" / "omop_synthetic_ppi_administration.yaml"
ALL_CLASS_SPEC = ROOT / "examples" / "transport" / "native_demo_request.yaml"
ATLAS_JSON = ROOT / "examples" / "omop" / "atlas_style_ppi_cohort.json"
EXTENSION_JSON = ROOT / "examples" / "omop" / "medprov_provenance_extension.json"
FIXTURE_WITH = ROOT / "tests" / "fixtures" / "omop" / "drug_exposure_with_extension.csv"
FIXTURE_WITHOUT = ROOT / "tests" / "fixtures" / "omop" / "drug_exposure_without_extension.csv"

CLASSES = (
    "stress_ulcer_prophylaxis",
    "vte_prophylaxis",
    "intra_abdominal_antibiotics",
    "electrolyte_replacement",
    "prokinetic",
    "insulin",
)
FROZEN_FIELDS = (
    "drug_exposure_id",
    "person_id",
    "drug_concept_id",
    "drug_exposure_start_datetime",
    "drug_exposure_end_datetime",
    "drug_type_concept_id",
    "route_concept_id",
    "route_source_value",
    "quantity",
    "dose_unit_source_value",
    "sig",
    "provider_id",
    "visit_occurrence_id",
    "visit_detail_id",
    "drug_source_value",
    "drug_source_concept_id",
)
PROVENANCE_EXTENSION_FIELDS = (
    "medprov_event_state",
    "medprov_source_role",
    "medprov_native_record_id",
    "medprov_native_order_id",
    "medprov_not_given_reason",
    "medprov_revision_chain",
)


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


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path.name}")
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


def concept_names(path: Path) -> dict[str, str]:
    return {
        str(row.get("concept_id", "")): str(row.get("concept_name", ""))
        for row in read_csv(path)
        if str(row.get("concept_id", "")).strip()
    }


def integrity_rows(release_root: Path) -> list[dict[str, Any]]:
    manifest = parse_manifest(release_root / "SHA256SUMS.txt")
    rows: list[dict[str, Any]] = []
    for relpath in (
        "1_omop_data_csv/drug_exposure.csv",
        "1_omop_data_csv/2b_concept.csv",
        "1_omop_data_csv/cdm_source.csv",
    ):
        path = release_root / Path(relpath)
        expected = manifest.get(relpath, "not_listed")
        observed = sha256_file(path) if path.is_file() else "missing"
        rows.append(
            {
                "relative_path": relpath,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "integrity_pass": observed == expected,
            }
        )
    return rows


def field_and_type_audit(
    drug_path: Path, names: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, set[str]]:
    rows = list(read_csv(drug_path))
    total = len(rows)
    fields = set(rows[0]) if rows else set()
    completeness: list[dict[str, Any]] = []
    for field in (*FROZEN_FIELDS, *PROVENANCE_EXTENSION_FIELDS):
        nonmissing = sum(bool(str(row.get(field, "")).strip()) for row in rows)
        completeness.append(
            {
                "field": field,
                "field_group": (
                    "standard_or_observed_omop"
                    if field in FROZEN_FIELDS
                    else "medprov_provenance_extension"
                ),
                "column_present": field in fields,
                "rows_n": total,
                "nonmissing_n": nonmissing,
                "nonmissing_pct": round(100 * nonmissing / total, 6) if total else math.nan,
            }
        )
    types = Counter(str(row.get("drug_type_concept_id", "")) for row in rows)
    type_rows = [
        {
            "drug_type_concept_id": concept_id,
            "concept_name_if_in_local_subset": names.get(concept_id, "not_in_subset"),
            "rows_n": count,
            "rows_pct": round(100 * count / total, 6) if total else math.nan,
            "source_role_interpretation": (
                "not administration-specific; official demo derives DRUG_EXPOSURE from "
                "prescriptions/pharmacy"
            ),
        }
        for concept_id, count in sorted(types.items())
    ]
    return completeness, type_rows, total, fields


def six_class_audit(
    drug_path: Path, names: dict[str, str]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    all_spec = load_document(ALL_CLASS_SPEC)
    rules = load_name_rules(all_spec)
    row_counts: Counter[str] = Counter()
    unit_sets: dict[str, set[tuple[str, str]]] = defaultdict(set)
    standard_nonzero: Counter[str] = Counter()
    source_concept_nonzero: Counter[str] = Counter()
    route_nonmissing: Counter[str] = Counter()
    quantity_nonmissing: Counter[str] = Counter()
    time_nonmissing: Counter[str] = Counter()
    identity_states: Counter[str] = Counter()
    for row in read_csv(drug_path):
        medication_class, identity_state = classify_strings(
            [
                row.get("drug_source_value", ""),
                names.get(str(row.get("drug_concept_id", "")), ""),
                names.get(str(row.get("drug_source_concept_id", "")), ""),
            ],
            rules,
        )
        identity_states[identity_state] += 1
        if medication_class is None:
            continue
        row_counts[medication_class] += 1
        person = str(row.get("person_id", "")).strip()
        visit = str(row.get("visit_occurrence_id", "")).strip()
        if person and visit:
            unit_sets[medication_class].add((person, visit))
        standard_nonzero[medication_class] += str(row.get("drug_concept_id", "")).strip() not in {
            "",
            "0",
        }
        source_concept_nonzero[medication_class] += str(
            row.get("drug_source_concept_id", "")
        ).strip() not in {"", "0"}
        route_nonmissing[medication_class] += bool(
            str(row.get("route_source_value", "")).strip()
            or str(row.get("route_concept_id", "")).strip() not in {"", "0"}
        )
        quantity_nonmissing[medication_class] += bool(str(row.get("quantity", "")).strip())
        time_nonmissing[medication_class] += bool(
            str(row.get("drug_exposure_start_datetime", "")).strip()
        )
    rows = []
    for medication_class in CLASSES:
        n = row_counts[medication_class]
        rows.append(
            {
                "medication_class": medication_class,
                "matched_rows_n": n,
                "person_visit_class_units_n": len(unit_sets[medication_class]),
                "standard_drug_concept_nonzero_n": standard_nonzero[medication_class],
                "source_concept_nonzero_n": source_concept_nonzero[medication_class],
                "route_available_n": route_nonmissing[medication_class],
                "quantity_available_n": quantity_nonmissing[medication_class],
                "start_datetime_available_n": time_nonmissing[medication_class],
                "literal_event_state_available_n": 0,
                "strict_administration_measurability": (
                    "unmeasurable_event_semantics" if n else "not_evaluable_no_class_rows"
                ),
            }
        )
    return rows, dict(identity_states)


def atlas_record_existence(fixture: Path, expression: Path) -> dict[str, Any]:
    document = json.loads(expression.read_text(encoding="utf-8"))
    concepts = {
        str(item["concept"]["CONCEPT_ID"])
        for concept_set in document["ConceptSets"]
        for item in concept_set["expression"]["items"]
    }
    matched_rows = 0
    units: set[tuple[str, str]] = set()
    for row in read_csv(fixture):
        if str(row.get("drug_concept_id", "")) not in concepts:
            continue
        matched_rows += 1
        units.add((str(row.get("person_id", "")), str(row.get("visit_occurrence_id", ""))))
    return {
        "operator": "OMOP/ATLAS-style DRUG_EXPOSURE record existence",
        "matched_source_rows": matched_rows,
        "analysis_units": len(units),
        "exposed": len(units),
        "unexposed": 0,
        "unresolved": 0,
        "unmeasurable": 0,
        "event_semantics_represented": False,
    }


def capability_rows(total: int, fields: set[str]) -> list[dict[str, Any]]:
    del total
    return [
        {
            "provenance_element": "drug record existence",
            "omop_state": "native",
            "evidence": "DRUG_EXPOSURE row and drug_exposure_id",
        },
        {
            "provenance_element": "standard and source drug identity",
            "omop_state": "native",
            "evidence": "drug_concept_id, drug_source_concept_id, drug_source_value",
        },
        {
            "provenance_element": "source role",
            "omop_state": "implementation_dependent",
            "evidence": "drug_type_concept_id present, but this demo merges prescription/pharmacy inputs",
        },
        {
            "provenance_element": "literal administration/non-administration state",
            "omop_state": "extension_required",
            "evidence": (
                "medprov_event_state present" if "medprov_event_state" in fields else "field absent"
            ),
        },
        {
            "provenance_element": "not-given reason",
            "omop_state": "extension_required",
            "evidence": "no standard field in observed DRUG_EXPOSURE schema",
        },
        {
            "provenance_element": "native order identifier",
            "omop_state": "extension_required",
            "evidence": "no native pharmacy_id/poe_id field",
        },
        {
            "provenance_element": "native record identifier",
            "omop_state": "lost",
            "evidence": "drug_exposure_id is an OMOP record ID, not native emar_id",
        },
        {
            "provenance_element": "revision chain",
            "omop_state": "extension_required",
            "evidence": "no standard discontinue/revision-chain field",
        },
        {
            "provenance_element": "start/end time",
            "omop_state": "native",
            "evidence": "drug_exposure_start_datetime and drug_exposure_end_datetime",
        },
        {
            "provenance_element": "route/dose/unit",
            "omop_state": "partially_native",
            "evidence": "route, quantity, and source-unit fields present; semantic completeness audited",
        },
    ]


def report_text(summary: dict[str, Any]) -> str:
    h = summary["headline_findings"]
    return f"""# OMOP capability and semantic-loss report

## Decisions

- Synthetic adapter gate: **{summary['synthetic_gate']}**
- Real demo gate: **{summary['real_demo_gate']}**

This is an adapter smoke test and semantic-loss demonstration. It is not OMOP validation, external validation, or a treatment-effect analysis.

## Main findings

1. The official 100-patient OMOP demo contained {h['drug_exposure_rows_n']:,} `DRUG_EXPOSURE` rows. The frozen PPI operator matched {h['ppi_source_rows_n']:,} rows and collapsed them to {h['ppi_person_visit_units_n']:,} person×visit×class units.
2. Record-existence exposure was executable: all {h['ppi_person_visit_units_n']:,} PPI units were classified as documented drug exposure.
3. Strict documented administration was structurally unmeasurable: `medprov_event_state` was present in 0 rows, so all {h['real_strict_admin_unmeasurable_n']:,} PPI units became `unmeasurable`, not unexposed.
4. On the same synthetic fixture, the ATLAS-style record-existence operator classified {h['synthetic_atlas_exposed_n']} units as exposed. The provenance extension separated them into {h['synthetic_medprov_exposed_n']} exposed, {h['synthetic_medprov_unexposed_n']} unexposed, {h['synthetic_medprov_unresolved_n']} unresolved, and {h['synthetic_medprov_unmeasurable_n']} unmeasurable. Removing the extension made all {h['synthetic_ablation_unmeasurable_n']} units unmeasurable.
5. This demonstrates complementarity rather than replacement: OMOP/ATLAS expresses reusable drug-record cohorts; medprov makes source role and event semantics executable and auditable when those distinctions matter.

## Official source boundary

The evaluated v0.9 demo documents that `DRUG_EXPOSURE` is built from `prescriptions` and `pharmacy`; it does not add `emar`/`emar_detail` medication detail and does not incorporate ICU `inputevents`. A `DRUG_EXPOSURE` row therefore cannot be relabeled as documented administration without additional provenance.

## Reproduction

```powershell
.\\.venv\\Scripts\\python.exe scripts\\53_build_omop_evaluation.py
```

Only aggregate public-demo and fully synthetic results are released.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--omop-release-root", type=Path, default=OMOP_RELEASE_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    args = parser.parse_args()
    started = time.perf_counter()
    release_root = args.omop_release_root.resolve()
    data_root = release_root / "1_omop_data_csv"
    drug_path = data_root / "drug_exposure.csv"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    integrity = integrity_rows(release_root)
    write_csv(output / "omop_data_integrity.csv", integrity)
    if not all(bool(row["integrity_pass"]) for row in integrity):
        raise RuntimeError("Official OMOP demo SHA-256 integrity gate failed")

    names = concept_names(data_root / "2b_concept.csv")
    completeness, drug_types, total_rows, observed_fields = field_and_type_audit(
        drug_path, names
    )
    six_class, identity_states = six_class_audit(drug_path, names)

    adapter = get_adapter("omop")
    documentation_spec = load_document(DOC_SPEC)
    strict_spec = load_document(STRICT_SPEC)
    real_documentation = adapter.execute(documentation_spec, data_root).to_dict()
    real_strict = adapter.execute(strict_spec, drug_path).to_dict()
    synthetic_with = adapter.execute(strict_spec, FIXTURE_WITH).to_dict()
    synthetic_without = adapter.execute(strict_spec, FIXTURE_WITHOUT).to_dict()
    atlas = atlas_record_existence(FIXTURE_WITH, ATLAS_JSON)

    comparator_rows = []
    for label, result in (
        ("atlas_style_record_existence", atlas),
        ("medprov_with_provenance_extension", synthetic_with["counts"]),
        ("medprov_without_provenance_extension", synthetic_without["counts"]),
    ):
        comparator_rows.append(
            {
                "operator": label,
                "analysis_units": result["analysis_units"],
                "exposed": result["exposed"],
                "unexposed": result["unexposed"],
                "unresolved": result["unresolved"],
                "unmeasurable": result["unmeasurable"],
                "interpretation": (
                    "drug record exists"
                    if label.startswith("atlas")
                    else "strict source-event semantics"
                ),
            }
        )

    write_csv(output / "omop_field_completeness.csv", completeness)
    write_csv(output / "omop_drug_type_distribution.csv", drug_types)
    write_csv(output / "omop_six_class_observability.csv", six_class)
    write_csv(output / "omop_synthetic_extension_ablation.csv", comparator_rows)
    write_csv(output / "omop_provenance_capability.csv", capability_rows(total_rows, observed_fields))
    json_dump(output / "omop_real_documentation_execution.json", real_documentation)
    json_dump(output / "omop_real_strict_administration_execution.json", real_strict)
    json_dump(output / "omop_synthetic_with_extension.json", synthetic_with)
    json_dump(output / "omop_synthetic_without_extension.json", synthetic_without)
    json_dump(output / "omop_atlas_style_execution.json", atlas)

    headline = {
        "drug_exposure_rows_n": total_rows,
        "ppi_source_rows_n": int(real_documentation["metrics"]["matched_source_rows"]),
        "ppi_person_visit_units_n": int(real_documentation["counts"]["analysis_units"]),
        "real_strict_admin_unmeasurable_n": int(real_strict["counts"]["unmeasurable"]),
        "synthetic_atlas_exposed_n": int(atlas["exposed"]),
        "synthetic_medprov_exposed_n": int(synthetic_with["counts"]["exposed"]),
        "synthetic_medprov_unexposed_n": int(synthetic_with["counts"]["unexposed"]),
        "synthetic_medprov_unresolved_n": int(synthetic_with["counts"]["unresolved"]),
        "synthetic_medprov_unmeasurable_n": int(synthetic_with["counts"]["unmeasurable"]),
        "synthetic_ablation_unmeasurable_n": int(
            synthetic_without["counts"]["unmeasurable"]
        ),
    }
    synthetic_gate = (
        "PASS_DETERMINISTIC_SEMANTIC_ABLATION"
        if synthetic_with["counts"]
        == {
            "analysis_units": 4,
            "exposed": 1,
            "unexposed": 1,
            "unresolved": 1,
            "unmeasurable": 1,
        }
        and synthetic_without["counts"]["unmeasurable"] == 4
        else "FAIL_SYNTHETIC_ADAPTER"
    )
    real_gate = (
        "EXECUTED_CAPABILITY_SMOKE_TEST"
        if real_documentation["status"] == "executed" and total_rows > 0
        else "NOT_EXECUTED_DATA_UNAVAILABLE"
    )
    summary = {
        "schema_version": "1.0.0",
        "synthetic_gate": synthetic_gate,
        "real_demo_gate": real_gate,
        "claim_boundary": "OMOP capability and semantic-loss evaluation; not validation",
        "dataset": {
            "name": "MIMIC-IV demo data in OMOP CDM v0.9",
            "doi": "10.13026/p1f5-7x35",
        },
        "contract": {
            "path": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(CONTRACT),
        },
        "inputs": {
            "atlas_style_expression_sha256": sha256_file(ATLAS_JSON),
            "provenance_extension_sha256": sha256_file(EXTENSION_JSON),
            "strict_operator_sha256": sha256_file(STRICT_SPEC),
            "synthetic_fixture_with_extension_sha256": sha256_file(FIXTURE_WITH),
            "synthetic_fixture_without_extension_sha256": sha256_file(FIXTURE_WITHOUT),
        },
        "headline_findings": headline,
        "six_class_identity_states": identity_states,
        "execution": {
            "wall_clock_seconds": round(time.perf_counter() - started, 6),
            "script_sha256": sha256_file(Path(__file__).resolve()),
        },
    }
    json_dump(output / "omop_evaluation_summary.json", summary)
    (output / "OMOP_CAPABILITY_REPORT.md").write_text(report_text(summary), encoding="utf-8")

    manifest = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "manifest_sha256.csv":
            manifest.append(
                {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            )
    write_csv(output / "manifest_sha256.csv", manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
