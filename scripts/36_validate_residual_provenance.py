from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
SCRATCH_DB = PROJECT / "cache" / "jamia_residual_provenance_v1_0.duckdb"
OUTPUT = PROJECT / "outputs" / "jamia_residual_provenance_v1_0"
TABLES = OUTPUT / "tables"
PLANS = OUTPUT / "plans"
QA = OUTPUT / "qa"
ENVIRONMENT = PROJECT / "environment"
CONTRACT = (
    PROJECT
    / "contracts"
    / "jamia_residual_provenance_addendum_v1.0_2026-07-31.md"
)
EXPECTED_CONTRACT_SHA256 = (
    "af533e4d3a9b636c368dc6c76cc3e3ea472c77f9884476520d341ae09575dcfd"
)

QA.mkdir(parents=True, exist_ok=True)
ENVIRONMENT.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frame(filename: str) -> pd.DataFrame:
    return pd.read_csv(TABLES / filename)


def main() -> None:
    checks: list[dict[str, str]] = []

    def check(check_id: str, passed: bool, evidence: str) -> None:
        checks.append(
            {
                "check_id": check_id,
                "status": "PASS" if passed else "FAIL",
                "evidence": evidence,
            }
        )

    observed_hash = sha256(CONTRACT)
    check(
        "contract_hash",
        observed_hash == EXPECTED_CONTRACT_SHA256,
        f"observed={observed_hash}; expected={EXPECTED_CONTRACT_SHA256}",
    )

    required = [
        "a2_residual_event_link_path_summary.csv",
        "a2_residual_patient_trace_summary.csv",
        "a2_residual_emar_medication_top10.csv",
        "a2_residual_product_description_top10.csv",
        "a2_residual_prescription_eligibility_criteria.csv",
        "a2_residual_prescription_failure_signatures.csv",
        "a2_residual_prescription_timing_summary.csv",
        "a2_residual_identity_time_alignment.csv",
        "a2_residual_prescription_drug_route_top20.csv",
        "a1_order_vs_emar_route_availability.csv",
        "a1_order_route_values.csv",
    ]
    missing = [name for name in required if not (TABLES / name).exists()]
    check("required_outputs", not missing, f"missing={missing}")

    patient = frame("a2_residual_patient_trace_summary.csv")
    patient_map = dict(zip(patient["trace_category"], patient["patients_n"]))
    check(
        "a2_patient_trace_partition",
        int(patient["patients_n"].sum()) == 184
        and int(patient_map.get("direct_pharmacy_id_to_ppi_prescription", 0)) == 183
        and int(
            patient_map.get(
                "no_resolved_pharmacy_record_or_ppi_prescription", 0
            )
        )
        == 1,
        f"partition={patient_map}",
    )

    paths = frame("a2_residual_event_link_path_summary.csv")
    path_map = dict(zip(paths["link_path"], paths["linked_events_n"]))
    check(
        "a2_event_native_linkage",
        int(path_map.get("any_ppi_prescription_in_admission", 0)) == 398
        and int(path_map.get("ppi_pharmacy_id_link", 0)) == 396
        and int(path_map.get("ppi_prescription_by_pharmacy_id", 0)) == 396,
        f"linked_events={path_map}; denominator=399",
    )

    meds = frame("a2_residual_emar_medication_top10.csv")
    med_names = set(meds["emar_medication"].astype(str))
    expected_meds = {
        "Pantoprazole",
        "Omeprazole",
        "Lansoprazole Oral Disintegrating Tab",
        "Pantoprazole (Granules for DR Suspension)",
    }
    check(
        "a2_medication_string_specificity",
        int(meds["events_n"].sum()) == 399
        and med_names == expected_meds
        and abs(float(meds["events_pct"].sum()) - 100.0) < 1e-6,
        f"events={int(meds['events_n'].sum())}; strings={sorted(med_names)}",
    )

    criteria = frame("a2_residual_prescription_eligibility_criteria.csv")
    criterion_units = dict(zip(criteria["criterion"], criteria["units_meeting_n"]))
    criterion_stays = dict(
        zip(criteria["criterion"], criteria["stays_with_any_meeting_n"])
    )
    check(
        "a2_linked_prescription_identity",
        int(criterion_units.get("POE nonmissing", -1)) == 256
        and int(
            criterion_units.get("POE identity resolves to same admission", -1)
        )
        == 256
        and int(criterion_stays.get("POE nonmissing", -1)) == 183,
        f"units={criterion_units}; stays={criterion_stays}",
    )
    check(
        "a2_frozen_hospital_eligibility_preserved",
        int(
            criterion_units.get(
                "all hospital-overlap eligibility criteria", -1
            )
        )
        == 0,
        "0/256 directly linked prescription units meet all frozen criteria",
    )

    alignment = frame("a2_residual_identity_time_alignment.csv").iloc[0]
    check(
        "a2_identity_time_discordance",
        int(alignment["prescription_units_n"]) == 256
        and int(alignment["patients_n"]) == 183
        and int(alignment["poe_matches_emar_n"]) == 0
        and int(alignment["poe_ordered_after_first_admin_n"]) == 256,
        "256/256 prescription POEs differ from eMAR POE and have first POE "
        "ordertime after first linked administration",
    )

    route = frame("a1_order_vs_emar_route_availability.csv")
    order = route.loc[route["source_layer"].eq("eligible order unit")].iloc[0]
    emar = route.loc[
        route["source_layer"].eq("strict eMAR administration")
    ].iloc[0]
    check(
        "a1_route_layer_asymmetry",
        int(order["records_n"]) == 9940
        and float(order["route_available_pct"]) == 100.0
        and int(emar["records_n"]) == 87569
        and float(emar["route_available_pct"]) == 0.0,
        "order route 9940/9940; strict eMAR route 0/87569",
    )

    unsafe_plans = []
    for path in sorted(PLANS.glob("*.txt")):
        upper = path.read_text(encoding="utf-8").upper()
        if "CROSS_PRODUCT" in upper or "BLOCKWISE_NL_JOIN" in upper:
            unsafe_plans.append(path.name)
    check(
        "query_plan_join_safety",
        not unsafe_plans,
        f"unsafe_plans={unsafe_plans}; plans_checked={len(list(PLANS.glob('*.txt')))}",
    )

    con = duckdb.connect(str(SCRATCH_DB), read_only=True)
    try:
        table_counts = dict(con.execute("SELECT table_name, estimated_size FROM duckdb_tables()").fetchall())
    finally:
        con.close()
    check(
        "scratch_cardinality",
        int(table_counts.get("a2_residual_stays", -1)) == 184
        and int(table_counts.get("a2_residual_emar_events", -1)) == 399
        and int(table_counts.get("a2_residual_linked_prescription_rows", -1))
        == 571,
        f"selected_table_counts={table_counts}",
    )

    qa = pd.DataFrame(checks)
    qa.to_csv(QA / "residual_provenance_validation.csv", index=False, encoding="utf-8-sig")
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "script": Path(__file__).name,
        "script_sha256": sha256(Path(__file__)),
        "checks_n": len(qa),
        "pass_n": int(qa["status"].eq("PASS").sum()),
        "fail_n": int(qa["status"].eq("FAIL").sum()),
        "status": "PASS" if qa["status"].eq("PASS").all() else "FAIL",
    }
    (QA / "residual_provenance_validation.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (ENVIRONMENT / "sessionInfo_residual_validation.txt").write_text(
        "\n".join(
            [
                f"timestamp={summary['generated_at']}",
                f"python={sys.version}",
                f"platform={platform.platform()}",
                f"duckdb={duckdb.__version__}",
                f"pandas={pd.__version__}",
                f"script={Path(__file__).name}",
                f"script_sha256={summary['script_sha256']}",
                f"contract_sha256={EXPECTED_CONTRACT_SHA256}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(qa.to_string(index=False), flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    if summary["status"] != "PASS":
        raise RuntimeError("Residual provenance validation failed")


if __name__ == "__main__":
    main()
