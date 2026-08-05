#!/usr/bin/env python3
"""Validate and import a genuinely independent coder's completed worksheet."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

DIMENSIONS = (
    "source_layer",
    "identity_rule",
    "time_origin_window",
    "event_semantics_map",
    "required_metadata",
)
ALLOWED = {"reported", "missing", "ambiguous", "not_applicable"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("worksheet", type=Path)
    parser.add_argument("--coder-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.coder_id.strip().lower() in {"primary_coder_1", "codex", "ai", "llm"}:
        raise ValueError("A genuinely independent human coder identifier is required")
    with args.worksheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Second-coder worksheet is empty")
    output = []
    for row_number, row in enumerate(rows, start=2):
        study_id = (row.get("study_id") or "").strip()
        if not study_id:
            raise ValueError(f"Missing study_id at worksheet row {row_number}")
        statuses = {}
        for dimension in DIMENSIONS:
            value = (row.get(dimension) or "").strip().lower()
            if value not in ALLOWED:
                raise ValueError(
                    f"Invalid {dimension}={value!r} at row {row_number}; allowed={sorted(ALLOWED)}"
                )
            statuses[dimension] = value
        output.append(
            {
                "study_id": study_id,
                "coder_id": args.coder_id.strip(),
                "dimensions": statuses,
                "notes": (row.get("coder_notes") or "").strip(),
            }
        )
    if len({row["study_id"] for row in output}) != len(output):
        raise ValueError("Duplicate study_id in second-coder worksheet")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "\n".join(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in output) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"IMPORTED independent_coder_records={len(output)} output={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
