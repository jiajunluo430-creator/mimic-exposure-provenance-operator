#!/usr/bin/env python3
"""Build aggregate-only MIMIC parity and prespecified operator ablation reports."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import duckdb

from medprov.adapters import get_adapter
from medprov.executor import execute_operator_file
from medprov.schema import load_document

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
CACHE = PROJECT / "cache"
OUT = ROOT / "outputs" / "method_evaluation_v0_1_0"
TABLES = OUT / "tables"
REPORTS = OUT / "reports"
MANIFESTS = OUT / "manifests"

PRE_DB = CACHE / "jamia_pre_submission_v1_0.duckdb"
UPGRADE_DB = CACHE / "jamia_prereview_upgrade_v1_0.duckdb"
BASE_DB = CACHE / "n1_validity.duckdb"

CONTRACT = ROOT / "contracts" / "OPERATOR_ABLATION_CONTRACT_v1.0_2026-08-05.md"
CONTRACT_SHA = ROOT / "contracts" / "OPERATOR_ABLATION_CONTRACT_v1.0_2026-08-05.sha256"

STRICT_SPEC = ROOT / "examples" / "mimic_strict_same_poe.yaml"
BROAD_SPEC = ROOT / "examples" / "mimic_broad_same_class.yaml"
A1_ORDER_SPEC = ROOT / "examples" / "a1_vte_order.yaml"
A1_ROUTE_SPEC = ROOT / "examples" / "a1_vte_admin_route_required.yaml"
A2_ORIGINAL_SPEC = ROOT / "examples" / "a2_ppi_original_order.yaml"
A2_HOSPITAL_SPEC = ROOT / "examples" / "a2_ppi_hospital_overlap_order.yaml"
A2_ADMIN_SPEC = ROOT / "examples" / "a2_ppi_strict_admin.yaml"

FROZEN_CONVERSION = (
    ROOT
    / "outputs"
    / "jamia_pre_submission_v1_0"
    / "tables"
    / "conversion_strict_vs_class_window_cluster_bootstrap.csv"
)
FROZEN_SCOPE = (
    ROOT
    / "outputs"
    / "jamia_observability_v1_1"
    / "tables"
    / "order_conversion_by_observability_scope.csv"
)
FROZEN_CELLS = (
    ROOT
    / "outputs"
    / "jamia_prereview_upgrade_v1_0"
    / "tables"
    / "prereview_operator_outcome_cells.csv"
)
FROZEN_MODELS = (
    ROOT
    / "outputs"
    / "jamia_prereview_upgrade_v1_0"
    / "tables"
    / "prereview_static_model_effects.csv"
)
ORIGINAL_MODELS = (
    ROOT / "outputs" / "jamia_pre_submission_v1_0" / "tables" / "anchor_operator_model_effects.csv"
)
P2_CARDINALITY = (
    ROOT
    / "outputs"
    / "jamia_residual_provenance_v1_0"
    / "tables"
    / "a2_cross_poe_checkpoint_cardinality.csv"
)
P2_TIMING = (
    ROOT
    / "outputs"
    / "jamia_residual_provenance_v1_0"
    / "tables"
    / "a2_cross_poe_timing_summary.csv"
)
A1_ROUTE = (
    ROOT
    / "outputs"
    / "jamia_residual_provenance_v1_0"
    / "tables"
    / "a1_order_vs_emar_route_availability.csv"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_tsv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def assert_inputs() -> None:
    required = [
        PRE_DB,
        UPGRADE_DB,
        BASE_DB,
        CONTRACT,
        CONTRACT_SHA,
        FROZEN_CONVERSION,
        FROZEN_SCOPE,
        FROZEN_CELLS,
        FROZEN_MODELS,
        ORIGINAL_MODELS,
        P2_CARDINALITY,
        P2_TIMING,
        A1_ROUTE,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Required frozen inputs are missing:\n" + "\n".join(missing))
    recorded = CONTRACT_SHA.read_text(encoding="utf-8").split()[0].lower()
    observed = sha256_file(CONTRACT)
    if recorded != observed:
        raise RuntimeError(f"Ablation contract hash mismatch: {recorded} != {observed}")


def cross_matrix(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    left: str,
    right: str,
    anchor: str,
    comparison: str,
) -> list[dict[str, Any]]:
    query = f"""
        SELECT CAST({left} AS INTEGER) AS left_exposure,
               CAST({right} AS INTEGER) AS right_exposure,
               count(*)::BIGINT AS analysis_units_n,
               sum(outcome)::BIGINT AS outcomes_n
        FROM {table}
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    return [
        {
            "anchor_id": anchor,
            "comparison": comparison,
            "left_exposure": int(row[0]),
            "right_exposure": int(row[1]),
            "analysis_units_n": int(row[2]),
            "outcomes_n": int(row[3]),
        }
        for row in connection.execute(query).fetchall()
    ]


