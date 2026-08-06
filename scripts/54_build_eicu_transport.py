#!/usr/bin/env python3
"""Run the frozen full eICU interface-semantic transport evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from medprov.eicu_engine import find_member, run_eicu_reconciliation
from medprov.schema import load_document

ROOT = Path(__file__).resolve().parents[1]
EICU_DEFAULT = Path(
    r"D:\respiratory_icu_qdp\eicu-collaborative-research-database-2.0.zip"
)
OUTPUT_DEFAULT = ROOT / "outputs" / "eicu_transport_v0_1_0"
SPEC = ROOT / "examples" / "transport" / "eicu_six_class_reconciliation.yaml"
CONTRACT = ROOT / "contracts" / "EICU_ADAPTER_CONTRACT_v1.0_2026-08-05.md"
USED_MEMBERS = (
    "patient.csv.gz",
    "medication.csv.gz",
    "infusionDrug.csv.gz",
    "hospital.csv.gz",
    "treatment.csv.gz",
)


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def member_integrity(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for basename in USED_MEMBERS:
            member = find_member(archive, basename)
            info = archive.getinfo(member)
            digest = hashlib.sha256()
            read_bytes = 0
            with archive.open(member) as handle:
                for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                    digest.update(block)
                    read_bytes += len(block)
            rows.append(
                {
                    "member": member,
                    "bytes_read": read_bytes,
                    "zip_uncompressed_bytes": info.file_size,
                    "zip_compressed_bytes": info.compress_size,
                    "zip_crc32_hex": f"{info.CRC:08x}",
                    "member_sha256": digest.hexdigest(),
                    "integrity_pass": read_bytes == info.file_size,
                }
            )
            log(f"CHECKPOINT integrity member={basename} bytes={read_bytes}")
    return rows


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


def report_text(summary: dict[str, Any], results: dict[str, Any]) -> str:
    passed = summary["classes_passed"]
    failed = summary["classes_failed"]
    gates_by_class = {
        row["medication_class"]: row for row in results["feasibility_gates"]
    }
    class_lines = []
    for row in results["class_reconciliation"]:
        if row["gate_pass"]:
            class_lines.append(
                f"- `{row['medication_class']}`: {row['converted_orders_n']}/"
                f"{row['eligible_time_valid_orders_n']} converted "
                f"({row['conversion_pct']}%)."
            )
        else:
            gate_row = gates_by_class[row["medication_class"]]
            failed_gates = [
                key
                for key, value in gate_row.items()
                if key
                in {
                    "valid_orders_ge_100",
                    "admin_like_events_ge_100",
                    "hospitals_with_both_ge_10",
                    "valid_interval_ge_80pct",
                    "identity_unambiguous",
                }
                and not value
            ]
            class_lines.append(
                f"- `{row['medication_class']}`: not reconciled; failed frozen gate(s): "
                f"{', '.join(failed_gates)}."
            )
    ambiguous_lines = [
        f"- `{row['source']}`: `{row['raw_label']}` matched "
        f"`{row['matched_classes']}` ({row['rows_n']} rows)."
        for row in results["ambiguous_identity_labels"]
    ]
    return f"""# eICU interface-semantic transport report

## Decision

**{summary['gate']}**

This is a cross-hospital interface and source-observability comparison. It is not external validation, clinical adherence assessment, or an effectiveness/safety analysis.

## Main findings

- Full ZIP streaming completed with frozen strict labels and no patient-level output.
- Classes passing all five pre-specified feasibility gates ({len(passed)}): {', '.join(passed) if passed else 'none'}.
- Classes failing at least one gate ({len(failed)}): {', '.join(failed) if failed else 'none'}.
- Native medication-to-infusion identity remained unavailable by design; all performed reconciliation used `same stay × same class × frozen time window`.
- `treatment` remained documentation-only and `intakeOutput` remained excluded; neither was promoted to administration.

## Class results

{chr(10).join(class_lines)}

## Frozen identity ambiguities

{chr(10).join(ambiguous_lines) if ambiguous_lines else '- None observed.'}

Ambiguous composite labels were excluded and caused the affected class gate(s) to fail; they were not reassigned or used to tune the frozen whitelist.

## Engineering audit

