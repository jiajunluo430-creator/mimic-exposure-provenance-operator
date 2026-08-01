from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
BASE_DB = PROJECT / "cache" / "n1_validity.duckdb"
PRIOR_DB = PROJECT / "cache" / "jamia_prereview_upgrade_v1_0.duckdb"
SCRATCH_DB = PROJECT / "cache" / "jamia_residual_provenance_v1_0.duckdb"
OUTPUT = PROJECT / "outputs" / "jamia_residual_provenance_v1_0"
TABLES = OUTPUT / "tables"
LOGS = OUTPUT / "logs"
PLANS = OUTPUT / "plans"
MANIFESTS = OUTPUT / "manifests"
ENVIRONMENT = PROJECT / "environment"
CONTRACT = (
    PROJECT
    / "contracts"
    / "jamia_residual_provenance_addendum_v1.0_2026-07-31.md"
)
EXPECTED_CONTRACT_SHA256 = (
    "af533e4d3a9b636c368dc6c76cc3e3ea472c77f9884476520d341ae09575dcfd"
)

for directory in (TABLES, LOGS, PLANS, MANIFESTS, ENVIRONMENT):
    directory.mkdir(parents=True, exist_ok=True)

LOG_PATH = LOGS / "35_build_residual_prescription_eligibility_audit.log"


def log(message: str) -> None:
    line = f"{datetime.now().astimezone().isoformat()}\t{message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def save_plan(con: duckdb.DuckDBPyConnection, name: str, query: str) -> None:
    plan = "\n".join(str(row[-1]) for row in con.execute("EXPLAIN " + query).fetchall())
    (PLANS / f"{name}.txt").write_text(plan, encoding="utf-8")
    upper = plan.upper()
    if "CROSS_PRODUCT" in upper or "BLOCKWISE_NL_JOIN" in upper:
        raise RuntimeError(f"Unsafe join operator in {name}:\n{plan}")
    log(f"PLAN {name} equality_join_gate=PASS")


def export_query(
    con: duckdb.DuckDBPyConnection, query: str, filename: str
) -> pd.DataFrame:
    frame = con.execute(query).fetchdf()
    path = TABLES / filename
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    log(f"CHECKPOINT file={filename} rows={len(frame)}")
    return frame