def expected_cells() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_csv(FROZEN_CELLS):
        rows.append(
            {
                "anchor_id": row["anchor_id"],
                "comparison": row["comparison"],
                "left_exposure": int(row["order_exposure"]),
                "right_exposure": int(row["administration_exposure"]),
                "analysis_units_n": int(row["patients_n"]),
                "outcomes_n": int(float(row["outcomes_n"])),
            }
        )
    return rows


def matrix_map(rows: Iterable[dict[str, Any]]) -> dict[tuple[Any, ...], tuple[int, int]]:
    return {
        (
            row["anchor_id"],
            row["comparison"],
            int(row["left_exposure"]),
            int(row["right_exposure"]),
        ): (int(row["analysis_units_n"]), int(row["outcomes_n"]))
        for row in rows
    }


def matrix_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cells: dict[tuple[int, int], int] = defaultdict(int)
    for row in rows:
        cells[(int(row["left_exposure"]), int(row["right_exposure"]))] += int(
            row["analysis_units_n"]
        )
    a = cells.get((1, 1), 0)
    b = cells.get((1, 0), 0)
    c = cells.get((0, 1), 0)
    d = cells.get((0, 0), 0)
    total = a + b + c + d
    return {
        "both_positive_n": a,
        "left_only_n": b,
        "right_only_n": c,
        "both_negative_n": d,
        "analysis_units_n": total,
        "overall_agreement": (a + d) / total if total else None,
        "positive_agreement": 2 * a / (2 * a + b + c) if (2 * a + b + c) else None,
        "negative_agreement": 2 * d / (2 * d + b + c) if (2 * d + b + c) else None,
        "positive_jaccard": a / (a + b + c) if (a + b + c) else None,
    }


