"""Comparison of aggregate medprov execution results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .utils import canonical_json_sha256


def _class_map(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = result.get("counts", {}).get("by_class", [])
    return {str(row["medication_class"]): row for row in rows if "medication_class" in row}


def compare_results(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_counts = left.get("counts", {})
    right_counts = right.get("counts", {})
    exposed_left = int(left_counts.get("exposed", 0))
    exposed_right = int(right_counts.get("exposed", 0))
    output: dict[str, Any] = {
        "left_operator": left.get("operator_id"),
        "right_operator": right.get("operator_id"),
        "left_result_sha256": canonical_json_sha256(left),
        "right_result_sha256": canonical_json_sha256(right),
        "aggregate_differences": {
            "analysis_units": int(right_counts.get("analysis_units", 0))
            - int(left_counts.get("analysis_units", 0)),
            "exposed": exposed_right - exposed_left,
            "unexposed": int(right_counts.get("unexposed", 0))
            - int(left_counts.get("unexposed", 0)),
            "unresolved": int(right_counts.get("unresolved", 0))
            - int(left_counts.get("unresolved", 0)),
            "unmeasurable": int(right_counts.get("unmeasurable", 0))
            - int(left_counts.get("unmeasurable", 0)),
            "relative_exposed_change": ((exposed_right - exposed_left) / exposed_left)
            if exposed_left
            else None,
        },
        "by_class": [],
        "patient_level_metrics": {
            "available": False,
            "reason": "Aggregate result files do not contain restricted analysis-unit identifiers or a prespecified cross-classification matrix.",
        },
    }
    left_class = _class_map(left)
    right_class = _class_map(right)
    for medication_class in sorted(set(left_class) | set(right_class)):
        left_row = left_class.get(medication_class, {})
        right_row = right_class.get(medication_class, {})
        output["by_class"].append(
            {
                "medication_class": medication_class,
                "left_exposed": int(left_row.get("exposed", 0)),
                "right_exposed": int(right_row.get("exposed", 0)),
                "exposed_difference": int(right_row.get("exposed", 0))
                - int(left_row.get("exposed", 0)),
            }
        )
    cross = right.get("metrics", {}).get("crossclassification") or left.get("metrics", {}).get(
        "crossclassification"
    )
    if isinstance(cross, dict) and all(
        key in cross for key in ("both_positive", "left_only", "right_only")
    ):
        denominator = (
            int(cross["both_positive"]) + int(cross["left_only"]) + int(cross["right_only"])
        )
        output["patient_level_metrics"] = {
            "available": True,
            "jaccard": int(cross["both_positive"]) / denominator if denominator else None,
            "crossclassification": cross,
        }
    return output


def compare_result_files(left: str | Path, right: str | Path) -> dict[str, Any]:
    left_value = json.loads(Path(left).read_text(encoding="utf-8"))
    right_value = json.loads(Path(right).read_text(encoding="utf-8"))
    return compare_results(left_value, right_value)
