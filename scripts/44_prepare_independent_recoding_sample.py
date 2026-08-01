#!/usr/bin/env python3
"""Create the frozen blank 20% independent-recoding packet.

This script samples studies only. It never fills second-coder fields and never
computes inter-rater agreement.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import random
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs" / "jamia_residual_provenance_v1_0"
TABLES = OUTPUT_ROOT / "tables"
SOURCE = TABLES / "published_operator_blinded_recode_worksheet.csv"
OUTPUT = TABLES / "published_operator_independent_recode_20pct_packet.csv"
MANIFEST = OUTPUT_ROOT / "manifests" / "44_independent_recode_packet_manifest.json"
CHECKPOINT = TABLES / "published_operator_independent_recode_20pct_checkpoint.csv"
SESSION = OUTPUT_ROOT / "logs" / "44_independent_recode_packet_sessionInfo.txt"
CONTRACT = (
    ROOT
    / "contracts"
    / "jamia_independent_recoding_packet_addendum_v1.0_2026-08-01.md"
)
SEED = 20260801
SAMPLE_N = 8

IDENTITY_FIELDS = [
    "sample_order",
    "random_rank",
    "pmid",
    "pmcid",
    "doi",
    "publication_year",
    "title",
    "supplement_status",
    "article_specific_repo_status",
    "article_specific_repository_urls",
]
CODING_FIELDS = [
    "coder_id",
    "review_date",
    "main_text_reviewed",
    "supplement_reviewed",
    "linked_repo_reviewed",
    "source_layer",
    "named_native_table_reported",
    "database_identity_rule_reported",
    "time_origin_and_window_reported",
    "event_semantics_reported",
    "dose_or_route_reported",
    "evidence_location",
    "coder_notes",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not SOURCE.exists() or not CONTRACT.exists():
        raise FileNotFoundError("Frozen source worksheet or addendum is missing")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    SESSION.parent.mkdir(parents=True, exist_ok=True)
    fields, rows = read_rows(SOURCE)
    if len(rows) != 40:
        raise RuntimeError(f"Expected 40 source studies; observed {len(rows)}")
    required = set(IDENTITY_FIELDS + CODING_FIELDS)
    if not required.issubset(fields):
        raise RuntimeError(f"Missing worksheet fields: {sorted(required - set(fields))}")
    if any((row.get(field) or "").strip() for row in rows for field in CODING_FIELDS):
        raise RuntimeError("Source worksheet contains completed coding fields")

    chosen = random.Random(SEED).sample(rows, SAMPLE_N)
    chosen.sort(key=lambda row: int(row["sample_order"]))
    output_rows = [
        {field: (row[field] if field in IDENTITY_FIELDS else "") for field in fields}
        for row in chosen
    ]
    write_rows(OUTPUT, fields, output_rows)

    checkpoint_rows = [
        {"checkpoint": "source frame", "rows_n": len(rows), "status": "PASS"},
        {"checkpoint": "sample without replacement", "rows_n": len(output_rows), "status": "PASS"},
        {
            "checkpoint": "coding fields blank",
            "rows_n": sum(
                1
                for row in output_rows
                if not any((row.get(field) or "").strip() for field in CODING_FIELDS)
            ),
            "status": "PASS",
        },
    ]
    write_rows(CHECKPOINT, ["checkpoint", "rows_n", "status"], checkpoint_rows)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "script": str(Path(__file__).resolve()),
        "source": str(SOURCE),
        "source_sha256": sha256(SOURCE),
        "contract": str(CONTRACT),
        "contract_sha256": sha256(CONTRACT),
        "sampling_frame_n": len(rows),
        "sample_n": SAMPLE_N,
        "seed": SEED,
        "selected_sample_orders": [int(row["sample_order"]) for row in chosen],
        "selected_pmids": [row["pmid"] for row in chosen],
        "second_coder_completed": False,
        "inter_rater_agreement_computed": False,
        "output": str(OUTPUT),
        "output_sha256": sha256(OUTPUT),
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    SESSION.write_text(
        "\n".join(
            [
                f"generated_utc={manifest['generated_utc']}",
                f"python={sys.version.replace(chr(10), ' ')}",
                f"platform={platform.platform()}",
                f"seed={SEED}",
                f"source_sha256={manifest['source_sha256']}",
                f"contract_sha256={manifest['contract_sha256']}",
                "second_coder_completed=false",
                "inter_rater_agreement_computed=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"INDEPENDENT_RECODE_PACKET={OUTPUT}")
    print(f"SELECTED_SAMPLE_ORDERS={manifest['selected_sample_orders']}")
    print("SECOND_CODER_COMPLETED=false")


if __name__ == "__main__":
    main()