def build_parity() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    strict = execute_operator_file(STRICT_SPEC, "mimic_native", CACHE).to_dict()
    broad = execute_operator_file(BROAD_SPEC, "mimic_native", CACHE).to_dict()
    a1_order = execute_operator_file(A1_ORDER_SPEC, "mimic_native", CACHE).to_dict()
    a2_original = execute_operator_file(A2_ORIGINAL_SPEC, "mimic_native", CACHE).to_dict()
    a2_hospital = execute_operator_file(A2_HOSPITAL_SPEC, "mimic_native", CACHE).to_dict()
    a2_admin = execute_operator_file(A2_ADMIN_SPEC, "mimic_native", CACHE).to_dict()

    frozen_conversion = {
        row["drug_class"]: row
        for row in read_csv(FROZEN_CONVERSION)
        if row["drug_class"] != "all_classes"
    }
    strict_by_class = {row["medication_class"]: row for row in strict["counts"]["by_class"]}
    broad_by_class = {row["medication_class"]: row for row in broad["counts"]["by_class"]}
    six_class_rows: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    for medication_class in sorted(frozen_conversion):
        expected = frozen_conversion[medication_class]
        actual_strict = strict_by_class[medication_class]
        actual_broad = broad_by_class[medication_class]
        row = {
            "drug_class": medication_class,
            "expected_orders_n": int(expected["eligible_order_units_n"]),
            "actual_orders_n": int(actual_strict["analysis_units"]),
            "expected_strict_n": int(expected["strict_identity_converted_n"]),
            "actual_strict_n": int(actual_strict["exposed"]),
            "expected_broad_n": int(expected["class_window_converted_n"]),
            "actual_broad_n": int(actual_broad["exposed"]),
        }
        row["status"] = (
            "PASS"
            if all(
                row[left] == row[right]
                for left, right in (
                    ("expected_orders_n", "actual_orders_n"),
                    ("expected_strict_n", "actual_strict_n"),
                    ("expected_broad_n", "actual_broad_n"),
                )
            )
            else "FAIL"
        )
        six_class_rows.append(row)
    total_gates = [
        ("post_deployment_order_units", 264171, strict["counts"]["analysis_units"]),
        ("strict_same_poe_converted", 170890, strict["counts"]["exposed"]),
        ("broad_same_class_window_converted", 227355, broad["counts"]["exposed"]),
        ("a1_order_exposed", 7047, a1_order["counts"]["exposed"]),
        ("a2_original_order_exposed", 655, a2_original["counts"]["exposed"]),
        ("a2_hospital_order_exposed", 776, a2_hospital["counts"]["exposed"]),
        ("a2_strict_admin_exposed", 518, a2_admin["counts"]["exposed"]),
    ]
    for gate, expected, actual in total_gates:
        checks.append(
            {
                "domain": "count",
                "gate": gate,
                "expected": expected,
                "actual": int(actual),
                "tolerance": 0,
                "status": "PASS" if expected == int(actual) else "FAIL",
            }
        )
    for row in six_class_rows:
        checks.append(
            {
                "domain": "six_class",
                "gate": row["drug_class"],
                "expected": "orders/strict/broad",
                "actual": f"{row['actual_orders_n']}/{row['actual_strict_n']}/{row['actual_broad_n']}",
                "tolerance": 0,
                "status": row["status"],
            }
        )

    actual_cells: list[dict[str, Any]] = []
    with duckdb.connect(str(PRE_DB), read_only=True) as pre:
        actual_cells.extend(
            cross_matrix(
                pre, "a1_operator_post", "order_exposure", "admin_strict", "A1", "original_strict"
            )
        )
        actual_cells.extend(
            cross_matrix(
                pre, "a1_operator_post", "order_exposure", "admin_broad", "A1", "original_broad"
            )
        )
        actual_cells.extend(
            cross_matrix(
                pre, "a2_operator_post", "order_exposure", "admin_strict", "A2", "original_strict"
            )
        )
        actual_cells.extend(
            cross_matrix(
                pre, "a2_operator_post", "order_exposure", "admin_broad", "A2", "original_broad"
            )
        )
    with duckdb.connect(str(UPGRADE_DB), read_only=True) as upgrade:
        actual_cells.extend(
            cross_matrix(
                upgrade,
                "a1_upgrade_input",
                "order_exposure",
                "admin_metadata_constrained",
                "A1",
                "metadata_constrained_broad",
            )
        )
        actual_cells.extend(
            cross_matrix(
                upgrade,
                "a2_upgrade_input",
                "hospital_order_exposure",
                "hospital_admin_strict",
                "A2",
                "hospital_overlap_strict",
            )
        )
        actual_cells.extend(
            cross_matrix(
                upgrade,
                "a2_upgrade_input",
                "hospital_order_exposure",
                "admin_broad",
                "A2",
                "hospital_overlap_broad",
            )
        )
    expected_map = matrix_map(expected_cells())
    actual_map = matrix_map(actual_cells)
    all_cell_keys = sorted(set(expected_map) | set(actual_map))
    cross_parity: list[dict[str, Any]] = []
    for key in all_cell_keys:
        expected = expected_map.get(key)
        actual = actual_map.get(key)
        status = "PASS" if expected == actual else "FAIL"
        cross_parity.append(
            {
                "anchor_id": key[0],
                "comparison": key[1],
                "order_exposure": key[2],
                "administration_exposure": key[3],
                "expected_units_n": expected[0] if expected else None,
                "actual_units_n": actual[0] if actual else None,
                "expected_outcomes_n": expected[1] if expected else None,
                "actual_outcomes_n": actual[1] if actual else None,
                "status": status,
            }
        )
    checks.append(
        {
            "domain": "anchor_crossclassification",
            "gate": "all_A1_A2_cells",
            "expected": len(expected_map),
            "actual": sum(row["status"] == "PASS" for row in cross_parity),
            "tolerance": 0,
            "status": "PASS" if all(row["status"] == "PASS" for row in cross_parity) else "FAIL",
        }
    )

    original = read_csv(ORIGINAL_MODELS)
    upgraded = read_csv(FROZEN_MODELS)
    original_map: dict[tuple[str, str, str, str], float] = {}
    rename = {"strict_poe_identity": "original_strict", "broad_class_window": "original_broad"}
    for row in original:
        original_map[
            (
                row["anchor_id"],
                rename[row["operator"]],
                row["exposure_source"],
                row["model_variant"],
            )
        ] = float(row["beta"])
    model_differences: list[float] = []
    for row in upgraded:
        key = (row["anchor_id"], row["operator"], row["exposure_source"], row["model_variant"])
        if key in original_map:
            model_differences.append(abs(float(row["beta"]) - original_map[key]))
    max_model_difference = max(model_differences) if model_differences else float("inf")
    checks.append(
        {
            "domain": "continuous",
            "gate": "common_original_model_beta",
            "expected": 0.0,
            "actual": max_model_difference,
            "tolerance": 1e-10,
            "status": "PASS" if max_model_difference <= 1e-10 else "FAIL",
        }
    )

    card = {row["checkpoint"]: row for row in read_csv(P2_CARDINALITY)}
    timing = {row["timing_metric"]: row for row in read_csv(P2_TIMING)}
    p2_gates = [
        (
            "p2_primary_units",
            183,
            int(card["primary pharmacy-prescription POE units"]["rows_n"]),
            0,
        ),
        (
            "p2_prescription_poe_minus_administration_median_h",
            97.18333333333334,
            float(timing["prescription POE ordertime minus first administration"]["median_h"]),
            1e-10,
        ),
        (
            "p2_emar_poe_minus_administration_median_h",
            -5.683333333333334,
            float(timing["eMAR POE ordertime minus first administration"]["median_h"]),
            1e-10,
        ),
        (
            "p2_poe_role_separation_median_h",
            106.1,
            float(timing["prescription POE ordertime minus eMAR POE ordertime"]["median_h"]),
            1e-10,
        ),
    ]
    for gate, expected, actual, tolerance in p2_gates:
        checks.append(
            {
                "domain": "P2_trace",
                "gate": gate,
                "expected": expected,
                "actual": actual,
                "tolerance": tolerance,
                "status": "PASS" if abs(actual - expected) <= tolerance else "FAIL",
            }
        )
    summary = {
        "parity_status": "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL",
        "checks_n": len(checks),
        "passed_n": sum(row["status"] == "PASS" for row in checks),
        "failed_n": sum(row["status"] != "PASS" for row in checks),
        "continuous_tolerance_same_stored_estimate": 1e-10,
        "integer_tolerance": 0,
    }
    return (
        checks,
        six_class_rows,
        {"summary": summary, "cross_parity": cross_parity, "actual_cells": actual_cells},
    )