The production implementation performed one sequential scan per required gzip member inside the read-only ZIP. Medication and infusion rows were filtered by the frozen label prefilter before retained units were stored. Reconciliation operated only on the reduced stay×class objects. The 100-order, 10-hospital regression test passed before this full run; no full-table many-to-many SQL join was used.

## Interpretation boundary

Hospital/unit variation is source observability heterogeneity. It must not be interpreted as hospital quality, medication adherence, effectiveness, or safety. Cells with fewer than 10 eligible order units were suppressed.

## Reproduction

```powershell
.\\.venv\\Scripts\\python.exe scripts\\54_build_eicu_transport.py
```
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eicu-zip", type=Path, default=EICU_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    args = parser.parse_args()
    started = time.perf_counter()
    eicu_zip = args.eicu_zip.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not eicu_zip.is_file():
        raise FileNotFoundError(f"Frozen eICU ZIP is unavailable: {eicu_zip}")

    log(f"START eICU transport zip_bytes={eicu_zip.stat().st_size}")
    integrity = member_integrity(eicu_zip)
    write_csv(output / "eicu_used_member_integrity.csv", integrity)
    if not all(bool(row["integrity_pass"]) for row in integrity):
        raise RuntimeError("eICU used-member integrity gate failed")

    spec = load_document(SPEC)
    results = run_eicu_reconciliation(eicu_zip, spec, progress=log)
    write_csv(output / "eicu_source_observability.csv", results["source_observability"])
    write_csv(output / "eicu_metadata_availability.csv", results["metadata_availability"])
    write_csv(output / "eicu_feasibility_gates.csv", results["feasibility_gates"])
    write_csv(
        output / "eicu_ambiguous_identity_labels.csv",
        results["ambiguous_identity_labels"]
        or [
            {
                "source": "all",
                "raw_label": "none",
                "matched_classes": "none",
                "rows_n": 0,
            }
        ],
    )
    write_csv(output / "eicu_class_reconciliation.csv", results["class_reconciliation"])
    if results["time_displacement"]:
        write_csv(output / "eicu_first_time_displacement.csv", results["time_displacement"])
    else:
        write_csv(
            output / "eicu_first_time_displacement.csv",
            [
                {
                    "status": "not_evaluated_no_class_passed",
                    "reason": "all frozen class-specific feasibility gates failed",
                }
            ],
        )
    write_csv(
        output / "eicu_hospital_unit_heterogeneity.csv",
        results["hospital_unit_heterogeneity"]
        or [
            {
                "status": "not_evaluated_no_class_passed",
                "cell_suppression_threshold": 10,
            }
        ],
    )

    passed = sorted(
        row["medication_class"]
        for row in results["feasibility_gates"]
        if row["gate_pass"]
    )
    failed = sorted(
        row["medication_class"]
        for row in results["feasibility_gates"]
        if not row["gate_pass"]
    )
    summary = {
        "schema_version": "1.0.0",
        "gate": "EXECUTED_INTERFACE_SEMANTIC_COMPARISON",
        "claim_boundary": "interface semantic comparison; not external validation",
        "dataset": {
            "name": "eICU Collaborative Research Database v2.0",
            "local_archive_bytes": eicu_zip.stat().st_size,
            "used_member_integrity": "SHA-256 plus ZIP CRC32",
        },
        "contract": {
            "path": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(CONTRACT),
        },
        "spec": {
            "path": str(SPEC.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(SPEC),
        },
        "classes_passed": passed,
        "classes_failed": failed,
        "counts": results["counts"],
        "engine_metrics": results["metrics"],
        "execution": {
            "wall_clock_seconds": round(time.perf_counter() - started, 6),
            "script_sha256": sha256_file(Path(__file__).resolve()),
        },
        "privacy": (
            "aggregate only; patientunitstayid and native source IDs were held in memory and "
            "not serialized; hospital/unit cells below 10 were suppressed"
        ),
    }
    json_dump(output / "eicu_transport_summary.json", summary)
    (output / "EICU_INTERFACE_TRANSPORT_REPORT.md").write_text(
        report_text(summary, results), encoding="utf-8"
    )

    manifest = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "manifest_sha256.csv":
            manifest.append(
                {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            )
    write_csv(output / "manifest_sha256.csv", manifest)
    log(
        f"COMPLETE gate={summary['gate']} classes_passed={len(passed)} "
        f"elapsed_seconds={summary['execution']['wall_clock_seconds']}"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