def main() -> None:
    started = time.time()
    if sha256(CONTRACT) != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError("Residual-provenance contract hash mismatch")
    for database in (BASE_DB, PRIOR_DB, SCRATCH_DB):
        if not database.exists():
            raise FileNotFoundError(database)

    con = duckdb.connect(str(SCRATCH_DB))
    con.execute("SET threads=4")
    try:
        con.execute(f"ATTACH '{sql_path(BASE_DB)}' AS base (READ_ONLY)")
        con.execute(f"ATTACH '{sql_path(PRIOR_DB)}' AS prior (READ_ONLY)")

        query = """
            SELECT DISTINCT e.subject_id, e.hadm_id, e.stay_id,
                   e.emar_id, e.emar_seq, e.charttime AS emar_charttime,
                   e.poe_id AS emar_poe_id, e.pharmacy_id,
                   p.prescription_row_id, p.poe_id AS prescription_poe_id,
                   p.starttime, p.stoptime, p.drug, p.route,
                   i.first_ordertime,
                   nullif(trim(p.poe_id), '') IS NOT NULL
                     AS poe_nonmissing,
                   i.poe_id IS NOT NULL
                     AND i.subject_id = e.subject_id
                     AND i.hadm_id = e.hadm_id AS poe_identity_same_admission,
                   nullif(trim(p.poe_id), '') = nullif(trim(e.poe_id), '')
                     AS prescription_poe_matches_emar,
                   p.starttime IS NOT NULL
                     AND p.starttime <= s.intime + INTERVAL 48 HOUR
                     AS start_not_after_48h,
                   coalesce(p.stoptime, s.outtime) >= s.intime
                     AS stop_overlaps_icu_entry,
                   coalesce(i.first_ordertime, p.starttime) IS NOT NULL
                     AND coalesce(i.first_ordertime, p.starttime)
                         <= s.intime + INTERVAL 48 HOUR
                     AS order_not_after_48h,
                   (
                     nullif(trim(p.poe_id), '') IS NOT NULL
                     AND i.poe_id IS NOT NULL
                     AND i.subject_id = e.subject_id
                     AND i.hadm_id = e.hadm_id
                     AND p.starttime IS NOT NULL
                     AND p.starttime <= s.intime + INTERVAL 48 HOUR
                     AND coalesce(p.stoptime, s.outtime) >= s.intime
                     AND coalesce(i.first_ordertime, p.starttime) IS NOT NULL
                     AND coalesce(i.first_ordertime, p.starttime)
                         <= s.intime + INTERVAL 48 HOUR
                   ) AS meets_hospital_overlap_eligibility
            FROM a2_residual_emar_events e
            JOIN a2_residual_stays s
              ON e.subject_id = s.subject_id
             AND e.hadm_id = s.hadm_id
             AND e.stay_id = s.stay_id
            JOIN base.prescription_candidates p
              ON e.subject_id = p.subject_id
             AND e.hadm_id = p.hadm_id
             AND e.pharmacy_id = p.pharmacy_id
            LEFT JOIN base.poe_identity i
              ON p.poe_id = i.poe_id
            WHERE nullif(trim(e.pharmacy_id), '') IS NOT NULL
              AND p.drug_class = 'stress_ulcer_prophylaxis'
              AND p.subclass = 'PPI'
        """
        save_plan(con, "a2_residual_prescription_eligibility_explain", query)
        pilot_query = query.replace(
            "FROM a2_residual_emar_events e",
            "FROM (SELECT * FROM a2_residual_emar_events "
            "ORDER BY stay_id, charttime LIMIT 20) e",
            1,
        )
        con.execute("CREATE OR REPLACE TEMP TABLE eligibility_pilot AS " + pilot_query)
        pilot_rows, pilot_units = con.execute(
            "SELECT count(*), count(DISTINCT (stay_id, prescription_row_id)) "
            "FROM eligibility_pilot"
        ).fetchone()
        if int(pilot_rows) > 2000:
            raise RuntimeError(f"Pilot multiplicity unsafe: rows={pilot_rows}")
        log(f"PILOT rows={pilot_rows} unique_prescription_units={pilot_units}")

        con.execute(
            "CREATE OR REPLACE TABLE a2_residual_linked_prescription_rows AS "
            + query
        )
        row_n, unit_n, stay_n = con.execute(
            """
            SELECT count(*),
                   count(DISTINCT (stay_id, prescription_row_id)),
                   count(DISTINCT stay_id)
            FROM a2_residual_linked_prescription_rows
            """
        ).fetchone()
        if int(stay_n) != 183:
            raise RuntimeError(f"Expected 183 linked stays, observed {stay_n}")
        log(
            "MATERIALIZED linked_rows="
            f"{row_n} unique_stay_prescription_units={unit_n} stays={stay_n}"
        )

        criteria = export_query(
            con,
            """
            WITH units AS (
              SELECT DISTINCT stay_id, prescription_row_id,
                     poe_nonmissing, poe_identity_same_admission,
                     prescription_poe_matches_emar,
                     start_not_after_48h, stop_overlaps_icu_entry,
                     order_not_after_48h, meets_hospital_overlap_eligibility
              FROM a2_residual_linked_prescription_rows
            ), long AS (
              SELECT stay_id, prescription_row_id,
                     unnest([
                       'POE nonmissing',
                       'POE identity resolves to same admission',
                       'prescription POE matches eMAR POE',
                       'prescription start at or before ICU+48h',
                       'prescription stop overlaps ICU entry',
                       'POE order/start at or before ICU+48h',
                       'all hospital-overlap eligibility criteria'
                     ]) AS criterion,
                     unnest([
                       poe_nonmissing,
                       poe_identity_same_admission,
                       prescription_poe_matches_emar,
                       start_not_after_48h,
                       stop_overlaps_icu_entry,
                       order_not_after_48h,
                       meets_hospital_overlap_eligibility
                     ]) AS criterion_met
              FROM units
            )
            SELECT criterion,
                   count(*) AS prescription_units_n,
                   count(*) FILTER (WHERE criterion_met) AS units_meeting_n,
                   round(100.0 * count(*) FILTER (WHERE criterion_met)
                         / count(*), 4) AS units_meeting_pct,
                   count(DISTINCT stay_id) AS linked_stays_n,
                   count(DISTINCT stay_id) FILTER (WHERE criterion_met)
                     AS stays_with_any_meeting_n,
                   round(100.0 * count(DISTINCT stay_id)
                         FILTER (WHERE criterion_met)
                         / count(DISTINCT stay_id), 4)
                     AS stays_with_any_meeting_pct
            FROM long
            GROUP BY criterion
            ORDER BY CASE criterion
              WHEN 'POE nonmissing' THEN 1
              WHEN 'POE identity resolves to same admission' THEN 2
              WHEN 'prescription POE matches eMAR POE' THEN 3
              WHEN 'prescription start at or before ICU+48h' THEN 4
              WHEN 'prescription stop overlaps ICU entry' THEN 5
              WHEN 'POE order/start at or before ICU+48h' THEN 6
              ELSE 7 END
            """,
            "a2_residual_prescription_eligibility_criteria.csv",
        )

        signatures = export_query(
            con,
            """
            WITH units AS (
              SELECT DISTINCT stay_id, prescription_row_id,
                     poe_nonmissing, poe_identity_same_admission,
                     prescription_poe_matches_emar,
                     start_not_after_48h, stop_overlaps_icu_entry,
                     order_not_after_48h, meets_hospital_overlap_eligibility
              FROM a2_residual_linked_prescription_rows
            ), labeled AS (
              SELECT *, concat_ws('; ',
                CASE WHEN NOT poe_nonmissing THEN 'missing POE' END,
                CASE WHEN NOT coalesce(poe_identity_same_admission, false)
                  THEN 'POE identity not same admission' END,
                CASE WHEN NOT coalesce(prescription_poe_matches_emar, false)
                  THEN 'prescription/eMAR POE mismatch' END,
                CASE WHEN NOT coalesce(start_not_after_48h, false)
                  THEN 'start missing or after ICU+48h' END,
                CASE WHEN NOT coalesce(stop_overlaps_icu_entry, false)
                  THEN 'prescription stopped before ICU entry' END,
                CASE WHEN NOT coalesce(order_not_after_48h, false)
                  THEN 'order/start missing or after ICU+48h' END
              ) AS failed_criteria
              FROM units
            )
            SELECT failed_criteria,
                   count(*) AS prescription_units_n,
                   count(DISTINCT stay_id) AS patients_n
            FROM labeled
            GROUP BY failed_criteria
            ORDER BY patients_n DESC, prescription_units_n DESC,
                     failed_criteria
            """,
            "a2_residual_prescription_failure_signatures.csv",
        )

        timing = export_query(
            con,
            """
            WITH units AS (
              SELECT stay_id, prescription_row_id,
                     min(emar_charttime) AS first_linked_emar_charttime,
                     min(starttime) AS starttime,
                     max(stoptime) AS stoptime,
                     min(first_ordertime) AS first_ordertime,
                     bool_or(prescription_poe_matches_emar)
                       AS prescription_poe_matches_emar
              FROM a2_residual_linked_prescription_rows
              GROUP BY stay_id, prescription_row_id
            ), s AS (
              SELECT u.*, r.intime,
                     date_diff('minute', r.intime, u.starttime) / 60.0
                       AS start_from_icu_hours,
                     date_diff('minute', r.intime,
                       coalesce(u.first_ordertime, u.starttime)) / 60.0
                       AS order_from_icu_hours,
                     date_diff('minute', r.intime,
                       u.first_linked_emar_charttime) / 60.0
                       AS admin_from_icu_hours,
                     date_diff('minute', u.first_linked_emar_charttime,
                       u.starttime) / 60.0
                       AS start_minus_admin_hours,
                     date_diff('minute', u.first_linked_emar_charttime,
                       coalesce(u.first_ordertime, u.starttime)) / 60.0
                       AS order_minus_admin_hours
              FROM units u JOIN a2_residual_stays r USING (stay_id)
            )
            SELECT count(*) AS prescription_units_n,
                   median(start_from_icu_hours) AS start_from_icu_median_h,
                   quantile_cont(start_from_icu_hours, 0.25)
                     AS start_from_icu_q1_h,
                   quantile_cont(start_from_icu_hours, 0.75)
                     AS start_from_icu_q3_h,
                   median(order_from_icu_hours) AS order_from_icu_median_h,
                   quantile_cont(order_from_icu_hours, 0.25)
                     AS order_from_icu_q1_h,
                   quantile_cont(order_from_icu_hours, 0.75)
                     AS order_from_icu_q3_h,
                   median(admin_from_icu_hours) AS admin_from_icu_median_h,
                   median(start_minus_admin_hours) AS start_minus_admin_median_h,
                   median(order_minus_admin_hours) AS order_minus_admin_median_h
            FROM s
            """,
            "a2_residual_prescription_timing_summary.csv",
        )

        temporal_alignment = export_query(
            con,
            """
            WITH units AS (
              SELECT stay_id, prescription_row_id,
                     min(emar_charttime) AS first_linked_emar_charttime,
                     min(starttime) AS starttime,
                     min(first_ordertime) AS first_ordertime,
                     bool_or(prescription_poe_matches_emar)
                       AS prescription_poe_matches_emar
              FROM a2_residual_linked_prescription_rows
              GROUP BY stay_id, prescription_row_id
            )
            SELECT count(*) AS prescription_units_n,
                   count(DISTINCT stay_id) AS patients_n,
                   count(*) FILTER (WHERE prescription_poe_matches_emar)
                     AS poe_matches_emar_n,
                   count(*) FILTER (
                     WHERE starttime <= first_linked_emar_charttime
                   ) AS prescription_started_by_first_admin_n,
                   count(*) FILTER (
                     WHERE first_ordertime <= first_linked_emar_charttime
                   ) AS poe_ordered_by_first_admin_n,
                   count(*) FILTER (
                     WHERE first_ordertime > first_linked_emar_charttime
                   ) AS poe_ordered_after_first_admin_n,
                   round(100.0 * count(*) FILTER (
                     WHERE first_ordertime > first_linked_emar_charttime
                   ) / count(*), 4) AS poe_ordered_after_first_admin_pct
            FROM units
            """,
            "a2_residual_identity_time_alignment.csv",
        )

        top_drugs = export_query(
            con,
            """
            WITH units AS (
              SELECT DISTINCT stay_id, prescription_row_id, drug, route
              FROM a2_residual_linked_prescription_rows
            )
            SELECT drug, route, count(*) AS prescription_units_n,
                   count(DISTINCT stay_id) AS patients_n
            FROM units
            GROUP BY drug, route
            ORDER BY patients_n DESC, prescription_units_n DESC, drug, route
            LIMIT 20
            """,
            "a2_residual_prescription_drug_route_top20.csv",
        )

        all_eligible = int(
            con.execute(
                "SELECT count(*) FROM a2_residual_linked_prescription_rows "
                "WHERE meets_hospital_overlap_eligibility"
            ).fetchone()[0]
        )
        if all_eligible != 0:
            raise RuntimeError(
                "Residual eligibility audit contradicted frozen provenance: "
                f"eligible rows={all_eligible}"
            )

        manifest = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "script": Path(__file__).name,
            "script_sha256": sha256(Path(__file__)),
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "linked_rows_n": int(row_n),
            "linked_unique_stay_prescription_units_n": int(unit_n),
            "linked_stays_n": int(stay_n),
            "eligible_linked_rows_n": all_eligible,
            "criteria_rows_n": len(criteria),
            "failure_signature_rows_n": len(signatures),
            "timing_rows_n": len(timing),
            "temporal_alignment_rows_n": len(temporal_alignment),
            "top_drug_route_rows_n": len(top_drugs),
            "elapsed_seconds": time.time() - started,
        }
        (MANIFESTS / "35_residual_eligibility_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        (ENVIRONMENT / "sessionInfo_residual_eligibility.txt").write_text(
            "\n".join(
                [
                    f"timestamp={manifest['generated_at']}",
                    f"python={sys.version}",
                    f"platform={platform.platform()}",
                    f"duckdb={duckdb.__version__}",
                    f"pandas={pd.__version__}",
                    f"script={Path(__file__).name}",
                    f"script_sha256={manifest['script_sha256']}",
                    f"contract_sha256={EXPECTED_CONTRACT_SHA256}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        log("PASS residual prescription eligibility audit complete")
        print(json.dumps(manifest, indent=2), flush=True)
    finally:
        con.close()


if __name__ == "__main__":
    main()