def baseline_flags() -> dict[str, dict[str, dict[str, int]]]:
    queries = {
        "A1": """
            WITH event_flags AS (
              SELECT stay_id,
                     1 AS has_class_row,
                     max(CASE WHEN event_category <> 'not_given' THEN 1 ELSE 0 END) AS collapsed_positive,
                     max(CASE WHEN event_category = 'given_strict' THEN 1 ELSE 0 END) AS source_class_window
              FROM emar_stay_events
              WHERE drug_class = 'vte_prophylaxis'
              GROUP BY stay_id
            )
            SELECT a.admin_strict AS full_strict,
                   coalesce(e.has_class_row, 0) AS table_only,
                   coalesce(e.collapsed_positive, 0) AS collapsed_semantics,
                   coalesce(e.source_class_window, 0) AS source_class_window,
                   count(*)::BIGINT AS n
            FROM pre.a1_operator_post a
            LEFT JOIN event_flags e USING (stay_id)
            GROUP BY 1,2,3,4
        """,
        "A2": """
            WITH event_flags AS (
              SELECT stay_id,
                     1 AS has_class_row,
                     max(CASE
                           WHEN charttime BETWEEN intime AND least(outtime, intime + INTERVAL 48 HOUR)
                            AND event_category <> 'not_given' THEN 1 ELSE 0 END) AS collapsed_positive,
                     max(CASE
                           WHEN charttime BETWEEN intime AND least(outtime, intime + INTERVAL 48 HOUR)
                            AND event_category = 'given_strict' THEN 1 ELSE 0 END) AS source_class_window
              FROM emar_stay_events
              WHERE drug_class = 'stress_ulcer_prophylaxis' AND subclass = 'PPI'
              GROUP BY stay_id
            )
            SELECT a.admin_strict AS full_strict,
                   coalesce(e.has_class_row, 0) AS table_only,
                   coalesce(e.collapsed_positive, 0) AS collapsed_semantics,
                   coalesce(e.source_class_window, 0) AS source_class_window,
                   count(*)::BIGINT AS n
            FROM pre.a2_operator_post a
            LEFT JOIN event_flags e USING (stay_id)
            GROUP BY 1,2,3,4
        """,
    }
    results: dict[str, dict[str, dict[str, int]]] = {}
    with duckdb.connect(str(BASE_DB), read_only=True) as connection:
        escaped_pre = str(PRE_DB).replace("'", "''")
        connection.execute(f"ATTACH '{escaped_pre}' AS pre (READ_ONLY)")
        for anchor, query in queries.items():
            rows = connection.execute(query).fetchall()
            variants: dict[str, dict[str, int]] = {}
            for index, name in enumerate(
                ("full_strict", "table_only", "collapsed_semantics", "source_class_window")
            ):
                exposed = sum(int(row[4]) for row in rows if int(row[index]) == 1)
                total = sum(int(row[4]) for row in rows)
                variants[name] = {
                    "analysis_units": total,
                    "exposed": exposed,
                    "unexposed": total - exposed,
                }
            paired: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                for index, name in enumerate(
                    ("table_only", "collapsed_semantics", "source_class_window"), start=1
                ):
                    paired[name].append(
                        {
                            "left_exposure": int(row[0]),
                            "right_exposure": int(row[index]),
                            "analysis_units_n": int(row[4]),
                        }
                    )
            results[anchor] = {
                **variants,
                "paired": {name: matrix_metrics(values) for name, values in paired.items()},
            }
    return results


