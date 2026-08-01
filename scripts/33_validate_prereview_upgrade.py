#!/usr/bin/env python3
"""Validate the frozen prereview upgrade using aggregate, patient-free outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "jamia_prereview_upgrade_addendum_v1.0_2026-07-31.md"
UPGRADE = ROOT / "outputs" / "jamia_prereview_upgrade_v1_0"
TABLES = UPGRADE / "tables"
MANIFESTS = UPGRADE / "manifests"
EXPECTED_CONTRACT_SHA = "0a851a99c9176c16deda2cde9e30fded7f2b5131a5a3f64ac7f050ebd8f81d9d"


def read_csv(name: str) -> list[dict[str, str]]:
    with (TABLES / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(name: str) -> dict:
    return json.loads((MANIFESTS / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def close(value: str | float, expected: float, tolerance: float = 5e-4) -> bool:
    return math.isclose(float(value), expected, rel_tol=0, abs_tol=tolerance)


def main() -> int:
    checks: list[dict[str, object]] = []

    def check(check_id: str, description: str, passed: bool, evidence: str) -> None:
        checks.append(
            {
                "check_id": check_id,
                "description": description,
                "passed": bool(passed),
                "evidence": evidence,
            }
        )

    analytics = load_json("28_prereview_upgrade_analytics_manifest.json")
    models = load_json("29_prereview_upgrade_models_manifest.json")
    rxnav = load_json("30_rxnav_ndc_validation_manifest.json")
    retrieval = load_json("31_published_operator_retrieval_manifest.json")
    landscape = load_json("32_published_operator_landscape_manifest.json")

    observed_sha = sha256(CONTRACT)
    manifests = (analytics, models, rxnav, retrieval, landscape)
    check(
        "U01",
        "Frozen prereview addendum hash is unchanged across all upgrade stages",
        observed_sha == EXPECTED_CONTRACT_SHA
        and all(item.get("contract_sha256") == EXPECTED_CONTRACT_SHA for item in manifests),
        f"observed={observed_sha}; manifests={sum(item.get('contract_sha256') == EXPECTED_CONTRACT_SHA for item in manifests)}/5",
    )

    before = analytics["raw_source_before"]
    after = analytics["raw_source_after"]
    check(
        "U02",
        "MIMIC source was unchanged and analytic database was read-only",
        before == after and analytics.get("base_database_read_only") is True and models.get("raw_data_modified") is False,
        f"source_equal={before == after}; base_read_only={analytics.get('base_database_read_only')}; model_raw_modified={models.get('raw_data_modified')}",
    )

    check(
        "U03",
        "All static, time-varying, and paired-bootstrap models completed",
        models.get("static_models_n") == 28
        and models.get("static_models_converged_n") == 28
        and models.get("time_varying_models_n") == 16
        and models.get("time_varying_models_converged_n") == 16
        and models.get("bootstrap_comparisons_n") == 22
        and models.get("bootstrap_min_success_n") == 1000,
        "static=28/28; time-varying=16/16; bootstrap=22 comparisons with minimum 1,000 successes",
    )

    cells = read_csv("prereview_operator_outcome_cells.csv")
    grouped: dict[tuple[str, str], int] = {}
    for row in cells:
        key = (row["anchor_id"], row["comparison"])
        grouped[key] = grouped.get(key, 0) + int(row["patients_n"])
    expected_n = {"A1": 20248, "A2": 2813}
    check(
        "U04",
        "Each reported operator cell table reconciles to its complete anchor cohort",
        len(grouped) == 7 and all(total == expected_n[key[0]] for key, total in grouped.items()),
        f"operators={len(grouped)}; totals={grouped}",
    )

    a1_prov = read_csv("a1_broad_admin_only_provenance_summary.csv")
    a1_counts = {row["provenance_category"]: int(row["patients_n"]) for row in a1_prov}
    expected_a1 = {
        "vte_prescription_elsewhere_in_admission": 3843,
        "same_poe_vte_prescription_outside_original_eligibility": 1456,
        "observed_metadata_inconsistent_with_prophylaxis": 271,
        "different_poe_vte_order_assigned_to_icu_stay": 245,
        "no_mapped_vte_prescription_in_admission": 1,
    }
    check(
        "U05",
        "A1 broad administration-only provenance is mutually exclusive and complete",
        a1_counts == expected_a1 and sum(a1_counts.values()) == 5816,
        f"counts={a1_counts}; total={sum(a1_counts.values())}",
    )

    a2_prov = read_csv("a2_order_window_provenance_summary.csv")
    a2_counts = {row["provenance_category"]: int(row["patients_n"]) for row in a2_prov}
    expected_a2 = {
        "no_hospital_overlap_ppi_order_in_admission": 184,
        "different_poe_hospital_overlap_order_in_admission": 94,
        "same_poe_hospital_overlap_order_outside_original_window": 9,
        "emar_poe_missing_or_not_identity_resolvable": 9,
    }
    check(
        "U06",
        "A2 broad administration-only provenance is mutually exclusive and complete",
        a2_counts == expected_a2 and sum(a2_counts.values()) == 296,
        f"counts={a2_counts}; total={sum(a2_counts.values())}",
    )

    static = read_csv("prereview_static_model_effects.csv")

    def static_row(anchor: str, operator: str, source: str, model: str = "published_style_minimal") -> dict[str, str]:
        return next(
            row
            for row in static
            if row["anchor_id"] == anchor
            and row["operator"] == operator
            and row["exposure_source"] == source
            and row["model_variant"] == model
        )

    expected_static = [
        ("A1", "original_strict", "order", 1.868346),
        ("A1", "original_strict", "administration", 1.953035),
        ("A1", "original_broad", "administration", 0.906847),
        ("A1", "metadata_constrained_broad", "administration", 0.909169),
        ("A2", "original_strict", "order", 1.904039),
        ("A2", "original_strict", "administration", 1.925715),
        ("A2", "original_broad", "administration", 1.207663),
        ("A2", "hospital_overlap_strict", "order", 1.643379),
        ("A2", "hospital_overlap_broad", "administration", 1.207663),
    ]
    static_ok = all(close(static_row(a, o, s)["effect"], value, 2e-3) for a, o, s, value in expected_static)
    check(
        "U07",
        "Headline static operator effects reproduce the frozen model table",
        len(static) == 28 and all(row["converged"].upper() == "TRUE" for row in static) and static_ok,
        f"rows={len(static)}; converged={sum(row['converged'].upper() == 'TRUE' for row in static)}; headline_values={static_ok}",
    )

    tv = read_csv("prereview_time_varying_effects.csv")

    def tv_effect(operator: str, source: str) -> float:
        row = next(
            item
            for item in tv
            if item["operator"] == operator
            and item["exposure_source"] == source
            and item["model_variant"] == "time_varying_minimal"
        )
        return float(row["effect"])

    tv_expected = {
        ("original_strict", "order"): 2.011978,
        ("original_strict", "administration"): 2.156222,
        ("original_broad", "administration"): 1.342,
        ("hospital_overlap_strict", "order"): 1.765,
        ("hospital_overlap_broad", "administration"): 1.342,
    }
    tv_ok = all(close(tv_effect(*key), value, 3e-3) for key, value in tv_expected.items())
    check(
        "U08",
        "Corrected onset-at-zero time-varying effects reproduce the frozen table",
        len(tv) == 16 and all(row["converged"].upper() == "TRUE" for row in tv) and tv_ok,
        f"rows={len(tv)}; converged={sum(row['converged'].upper() == 'TRUE' for row in tv)}; headline_values={tv_ok}",
    )

    bootstrap = read_csv("prereview_paired_bootstrap_summary.csv")
    boot_index = {(row["anchor_id"], row["operator"], row["model_variant"], row["model_time"]): row for row in bootstrap}
    key_intervals = {
        ("A1", "original_strict", "published_style_minimal", "static"): (-0.004, 0.094),
        ("A1", "original_broad", "published_style_minimal", "static"): (-0.805, -0.642),
        ("A2", "original_strict", "published_style_minimal", "static"): (-0.058, 0.089),
        ("A2", "hospital_overlap_strict", "published_style_minimal", "static"): (0.072, 0.249),
        ("A2", "hospital_overlap_broad", "published_style_minimal", "static"): (-0.398, -0.217),
    }
    interval_ok = all(
        close(boot_index[key]["delta_ci_low"], interval[0], 2e-3)
        and close(boot_index[key]["delta_ci_high"], interval[1], 2e-3)
        for key, interval in key_intervals.items()
    )
    check(
        "U09",
        "All paired bootstrap comparisons passed and headline intervals reproduce",
        len(bootstrap) == 22
        and all(int(row["successful_pairs_n"]) == 1000 and int(row["failed_pairs_n"]) == 0 for row in bootstrap)
        and interval_ok,
        f"comparisons={len(bootstrap)}; all_success={all(int(row['successful_pairs_n']) == 1000 for row in bootstrap)}; intervals={interval_ok}",
    )

    concordant = read_csv("prereview_concordant_subset_effects.csv")
    check(
        "U10",
        "Every prespecified concordant-subset estimate remains above one",
        len(concordant) == 7 and all(float(row["effect"]) > 1 for row in concordant),
        "effects=" + ", ".join(f"{row['anchor_id']}:{row['operator']}={float(row['effect']):.3f}" for row in concordant),
    )

    dose = read_csv("emar_given_dose_route_availability_by_class.csv")
    check(
        "U11",
        "Dose-plus-unit is high while route availability remains source dependent",
        len(dose) == 6
        and min(float(row["dose_with_unit_available_pct"]) for row in dose) >= 94.5
        and min(float(row["route_available_pct"]) for row in dose) == 0
        and max(float(row["route_available_pct"]) for row in dose) < 42,
        f"dose+unit={min(float(row['dose_with_unit_available_pct']) for row in dose):.2f}–{max(float(row['dose_with_unit_available_pct']) for row in dose):.2f}%; route={min(float(row['route_available_pct']) for row in dose):.2f}–{max(float(row['route_available_pct']) for row in dose):.2f}%",
    )

    rx_summary = read_csv("rxnav_ndc_validation_summary.csv")[0]
    product = read_csv("emar_product_code_availability_by_class.csv")
    check(
        "U12",
        "RxNav validation meets 95%-represented-row target without overclaiming eMAR codes",
        int(rx_summary["queried_unique_ndcs_n"]) == 139
        and float(rx_summary["actual_row_coverage_pct"]) >= 95
        and close(rx_summary["api_mapped_rows_pct"], 100, 1e-6)
        and close(rx_summary["class_agreement_among_mapped_rows_pct"], 100, 1e-6)
        and close(rx_summary["ingredient_agreement_among_mapped_rows_pct"], 100, 1e-6)
        and all(int(row["ndc_like_product_code_events_n"]) == 0 for row in product),
        f"queried=139; row coverage={float(rx_summary['actual_row_coverage_pct']):.3f}%; mapped/class/ingredient=100%; eMAR NDC-like=0",
    )

    sample = read_csv("published_operator_landscape_sample.csv")
    reporting = {row["reporting_dimension"]: int(row["reported_n"]) for row in read_csv("published_operator_landscape_reporting_summary.csv")}
    source = {row["source_layer"]: int(row["n"]) for row in read_csv("published_operator_landscape_source_summary.csv")}
    expected_reporting = {
        "Named native medication table/source": 6,
        "Database-executable identity rule": 1,
        "Time origin and exposure window": 35,
        "Native event-state semantics": 0,
        "Dose or route constraint": 30,
        "Fully executable operator": 0,
    }
    check(
        "U13",
        "Structured published-operator sample and reporting totals reconcile",
        len(sample) == 40
        and reporting == expected_reporting
        and source == {"administration": 25, "order": 9, "hybrid": 4, "unspecified": 2}
        and retrieval.get("pubmed_query_count") == 379
        and retrieval.get("eligible_open_fulltext_pool_before_content_screen") == 293
        and landscape.get("last_screened_random_rank") == 149,
        f"sample=40; reporting={reporting}; source={source}; flow=379 to 293 to rank 149",
    )

    feasibility = read_csv("sepsis3_omop_local_input_feasibility.csv")
    check(
        "U14",
        "Sepsis-3 and OMOP extensions respect unavailable-input boundaries",
        len(feasibility) == 2
        and all(row["available"].lower() == "false" and row["decision"].startswith("not executed") for row in feasibility),
        "; ".join(f"{row['extension']}: {row['decision']}" for row in feasibility),
    )

    passed_n = sum(bool(row["passed"]) for row in checks)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": observed_sha,
        "checks_passed": passed_n,
        "checks_total": len(checks),
        "status": "PASS" if passed_n == len(checks) else "FAIL",
        "checks": checks,
    }
    output_json = MANIFESTS / "33_prereview_upgrade_validation.json"
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    output_csv = TABLES / "prereview_upgrade_validation_checks.csv"
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check_id", "description", "passed", "evidence"])
        writer.writeheader()
        writer.writerows(checks)

    print(f"PREREVIEW_UPGRADE_QA={passed_n}/{len(checks)}")
    print(f"REPORT={output_json}")
    return 0 if passed_n == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
