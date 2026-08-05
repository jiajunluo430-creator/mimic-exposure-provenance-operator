#!/usr/bin/env python3
"""Compute prespecified agreement after a real independent recode is supplied."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

DIMENSIONS = (
    "source_layer",
    "identity_rule",
    "time_origin_window",
    "event_semantics_map",
    "required_metadata",
)


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def primary_status(record: dict, dimension: str) -> str:
    return str(record["dimensions"][dimension]["status"])


def second_status(record: dict, dimension: str) -> str:
    return str(record["dimensions"][dimension])


def kappa(left: Iterable[str], right: Iterable[str]) -> tuple[float, float | None]:
    left_values = list(left)
    right_values = list(right)
    if len(left_values) != len(right_values) or not left_values:
        raise ValueError("Agreement vectors must be nonempty and equal length")
    n = len(left_values)
    observed = sum(a == b for a, b in zip(left_values, right_values, strict=True)) / n
    left_counts = Counter(left_values)
    right_counts = Counter(right_values)
    expected = sum(
        (left_counts[category] / n) * (right_counts[category] / n)
        for category in set(left_counts) | set(right_counts)
    )
    value = (observed - expected) / (1 - expected) if expected < 1 else None
    return observed, value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    primary = {row["study_id"]: row for row in load_jsonl(args.primary)}
    second = {row["study_id"]: row for row in load_jsonl(args.second)}
    if set(primary) != set(second):
        missing_second = sorted(set(primary) - set(second))
        missing_primary = sorted(set(second) - set(primary))
        raise ValueError(
            f"Study sets differ; missing_second={missing_second}, missing_primary={missing_primary}"
        )
    rows = []
    for dimension in DIMENSIONS:
        ids = sorted(primary)
        left = [primary_status(primary[study_id], dimension) for study_id in ids]
        right = [second_status(second[study_id], dimension) for study_id in ids]
        agreement, coefficient = kappa(left, right)
        rows.append(
            {
                "dimension": dimension,
                "studies_n": len(ids),
                "percent_agreement": 100 * agreement,
                "cohen_kappa": coefficient,
                "categories": ["reported", "missing", "ambiguous", "not_applicable"],
            }
        )
    output = {
        "status": "COMPLETED_WITH_INDEPENDENT_HUMAN_INPUT",
        "missing_ambiguous_policy": "separate nominal categories",
        "dimensions": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"WROTE agreement dimensions={len(rows)} output={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