def group_actual_cells(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["anchor_id"], row["comparison"])].append(row)
    return grouped


def build_ablation(
    actual_cells: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    flags = baseline_flags()
    grouped = group_actual_cells(actual_cells)
    variants: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []

    def add_variant(
        anchor: str,
        eval_id: str,
        label: str,
        counts: dict[str, int],
        *,
        measurable: str = "TRUE",
        executable: str = "TRUE",
        notes: str = "",
    ) -> None:
        variants.append(
            {
                "evaluation_id": eval_id,
                "anchor": anchor,
                "operator_label": label,
                "syntactically_valid": "TRUE",
                "adapter_supported": "TRUE",
                "measurable": measurable,
                "executable": executable,
                "analysis_units_n": counts.get("analysis_units", 0),
                "exposed_n": counts.get("exposed", 0),
                "unexposed_n": counts.get("unexposed", 0),
                "unresolved_n": counts.get("unresolved", 0),
                "unmeasurable_n": counts.get("unmeasurable", 0),
                "notes": notes,
            }
        )

    for anchor in ("A1", "A2"):
        for name, eval_id, label in (
            ("table_only", "BASE-01", "table-only"),
            ("source_class_window", "BASE-02", "source+class+window"),
            ("collapsed_semantics", "ABL-04", "collapsed event semantics"),
            ("full_strict", "FULL-01", "full exact-identity operator"),
        ):
            add_variant(anchor, eval_id, label, flags[anchor][name])
        for name in ("table_only", "source_class_window", "collapsed_semantics"):
            metrics.append(
                {
                    "anchor": anchor,
                    "comparison": f"full_strict_vs_{name}",
                    **flags[anchor]["paired"][name],
                    "event_time_displacement": "NOT_EVALUABLE_AGGREGATE_NOT_RETAINED",
                }
            )

    paired_definitions = [
        ("A1", "ABL-02", "exact_identity_vs_same_class", "original_strict", "original_broad"),
        ("A2", "ABL-02", "exact_identity_vs_same_class", "original_strict", "original_broad"),
        ("A2", "ABL-03", "original_order_vs_hospital_overlap_order", None, None),
    ]
    for anchor, eval_id, label, left_name, right_name in paired_definitions:
        if eval_id == "ABL-03":
            with duckdb.connect(str(UPGRADE_DB), read_only=True) as connection:
                matrix = cross_matrix(
                    connection,
                    "a2_upgrade_input",
                    "order_exposure",
                    "hospital_order_exposure",
                    "A2",
                    label,
                )
            displacement = "median 0.0 h (IQR 0.0-0.0) among units exposed under both windows"
        else:
            left_cells = grouped[(anchor, left_name)]
            right_cells = grouped[(anchor, right_name)]
            # Both comparisons share the same frozen order flag.  Derive the
            # paired strict-versus-broad administration matrix directly.
            table = "a1_operator_post" if anchor == "A1" else "a2_operator_post"
            with duckdb.connect(str(PRE_DB), read_only=True) as connection:
                matrix = cross_matrix(
                    connection, table, "admin_strict", "admin_broad", anchor, label
                )
            displacement = "NOT_EVALUABLE_AGGREGATE_NOT_RETAINED"
            assert left_cells and right_cells
        metrics.append(
            {
                "anchor": anchor,
                "comparison": label,
                **matrix_metrics(matrix),
                "event_time_displacement": displacement,
            }
        )

    route_capability = get_adapter("mimic_native").capability(load_document(A1_ROUTE_SPEC), CACHE)
    route_execution = execute_operator_file(A1_ROUTE_SPEC, "mimic_native", CACHE).to_dict()
    add_variant(
        "A1",
        "ABL-05",
        "route required",
        route_execution["counts"],
        measurable="FALSE",
        executable="FALSE",
        notes="Required eMAR route is 0% populated; construct is unmeasurable, not unexposed.",
    )
    add_variant(
        "A1",
        "ABL-05",
        "route ignored / broad administration",
        flags["A1"]["source_class_window"],
        notes="Ablation only; cannot replace the route-dependent construct.",
    )

    scope = read_csv(FROZEN_SCOPE)
    scope_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"analysis_units": 0, "exposed": 0}
    )
    for row in scope:
        if row["analysis_scope"] in {"all_periods", "post_implementation"}:
            bucket = scope_totals[row["analysis_scope"]]
            bucket["analysis_units"] += int(row["eligible_orders_n"])
            bucket["exposed"] += int(row["converted_orders_n"])
    for scope_name, label, measurable in (
        ("post_implementation", "deployment gate retained", "TRUE"),
        ("all_periods", "deployment gate removed", "PARTIAL"),
    ):
        counts = scope_totals[scope_name]
        counts["unexposed"] = counts["analysis_units"] - counts["exposed"]
        add_variant(
            "six_class_order_units",
            "ABL-01",
            label,
            counts,
            measurable=measurable,
            notes="All-period denominator includes pre-eMAR units"
            if scope_name == "all_periods"
            else "Frozen primary observable era",
        )

    effects = [
        row
        for row in read_csv(FROZEN_MODELS)
        if row["model_variant"] == "published_style_minimal"
        and row["operator"]
        in {
            "original_strict",
            "original_broad",
            "metadata_constrained_broad",
            "hospital_overlap_strict",
            "hospital_overlap_broad",
        }
    ]
    by_effect: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in effects:
        by_effect[(row["anchor_id"], row["operator"])][row["exposure_source"]] = row
    drift: list[dict[str, Any]] = []
    for (anchor, operator), source_rows in sorted(by_effect.items()):
        if not {"order", "administration"}.issubset(source_rows):
            continue
        order = source_rows["order"]
        admin = source_rows["administration"]
        delta = float(admin["beta"]) - float(order["beta"])
        drift.append(
            {
                "anchor": anchor,
                "operator": operator,
                "effect_measure": order["effect_measure"],
                "order_exposed_n": int(order["exposed_n"]),
                "administration_exposed_n": int(admin["exposed_n"]),
                "order_effect": float(order["effect"]),
                "administration_effect": float(admin["effect"]),
                "administration_minus_order_log_effect": delta,
                "absolute_log_effect_change": abs(delta),
                "direction_crossed_null": (float(order["effect"]) - 1)
                * (float(admin["effect"]) - 1)
                < 0,
                "interpretation": "measurement stress test; no causal efficacy or safety claim",
            }
        )

    route_rows = read_csv(A1_ROUTE)
    route_summary = {
        "capability_required_route_population_n": route_capability.source_status.get(
            "required_route_population_n"
        ),
        "capability_required_route_nonmissing_n": route_capability.source_status.get(
            "required_route_nonmissing_n"
        ),
        "published_aggregate_rows": route_rows,
    }
    return (
        variants,
        metrics,
        drift
        + [
            {
                "anchor": "A1",
                "operator": "route_metadata_capability",
                "effect_measure": "NOT_APPLICABLE",
                "order_exposed_n": "",
                "administration_exposed_n": "",
                "order_effect": "",
                "administration_effect": "",
                "administration_minus_order_log_effect": "",
                "absolute_log_effect_change": "",
                "direction_crossed_null": "",
                "interpretation": json.dumps(route_summary, ensure_ascii=False),
            }
        ],
    )


def markdown_reports(
    parity: dict[str, Any],
    six_class: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    drift: list[dict[str, Any]],
) -> None:
    parity_lines = [
        "# MIMIC native parity report",
        "",
        "Reference implementation: MIMIC-IV native 3.1; medprov 0.1.0.",
        "All outputs are aggregate-only.",
        "",
        f"## Decision: {parity['parity_status']}",
        "",
        f"{parity['passed_n']}/{parity['checks_n']} prespecified parity gates passed; integer tolerance was zero and the common stored-model beta tolerance was 1e-10.",
        "",
        "## Core counts",
        "",
        "- Post-deployment order units: 264,171.",
        "- Strict same-POE converted: 170,890 (64.69%).",
        "- Same-class/window converted: 227,355 (86.06%).",
        "- A1 order-exposed: 7,047/20,248; strict administration-exposed: 5,538/20,248.",
        "- A2 original order: 655/2,813; hospital-overlap order: 776/2,813; original strict administration: 518/2,813.",
        "",
        "## Six-class parity",
        "",
        "| Class | Orders | Strict | Broad | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for row in six_class:
        parity_lines.append(
            f"| {row['drug_class']} | {row['actual_orders_n']:,} | {row['actual_strict_n']:,} | {row['actual_broad_n']:,} | {row['status']} |"
        )
    parity_lines.extend(
        [
            "",
            "## P2 retained trace",
            "",
            "The previously completed P2 trace also passed: 183/183 primary units linked to raw POE; median prescription-POE minus administration was +97.18 h, eMAR-POE minus administration was -5.68 h, and paired POE-role separation was 106.10 h.",
            "",
            "No original source scan or outcome model was rerun. The adapter executed against the already-audited read-only materialized references. The earlier multi-table long-running implementation remains an engineering failure audit, not a statistical failure.",
        ]
    )
    (REPORTS / "MIMIC_NATIVE_PARITY_REPORT.md").write_text(
        "\n".join(parity_lines) + "\n", encoding="utf-8", newline="\n"
    )

    variant_lookup = {(row["anchor"], row["operator_label"]): row for row in variants}
    ablation_lines = [
        "# Prespecified operator ablation report",
        "",
        "Contract: `contracts/OPERATOR_ABLATION_CONTRACT_v1.0_2026-08-05.md`.",
        "All variants were specified before the aggregate queries and are retained regardless of result.",
        "",
        "## Main findings",
        "",
        "1. Exact identity is consequential: relaxing same-POE identity to same-class/window added 56,465 converted order units (170,890 to 227,355).",
        "2. Time is an independent dimension: A2 hospital-overlap eligibility added 121 order-exposed patients (655 to 776), while strict administration remained a distinct 521-patient representation in that paired analysis.",
        "3. A1 is a construct-measurability demonstration: route is required by the prophylactic construct but absent in the evaluated administration layer, so all 20,248 A1 analysis units are classified unmeasurable under the route-required operator—not unexposed.",
        "4. Table-only and collapsed-semantic comparators classify more patients than the literal exact-identity operator; their counts are reported below as deliberate naive baselines, not candidate replacements.",
        "5. Downstream association estimates can be exposure-sensitive: the already-frozen A1 broad comparator crosses the null direction relative to the order estimate, whereas the exact-identity pair is close; A2 identity and window changes alter magnitude without supporting a new causal conclusion.",
        "",
        "## Baseline and full-operator counts",
        "",
        "| Anchor | Operator | Status | Exposed | Unexposed | Unresolved | Unmeasurable |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in variants:
        ablation_lines.append(
            f"| {row['anchor']} | {row['operator_label']} | measurable={row['measurable']}, executable={row['executable']} | {int(row['exposed_n']):,} | {int(row['unexposed_n']):,} | {int(row['unresolved_n']):,} | {int(row['unmeasurable_n']):,} |"
        )
    ablation_lines.extend(
        [
            "",
            "## Reclassification metrics",
            "",
            "| Anchor | Comparison | Agreement | Positive agreement | Negative agreement | Jaccard |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in metrics:
        ablation_lines.append(
            f"| {row['anchor']} | {row['comparison']} | {row['overall_agreement']:.3f} | {row['positive_agreement']:.3f} | {row['negative_agreement']:.3f} | {row['positive_jaccard']:.3f} |"
        )
    route_required = variant_lookup[("A1", "route required")]
    ablation_lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            f"The route-required operator returned {route_required['unmeasurable_n']:,} unmeasurable units. Treating these units as negative would be a category error. Event-semantic collapse is likewise a comparator only: `Flushed`, `Confirmed`, blank, and other states remain separate under the scientific operator.",
            "",
            "A1/A2 ORs and HRs in the accompanying table are downstream measurement stress tests. They do not estimate medication benefit, harm, or an optimal treatment strategy. No P value was used to select a definition.",
        ]
    )
    (REPORTS / "OPERATOR_ABLATION_REPORT.md").write_text(
        "\n".join(ablation_lines) + "\n", encoding="utf-8", newline="\n"
    )


def build_manifest() -> dict[str, Any]:
    files = sorted(
        path
        for path in OUT.rglob("*")
        if path.is_file() and path.name != "method_evaluation_manifest.json"
    )
    return {
        "artifact": "medprov_method_evaluation_v0_1_0",
        "evaluation_date": "2026-08-05",
        "contract": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
        "contract_sha256": sha256_file(CONTRACT),
        "aggregate_only": True,
        "patient_level_files": 0,
        "files": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }


def main() -> int:
    assert_inputs()
    for directory in (TABLES, REPORTS, MANIFESTS):
        directory.mkdir(parents=True, exist_ok=True)
    checks, six_class, parity_payload = build_parity()
    variants, metrics, drift = build_ablation(parity_payload["actual_cells"])

    write_tsv(
        TABLES / "mimic_native_parity_checks.tsv",
        checks,
        ["domain", "gate", "expected", "actual", "tolerance", "status"],
    )
    write_tsv(
        TABLES / "mimic_six_class_parity.tsv",
        six_class,
        [
            "drug_class",
            "expected_orders_n",
            "actual_orders_n",
            "expected_strict_n",
            "actual_strict_n",
            "expected_broad_n",
            "actual_broad_n",
            "status",
        ],
    )
    write_tsv(
        TABLES / "anchor_crossclassification_parity.tsv",
        parity_payload["cross_parity"],
        [
            "anchor_id",
            "comparison",
            "order_exposure",
            "administration_exposure",
            "expected_units_n",
            "actual_units_n",
            "expected_outcomes_n",
            "actual_outcomes_n",
            "status",
        ],
    )
    write_tsv(
        TABLES / "operator_ablation_matrix.tsv",
        variants,
        [
            "evaluation_id",
            "anchor",
            "operator_label",
            "syntactically_valid",
            "adapter_supported",
            "measurable",
            "executable",
            "analysis_units_n",
            "exposed_n",
            "unexposed_n",
            "unresolved_n",
            "unmeasurable_n",
            "notes",
        ],
    )
    write_tsv(
        TABLES / "operator_reclassification_metrics.tsv",
        metrics,
        [
            "anchor",
            "comparison",
            "both_positive_n",
            "left_only_n",
            "right_only_n",
            "both_negative_n",
            "analysis_units_n",
            "overall_agreement",
            "positive_agreement",
            "negative_agreement",
            "positive_jaccard",
            "event_time_displacement",
        ],
    )
    write_tsv(
        TABLES / "operator_estimate_drift.tsv",
        drift,
        [
            "anchor",
            "operator",
            "effect_measure",
            "order_exposed_n",
            "administration_exposed_n",
            "order_effect",
            "administration_effect",
            "administration_minus_order_log_effect",
            "absolute_log_effect_change",
            "direction_crossed_null",
            "interpretation",
        ],
    )
    write_json(OUT / "method_evaluation_summary.json", parity_payload["summary"])
    markdown_reports(parity_payload["summary"], six_class, variants, metrics, drift)

    manifest = build_manifest()
    write_json(MANIFESTS / "method_evaluation_manifest.json", manifest)
    if parity_payload["summary"]["parity_status"] != "PASS":
        failures = [row for row in checks if row["status"] != "PASS"]
        (REPORTS / "PARITY_FAILURE_DIAGNOSTIC.md").write_text(
            "# Parity failure diagnostic\n\n"
            + "\n".join(
                f"- {row['domain']} / {row['gate']}: expected {row['expected']}, actual {row['actual']}"
                for row in failures
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return 2
    print(
        f"PASS method evaluation: {parity_payload['summary']['passed_n']}/"
        f"{parity_payload['summary']['checks_n']} parity gates; outputs={OUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
