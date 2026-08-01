from __future__ import annotations

import hashlib
import os
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
SCRATCH_DB = PROJECT / "cache" / "jamia_prereview_upgrade_v1_0.duckdb"
TMP = PROJECT / "cache" / "jamia_prereview_upgrade_tmp"
OUTPUT = PROJECT / "outputs" / "jamia_prereview_upgrade_v1_0"
TABLES = OUTPUT / "tables"
MODEL_INPUTS = OUTPUT / "model_inputs"
LOGS = OUTPUT / "logs"
PLANS = OUTPUT / "plans"
MANIFESTS = OUTPUT / "manifests"
ENVIRONMENT = PROJECT / "environment"
MIMIC = Path(os.environ["MIMIC_IV_ROOT"])
PRE = PROJECT / "outputs" / "jamia_pre_submission_v1_0"
A1_CSV = PRE / "model_inputs" / "anchor_a1_operator_post.csv"
A2_CSV = PRE / "model_inputs" / "anchor_a2_operator_post.csv"
CONTRACT = (
    PROJECT
    / "contracts"
    / "jamia_prereview_upgrade_addendum_v1.0_2026-07-31.md"
)
EXPECTED_CONTRACT_SHA256 = (
    "0a851a99c9176c16deda2cde9e30fded7f2b5131a5a3f64ac7f050ebd8f81d9d"
)
STARTED = time.time()

PRESCRIPTION_COLUMNS = [
    "subject_id",
    "hadm_id",
    "pharmacy_id",
    "poe_id",
    "poe_seq",
    "order_provider_id",
    "starttime",
    "stoptime",
    "drug_type",
    "drug",
    "formulary_drug_cd",
    "gsn",
    "ndc",
    "prod_strength",
    "form_rx",
    "dose_val_rx",
    "dose_unit_rx",
    "form_val_disp",
    "form_unit_disp",
    "doses_per_24_hrs",
    "route",
]


for directory in (TMP, TABLES, MODEL_INPUTS, LOGS, PLANS, MANIFESTS, ENVIRONMENT):
    directory.mkdir(parents=True, exist_ok=True)

LOG_PATH = LOGS / "28_build_prereview_upgrade_analytics.log"


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


def explicit_csv(path: Path, columns: list[str]) -> str:
    mapping = ", ".join(f"'{column}':'VARCHAR'" for column in columns)
    return (
        f"read_csv('{sql_path(path)}', header=true, compression='gzip', "
        f"columns={{{mapping}}}, strict_mode=true, ignore_errors=false, "
        "null_padding=false, quote='\"', escape='\"')"
    )


def run_step(
    con: duckdb.DuckDBPyConnection,
    name: str,
    sql: str,
    table: str | None = None,
) -> float:
    started = time.time()
    log(f"START {name}")
    con.execute(sql)
    elapsed = time.time() - started
    rows = None
    if table:
        rows = int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    log(f"DONE {name} rows={rows} elapsed_seconds={elapsed:.3f}")
    return elapsed


def save_plan(con: duckdb.DuckDBPyConnection, name: str, query: str) -> None:
    plan = "\n".join(str(row[-1]) for row in con.execute("EXPLAIN " + query).fetchall())
    (PLANS / f"{name}.txt").write_text(plan, encoding="utf-8")
    upper = plan.upper()
    if "CROSS_PRODUCT" in upper or "BLOCKWISE_NL_JOIN" in upper:
        raise RuntimeError(f"Unsafe join operator in {name}:\n{plan}")
    log(f"PLAN {name} equality_join_gate=PASS")


def export_query(
    con: duckdb.DuckDBPyConnection, query: str, path: Path
) -> pd.DataFrame:
    frame = con.execute(query).fetchdf()
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    log(f"CHECKPOINT file={path.name} rows={len(frame)}")
    return frame


def main() -> None:
    observed_contract_hash = sha256(CONTRACT)
    if observed_contract_hash != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError(
            "Prereview-upgrade contract hash mismatch: "
            f"{observed_contract_hash}"
        )
    if not BASE_DB.exists():
        raise FileNotFoundError(BASE_DB)
    for source in (A1_CSV, A2_CSV):
        if not source.exists():
            raise FileNotFoundError(source)
    log("PASS prereview-upgrade contract hash")

    raw_source = MIMIC / "hosp" / "prescriptions.csv.gz"
    raw_before = {
        "path": str(raw_source),
        "size": raw_source.stat().st_size,
        "mtime_ns": raw_source.stat().st_mtime_ns,
    }

    con = duckdb.connect(str(SCRATCH_DB))
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{sql_path(TMP)}'")
    try:
        con.execute(f"ATTACH '{sql_path(BASE_DB)}' AS base (READ_ONLY)")
        run_step(
            con,
            "load frozen anchor model inputs",
            f"""
            CREATE OR REPLACE TABLE a1_post AS
              SELECT * FROM read_csv_auto(
                '{sql_path(A1_CSV)}', header=true, sample_size=-1,
                strict_mode=true, ignore_errors=false
              );
            CREATE OR REPLACE TABLE a2_post AS
              SELECT * FROM read_csv_auto(
                '{sql_path(A2_CSV)}', header=true, sample_size=-1,
                strict_mode=true, ignore_errors=false
              )
            """,
        )
        a1_n = int(con.execute("SELECT count(*) FROM a1_post").fetchone()[0])
        a2_n = int(con.execute("SELECT count(*) FROM a2_post").fetchone()[0])
        if (a1_n, a2_n) != (20_248, 2_813):
            raise RuntimeError(f"Anchor row gate failed: A1={a1_n}, A2={a2_n}")

        a2_candidate_query = """
            SELECT a.subject_id, a.hadm_id, a.stay_id, a.intime, a.outtime,
                   p.poe_id, p.starttime, p.stoptime, p.drug,
                   p.ingredient, p.subclass, p.prescription_row_id,
                   i.first_ordertime
            FROM a2_post a
            JOIN base.prescription_candidates p
              ON a.subject_id = p.subject_id AND a.hadm_id = p.hadm_id
            JOIN base.poe_identity i
              ON p.poe_id = i.poe_id
             AND p.subject_id = i.subject_id
             AND p.hadm_id = i.hadm_id
            WHERE p.drug_class = 'stress_ulcer_prophylaxis'
              AND p.subclass = 'PPI'
              AND nullif(trim(p.poe_id), '') IS NOT NULL
              AND p.starttime <= a.intime + INTERVAL 48 HOUR
              AND coalesce(p.stoptime, a.outtime) >= a.intime
              AND coalesce(i.first_ordertime, p.starttime)
                    <= a.intime + INTERVAL 48 HOUR
        """
        save_plan(con, "a2_hospital_overlap_candidate_explain", a2_candidate_query)
        a2_candidate_pilot = a2_candidate_query.replace(
            "FROM a2_post a",
            "FROM (SELECT * FROM a2_post ORDER BY stay_id LIMIT 100) a",
            1,
        )
        run_step(
            con,
            "limited 100-stay A2 hospital-overlap pilot",
            "CREATE OR REPLACE TEMP TABLE a2_candidate_pilot AS "
            + a2_candidate_pilot,
            "a2_candidate_pilot",
        )
        a2_pilot_max = int(
            con.execute(
                """
                SELECT coalesce(max(rows_n), 0) FROM (
                  SELECT stay_id, count(*) AS rows_n
                  FROM a2_candidate_pilot GROUP BY stay_id
                )
                """
            ).fetchone()[0]
        )
        if a2_pilot_max > 1000:
            raise RuntimeError(
                f"A2 candidate pilot multiplicity unsafe: max={a2_pilot_max}"
            )
        run_step(
            con,
            "materialize A2 hospital-overlap PPI candidate rows",
            "CREATE OR REPLACE TABLE a2_hospital_candidate_rows AS "
            + a2_candidate_query,
            "a2_hospital_candidate_rows",
        )
        run_step(
            con,
            "deduplicate A2 hospital-overlap PPI order units",
            """
            CREATE OR REPLACE TABLE a2_hospital_order_units AS
            SELECT subject_id, hadm_id, stay_id, poe_id,
                   min(starttime) AS prescription_starttime,
                   max(stoptime) AS prescription_stoptime,
                   min(first_ordertime) AS first_ordertime,
                   count(*) AS prescription_rows_n,
                   min(CASE
                     WHEN coalesce(first_ordertime, starttime) <= intime
                       THEN intime
                     ELSE coalesce(first_ordertime, starttime)
                   END) AS hospital_order_onset
            FROM a2_hospital_candidate_rows
            GROUP BY subject_id, hadm_id, stay_id, poe_id
            """,
            "a2_hospital_order_units",
        )
        hospital_rows, hospital_unique = con.execute(
            """
            SELECT count(*), count(DISTINCT (stay_id, poe_id))
            FROM a2_hospital_order_units
            """
        ).fetchone()
        if int(hospital_rows) != int(hospital_unique):
            raise RuntimeError("A2 hospital order unit multiplicity gate failed")

        a2_event_query = """
            SELECT e.subject_id, e.hadm_id, e.stay_id, e.poe_id,
                   min(e.charttime) AS first_strict_ppi_administration,
                   count(*) AS strict_given_events_n
            FROM base.emar_stay_events e
            JOIN a2_post a USING (stay_id)
            WHERE e.drug_class = 'stress_ulcer_prophylaxis'
              AND e.subclass = 'PPI'
              AND e.event_category = 'given_strict'
              AND e.poe_id_identity_link
              AND e.charttime BETWEEN a.intime
                                  AND least(a.outtime,
                                            a.intime + INTERVAL 48 HOUR)
            GROUP BY e.subject_id, e.hadm_id, e.stay_id, e.poe_id
        """
        save_plan(con, "a2_ppi_events_by_poe_explain", a2_event_query)
        run_step(
            con,
            "preaggregate A2 PPI administrations by POE",
            "CREATE OR REPLACE TABLE a2_ppi_events_by_poe AS " + a2_event_query,
            "a2_ppi_events_by_poe",
        )
        run_step(
            con,
            "link hospital-overlap A2 order units to strict administrations",
            """
            CREATE OR REPLACE TABLE a2_hospital_strict AS
            SELECT o.stay_id,
                   min(e.first_strict_ppi_administration)
                     AS hospital_strict_admin_onset,
                   count(DISTINCT o.poe_id) AS linked_order_units_n
            FROM a2_hospital_order_units o
            JOIN a2_ppi_events_by_poe e
              ON o.subject_id = e.subject_id
             AND o.hadm_id = e.hadm_id
             AND o.stay_id = e.stay_id
             AND o.poe_id = e.poe_id
            GROUP BY o.stay_id
            """,
            "a2_hospital_strict",
        )
        run_step(
            con,
            "assemble upgraded A2 model input",
            """
            CREATE OR REPLACE TABLE a2_upgrade_input AS
            WITH hospital_order AS (
              SELECT stay_id, min(hospital_order_onset) AS hospital_order_onset,
                     count(*) AS hospital_order_units_n
              FROM a2_hospital_order_units GROUP BY stay_id
            )
            SELECT a.*,
                   (o.stay_id IS NOT NULL)::INTEGER
                     AS hospital_order_exposure,
                   (s.stay_id IS NOT NULL)::INTEGER
                     AS hospital_admin_strict,
                   CASE WHEN o.hospital_order_onset IS NULL THEN NULL ELSE
                     greatest(0.0, date_diff('second', a.intime,
                       o.hospital_order_onset) / 3600.0) END
                     AS hospital_order_onset_hours,
                   CASE WHEN s.hospital_strict_admin_onset IS NULL THEN NULL ELSE
                     greatest(0.0, date_diff('second', a.intime,
                       s.hospital_strict_admin_onset) / 3600.0) END
                     AS hospital_strict_admin_onset_hours,
                   coalesce(o.hospital_order_units_n, 0)::BIGINT
                     AS hospital_order_units_n
            FROM a2_post a
            LEFT JOIN hospital_order o USING (stay_id)
            LEFT JOIN a2_hospital_strict s USING (stay_id)
            """,
            "a2_upgrade_input",
        )
        a2_upgrade_n = int(
            con.execute("SELECT count(*) FROM a2_upgrade_input").fetchone()[0]
        )
        if a2_upgrade_n != a2_n:
            raise RuntimeError("A2 upgraded input changed cohort membership")

        run_step(
            con,
            "trace A2 broad administration-only provenance by hospital window",
            """
            CREATE OR REPLACE TABLE a2_first_broad_event AS
            SELECT * EXCLUDE (rn) FROM (
              SELECT e.*, row_number() OVER (
                PARTITION BY e.stay_id
                ORDER BY e.charttime, e.emar_id, e.emar_seq
              ) AS rn
              FROM base.emar_stay_events e
              JOIN a2_upgrade_input a USING (stay_id)
              WHERE a.order_exposure = 0 AND a.admin_broad = 1
                AND e.drug_class = 'stress_ulcer_prophylaxis'
                AND e.subclass = 'PPI'
                AND e.event_category = 'given_strict'
                AND e.charttime BETWEEN a.intime
                                    AND least(a.outtime,
                                              a.intime + INTERVAL 48 HOUR)
            ) WHERE rn = 1;

            CREATE OR REPLACE TABLE a2_window_provenance AS
            WITH any_hospital AS (
              SELECT stay_id, count(*) AS order_units_n
              FROM a2_hospital_order_units GROUP BY stay_id
            ), same_poe AS (
              SELECT stay_id, poe_id, count(*) AS order_units_n
              FROM a2_hospital_order_units GROUP BY stay_id, poe_id
            )
            SELECT a.subject_id, a.hadm_id, a.stay_id, a.outcome,
                   e.emar_id, e.poe_id, e.charttime,
                   e.poe_id_identity_link,
                   coalesce(s.order_units_n, 0) AS same_poe_order_units_n,
                   coalesce(h.order_units_n, 0) AS hospital_order_units_n,
                   CASE
                     WHEN s.order_units_n IS NOT NULL
                       THEN 'same_poe_hospital_overlap_order_outside_original_window'
                     WHEN h.order_units_n IS NOT NULL
                       THEN 'different_poe_hospital_overlap_order_in_admission'
                     WHEN e.poe_id IS NULL OR trim(e.poe_id) = ''
                          OR NOT coalesce(e.poe_id_identity_link, false)
                       THEN 'emar_poe_missing_or_not_identity_resolvable'
                     ELSE 'no_hospital_overlap_ppi_order_in_admission'
                   END AS provenance_category
            FROM a2_upgrade_input a
            JOIN a2_first_broad_event e USING (stay_id)
            LEFT JOIN same_poe s
              ON e.stay_id = s.stay_id AND e.poe_id = s.poe_id
            LEFT JOIN any_hospital h USING (stay_id)
            WHERE a.order_exposure = 0 AND a.admin_broad = 1
            """,
            "a2_window_provenance",
        )

        a1_events_query = r"""
            SELECT e.*,
                   (nullif(trim(coalesce(e.route, '')), '') IS NOT NULL)
                     AS route_available,
                   (e.dose_given_num IS NOT NULL
                     AND nullif(trim(coalesce(e.dose_given_unit, '')), '')
                         IS NOT NULL) AS dose_unit_pair_available,
                   CASE
                     WHEN nullif(trim(coalesce(e.route, '')), '') IS NULL
                       THEN true
                     ELSE regexp_matches(
                       lower(e.route),
                       'subcut|(^|[^a-z])(sc|sq)([^a-z]|$)'
                     )
                   END AS route_if_available_pass,
                   CASE
                     WHEN e.dose_given_num IS NULL
                       OR nullif(trim(coalesce(e.dose_given_unit, '')), '') IS NULL
                       THEN true
                     WHEN e.ingredient = 'heparin'
                       THEN regexp_matches(lower(e.dose_given_unit), 'unit')
                            AND abs(e.dose_given_num - 5000.0) < 0.001
                     WHEN e.ingredient = 'enoxaparin'
                       THEN regexp_matches(lower(e.dose_given_unit), '(^|[^a-z])mg([^a-z]|$)')
                            AND e.dose_given_num BETWEEN 20.0 AND 60.0
                     ELSE false
                   END AS dose_if_available_pass
            FROM base.emar_stay_events e
            JOIN a1_post a USING (stay_id)
            WHERE e.drug_class = 'vte_prophylaxis'
              AND e.ingredient IN ('heparin', 'enoxaparin')
              AND e.event_category = 'given_strict'
              AND e.charttime BETWEEN a.intime AND a.outtime
        """
        save_plan(con, "a1_given_events_metadata_explain", a1_events_query)
        a1_event_pilot = a1_events_query.replace(
            "JOIN a1_post a USING (stay_id)",
            "JOIN (SELECT * FROM a1_post ORDER BY stay_id LIMIT 100) a USING (stay_id)",
            1,
        )
        run_step(
            con,
            "limited 100-stay A1 administration-metadata pilot",
            "CREATE OR REPLACE TEMP TABLE a1_event_pilot AS " + a1_event_pilot,
            "a1_event_pilot",
        )
        a1_pilot_max = int(
            con.execute(
                """
                SELECT coalesce(max(rows_n), 0) FROM (
                  SELECT stay_id, count(*) AS rows_n
                  FROM a1_event_pilot GROUP BY stay_id
                )
                """
            ).fetchone()[0]
        )
        if a1_pilot_max > 5000:
            raise RuntimeError(
                f"A1 event pilot multiplicity unsafe: max={a1_pilot_max}"
            )
        run_step(
            con,
            "materialize A1 strict-positive VTE events with metadata gates",
            "CREATE OR REPLACE TABLE a1_given_events AS " + a1_events_query,
            "a1_given_events",
        )
        run_step(
            con,
            "aggregate original and metadata-constrained A1 operators",
            """
            CREATE OR REPLACE TABLE a1_event_operator_by_stay AS
            SELECT stay_id,
                   min(charttime) AS broad_admin_onset,
                   min(charttime) FILTER (
                     WHERE route_if_available_pass AND dose_if_available_pass
                   ) AS metadata_admin_onset,
                   count(*) AS broad_events_n,
                   count(*) FILTER (
                     WHERE route_if_available_pass AND dose_if_available_pass
                   ) AS metadata_events_n
            FROM a1_given_events GROUP BY stay_id;

            CREATE OR REPLACE TABLE a1_upgrade_input AS
            SELECT a.*,
                   (m.metadata_admin_onset IS NOT NULL)::INTEGER
                     AS admin_metadata_constrained,
                   CASE WHEN m.metadata_admin_onset IS NULL THEN NULL ELSE
                     greatest(0.0, date_diff('second', a.intime,
                       m.metadata_admin_onset) / 3600.0) END
                     AS metadata_admin_onset_hours
            FROM a1_post a
            LEFT JOIN a1_event_operator_by_stay m USING (stay_id)
            """,
        )
        a1_upgrade_n = int(
            con.execute("SELECT count(*) FROM a1_upgrade_input").fetchone()[0]
        )
        if a1_upgrade_n != a1_n:
            raise RuntimeError("A1 upgraded input changed cohort membership")

        run_step(
            con,
            "trace A1 broad administration-only provenance",
            """
            CREATE OR REPLACE TABLE a1_first_broad_event AS
            SELECT * EXCLUDE (rn) FROM (
              SELECT e.*, row_number() OVER (
                PARTITION BY e.stay_id
                ORDER BY e.charttime, e.emar_id, e.emar_seq
              ) AS rn
              FROM a1_given_events e
              JOIN a1_upgrade_input a USING (stay_id)
              WHERE a.order_exposure = 0 AND a.admin_broad = 1
            ) WHERE rn = 1;

            CREATE OR REPLACE TABLE a1_same_poe_prescription AS
            SELECT f.stay_id, f.poe_id, count(*) AS prescription_rows_n
            FROM a1_first_broad_event f
            JOIN base.prescription_candidates p
              ON f.subject_id = p.subject_id
             AND f.hadm_id = p.hadm_id
             AND f.poe_id = p.poe_id
            WHERE p.drug_class = 'vte_prophylaxis'
              AND p.ingredient IN ('heparin', 'enoxaparin')
            GROUP BY f.stay_id, f.poe_id;

            CREATE OR REPLACE TABLE a1_any_admission_prescription AS
            SELECT f.stay_id, count(*) AS prescription_rows_n
            FROM a1_first_broad_event f
            JOIN base.prescription_candidates p
              ON f.subject_id = p.subject_id AND f.hadm_id = p.hadm_id
            WHERE p.drug_class = 'vte_prophylaxis'
              AND p.ingredient IN ('heparin', 'enoxaparin')
            GROUP BY f.stay_id;

            CREATE OR REPLACE TABLE a1_any_stay_order AS
            SELECT f.stay_id, count(*) AS order_units_n
            FROM a1_first_broad_event f
            JOIN base.order_clusters_all o USING (stay_id)
            WHERE o.drug_class = 'vte_prophylaxis'
              AND o.ingredient IN ('heparin', 'enoxaparin')
            GROUP BY f.stay_id;

            CREATE OR REPLACE TABLE a1_admin_only_provenance AS
            SELECT a.subject_id, a.hadm_id, a.stay_id, a.outcome,
                   e.emar_id, e.poe_id, e.charttime, e.medication,
                   e.ingredient, e.route, e.dose_given_num,
                   e.dose_given_unit, e.route_available,
                   e.dose_unit_pair_available,
                   e.route_if_available_pass, e.dose_if_available_pass,
                   e.poe_id_identity_link,
                   coalesce(s.prescription_rows_n, 0)
                     AS same_poe_prescription_rows_n,
                   coalesce(t.order_units_n, 0) AS stay_order_units_n,
                   coalesce(h.prescription_rows_n, 0)
                     AS admission_prescription_rows_n,
                   CASE
                     WHEN NOT e.route_if_available_pass
                          OR NOT e.dose_if_available_pass
                       THEN 'observed_metadata_inconsistent_with_prophylaxis'
                     WHEN s.prescription_rows_n IS NOT NULL
                       THEN 'same_poe_vte_prescription_outside_original_eligibility'
                     WHEN t.order_units_n IS NOT NULL
                       THEN 'different_poe_vte_order_assigned_to_icu_stay'
                     WHEN h.prescription_rows_n IS NOT NULL
                       THEN 'vte_prescription_elsewhere_in_admission'
                     WHEN e.poe_id IS NULL OR trim(e.poe_id) = ''
                          OR NOT coalesce(e.poe_id_identity_link, false)
                       THEN 'emar_poe_missing_or_not_identity_resolvable'
                     ELSE 'no_mapped_vte_prescription_in_admission'
                   END AS provenance_category
            FROM a1_upgrade_input a
            JOIN a1_first_broad_event e USING (stay_id)
            LEFT JOIN a1_same_poe_prescription s
              ON e.stay_id = s.stay_id AND e.poe_id = s.poe_id
            LEFT JOIN a1_any_stay_order t USING (stay_id)
            LEFT JOIN a1_any_admission_prescription h USING (stay_id)
            WHERE a.order_exposure = 0 AND a.admin_broad = 1
            """,
            "a1_admin_only_provenance",
        )

        export_query(
            con,
            """
            SELECT drug_class,
                   count(*) AS strict_given_events_n,
                   count(*) FILTER (WHERE dose_given_num IS NOT NULL)
                     AS dose_given_available_n,
                   100.0 * count(*) FILTER (WHERE dose_given_num IS NOT NULL)
                     / count(*) AS dose_given_available_pct,
                   count(*) FILTER (
                     WHERE dose_given_num IS NOT NULL
                       AND nullif(trim(coalesce(dose_given_unit, '')), '')
                           IS NOT NULL
                   ) AS dose_with_unit_available_n,
                   100.0 * count(*) FILTER (
                     WHERE dose_given_num IS NOT NULL
                       AND nullif(trim(coalesce(dose_given_unit, '')), '')
                           IS NOT NULL
                   ) / count(*) AS dose_with_unit_available_pct,
                   count(*) FILTER (
                     WHERE nullif(trim(coalesce(route, '')), '') IS NOT NULL
                   ) AS route_available_n,
                   100.0 * count(*) FILTER (
                     WHERE nullif(trim(coalesce(route, '')), '') IS NOT NULL
                   ) / count(*) AS route_available_pct
            FROM base.emar_stay_events
            WHERE event_category = 'given_strict'
            GROUP BY drug_class ORDER BY drug_class
            """,
            TABLES / "emar_given_dose_route_availability_by_class.csv",
        )
        export_query(
            con,
            """
            SELECT ingredient, count(*) AS strict_given_events_n,
                   sum(route_available::INTEGER) AS route_available_n,
                   100.0 * avg(route_available::INTEGER) AS route_available_pct,
                   sum(dose_unit_pair_available::INTEGER)
                     AS dose_unit_pair_available_n,
                   100.0 * avg(dose_unit_pair_available::INTEGER)
                     AS dose_unit_pair_available_pct,
                   sum((route_if_available_pass
                        AND dose_if_available_pass)::INTEGER)
                     AS metadata_constrained_events_n,
                   100.0 * avg((route_if_available_pass
                        AND dose_if_available_pass)::INTEGER)
                     AS metadata_constrained_events_pct
            FROM a1_given_events GROUP BY ingredient ORDER BY ingredient
            """,
            TABLES / "a1_administration_metadata_availability.csv",
        )
        export_query(
            con,
            """
            SELECT provenance_category, count(*) AS patients_n,
                   sum(outcome) AS hospital_deaths_n,
                   100.0 * avg(outcome) AS hospital_death_pct,
                   sum(route_available::INTEGER) AS route_available_n,
                   sum(dose_unit_pair_available::INTEGER)
                     AS dose_unit_pair_available_n
            FROM a1_admin_only_provenance
            GROUP BY provenance_category ORDER BY patients_n DESC
            """,
            TABLES / "a1_broad_admin_only_provenance_summary.csv",
        )
        export_query(
            con,
            """
            SELECT provenance_category, count(*) AS patients_n,
                   sum(outcome) AS deaths_90d_n,
                   100.0 * avg(outcome) AS death_90d_pct
            FROM a2_window_provenance
            GROUP BY provenance_category ORDER BY patients_n DESC
            """,
            TABLES / "a2_order_window_provenance_summary.csv",
        )

        export_query(
            con,
            "SELECT * FROM a1_upgrade_input ORDER BY stay_id",
            MODEL_INPUTS / "anchor_a1_prereview_upgrade.csv",
        )
        export_query(
            con,
            "SELECT * FROM a2_upgrade_input ORDER BY stay_id",
            MODEL_INPUTS / "anchor_a2_prereview_upgrade.csv",
        )
        export_query(
            con,
            """
            WITH operators AS (
              SELECT 'A1' AS anchor_id,
                     'original_strict' AS comparison,
                     order_exposure AS order_exposure,
                     admin_strict AS administration_exposure,
                     outcome FROM a1_upgrade_input
              UNION ALL
              SELECT 'A1', 'original_broad', order_exposure, admin_broad,
                     outcome FROM a1_upgrade_input
              UNION ALL
              SELECT 'A1', 'metadata_constrained_broad', order_exposure,
                     admin_metadata_constrained, outcome FROM a1_upgrade_input
              UNION ALL
              SELECT 'A2', 'original_strict', order_exposure, admin_strict,
                     outcome FROM a2_upgrade_input
              UNION ALL
              SELECT 'A2', 'original_broad', order_exposure, admin_broad,
                     outcome FROM a2_upgrade_input
              UNION ALL
              SELECT 'A2', 'hospital_overlap_strict', hospital_order_exposure,
                     hospital_admin_strict, outcome FROM a2_upgrade_input
              UNION ALL
              SELECT 'A2', 'hospital_overlap_broad', hospital_order_exposure,
                     admin_broad, outcome FROM a2_upgrade_input
            )
            SELECT anchor_id, comparison, order_exposure,
                   administration_exposure, count(*) AS patients_n,
                   sum(outcome) AS outcomes_n,
                   100.0 * avg(outcome) AS outcome_pct
            FROM operators
            GROUP BY anchor_id, comparison, order_exposure,
                     administration_exposure
            ORDER BY anchor_id, comparison, order_exposure,
                     administration_exposure
            """,
            TABLES / "prereview_operator_outcome_cells.csv",
        )

        prescription_scan = explicit_csv(raw_source, PRESCRIPTION_COLUMNS)
        ndc_query = f"""
            SELECT im.drug_class, nm.direct_ingredient AS ingredient,
                   CASE
                     WHEN regexp_replace(trim(coalesce(p.ndc, '')),
                           '[^0-9]', '', 'g') IN ('', '0') THEN ''
                     WHEN regexp_matches(
                       regexp_replace(trim(p.ndc), '[^0-9]', '', 'g'),
                       '^0+$'
                     ) THEN ''
                     ELSE regexp_replace(trim(p.ndc), '[^0-9]', '', 'g')
                   END AS normalized_ndc,
                   count(*) AS prescription_rows_n
            FROM {prescription_scan} p
            JOIN base.prescription_name_map nm
              ON lower(trim(coalesce(p.drug, '') || ' ' ||
                            coalesce(p.formulary_drug_cd, ''))) = nm.name_key
            JOIN base.s02v2_ingredient_map im
              ON nm.direct_ingredient = im.ingredient
            WHERE nm.direct_ingredient IS NOT NULL
            GROUP BY im.drug_class, nm.direct_ingredient, normalized_ndc
        """
        save_plan(con, "ndc_name_mapped_aggregate_explain", ndc_query)
        ndc_pilot_query = ndc_query.replace(
            f"FROM {prescription_scan} p",
            f"FROM (SELECT * FROM {prescription_scan} LIMIT 100000) p",
            1,
        )
        run_step(
            con,
            "limited 100000-row prescriptions NDC pilot",
            "CREATE OR REPLACE TEMP TABLE ndc_pilot AS " + ndc_pilot_query,
            "ndc_pilot",
        )
        run_step(
            con,
            "full prescriptions NDC projection and name-mapped aggregation",
            "CREATE OR REPLACE TABLE ndc_name_mapped_counts AS " + ndc_query,
            "ndc_name_mapped_counts",
        )
        export_query(
            con,
            """
            SELECT drug_class,
                   sum(prescription_rows_n) AS name_mapped_rows_n,
                   sum(prescription_rows_n) FILTER (WHERE normalized_ndc <> '')
                     AS ndc_bearing_rows_n,
                   100.0 * sum(prescription_rows_n) FILTER (
                     WHERE normalized_ndc <> ''
                   ) / sum(prescription_rows_n) AS ndc_bearing_rows_pct,
                   count(DISTINCT normalized_ndc) FILTER (
                     WHERE normalized_ndc <> ''
                   ) AS unique_ndc_n
            FROM ndc_name_mapped_counts GROUP BY drug_class
            ORDER BY drug_class
            """,
            TABLES / "prescription_ndc_availability_by_class.csv",
        )
        export_query(
            con,
            """
            SELECT normalized_ndc,
                   string_agg(DISTINCT ingredient, '|'
                     ORDER BY ingredient) AS expected_ingredients,
                   string_agg(DISTINCT drug_class, '|'
                     ORDER BY drug_class) AS expected_classes,
                   sum(prescription_rows_n) AS prescription_rows_n
            FROM ndc_name_mapped_counts WHERE normalized_ndc <> ''
            GROUP BY normalized_ndc
            ORDER BY prescription_rows_n DESC, normalized_ndc
            """,
            TABLES / "prescription_ndc_code_counts_for_rxnav.csv",
        )

        run_step(
            con,
            "aggregate nonmissing eMAR-detail product codes by event",
            """
            CREATE OR REPLACE TABLE emar_product_code_events AS
            SELECT emar_id, emar_seq,
                   max((nullif(trim(coalesce(product_code, '')), '')
                     IS NOT NULL)::INTEGER)::BOOLEAN AS product_code_available,
                   max(regexp_matches(
                     regexp_replace(trim(coalesce(product_code, '')),
                                    '[^0-9]', '', 'g'),
                     '^[0-9]{10,11}$'
                   )::INTEGER)::BOOLEAN AS ndc_like_product_code
            FROM base.emar_detail_relevant
            GROUP BY emar_id, emar_seq
            """,
            "emar_product_code_events",
        )
        export_query(
            con,
            """
            SELECT w.drug_class, count(*) AS whitelisted_emar_events_n,
                   count(*) FILTER (
                     WHERE coalesce(d.product_code_available, false)
                   ) AS product_code_available_events_n,
                   100.0 * count(*) FILTER (
                     WHERE coalesce(d.product_code_available, false)
                   ) / count(*) AS product_code_available_events_pct,
                   count(*) FILTER (
                     WHERE coalesce(d.ndc_like_product_code, false)
                   ) AS ndc_like_product_code_events_n,
                   100.0 * count(*) FILTER (
                     WHERE coalesce(d.ndc_like_product_code, false)
                   ) / count(*) AS ndc_like_product_code_events_pct
            FROM base.emar_whitelist_base w
            LEFT JOIN emar_product_code_events d USING (emar_id, emar_seq)
            GROUP BY w.drug_class ORDER BY w.drug_class
            """,
            TABLES / "emar_product_code_availability_by_class.csv",
        )

        feasibility = pd.DataFrame(
            [
                {
                    "extension": "Sepsis-3 sensitivity",
                    "required_local_input": "official versioned sepsis3 or complete derivation",
                    "searched_root": str(MIMIC),
                    "available": False,
                    "decision": "not executed; retain transparent ICD-sepsis anchor",
                },
                {
                    "extension": "OMOP DRUG_EXPOSURE execution",
                    "required_local_input": "versioned OMOP ETL and DRUG_EXPOSURE output",
                    "searched_root": str(PROJECT),
                    "available": False,
                    "decision": "not executed; retain conceptual translation only",
                },
            ]
        )
        feasibility.to_csv(
            TABLES / "sepsis3_omop_local_input_feasibility.csv",
            index=False,
            encoding="utf-8-sig",
        )
        log(f"CHECKPOINT file=sepsis3_omop_local_input_feasibility.csv rows={len(feasibility)}")

        pilot_cardinality = pd.DataFrame(
            [
                {
                    "pilot": "a2_hospital_overlap_100_stays",
                    "rows_n": int(
                        con.execute("SELECT count(*) FROM a2_candidate_pilot").fetchone()[0]
                    ),
                    "maximum_rows_per_stay": a2_pilot_max,
                    "safety_gate": "PASS",
                },
                {
                    "pilot": "a1_metadata_100_stays",
                    "rows_n": int(
                        con.execute("SELECT count(*) FROM a1_event_pilot").fetchone()[0]
                    ),
                    "maximum_rows_per_stay": a1_pilot_max,
                    "safety_gate": "PASS",
                },
                {
                    "pilot": "ndc_projection_100000_prescription_rows",
                    "rows_n": int(
                        con.execute("SELECT count(*) FROM ndc_pilot").fetchone()[0]
                    ),
                    "maximum_rows_per_stay": None,
                    "safety_gate": "PASS",
                },
            ]
        )
        pilot_cardinality.to_csv(
            TABLES / "prereview_query_pilot_cardinality.csv",
            index=False,
            encoding="utf-8-sig",
        )
        log(f"CHECKPOINT file=prereview_query_pilot_cardinality.csv rows={len(pilot_cardinality)}")

        raw_after = {
            "path": str(raw_source),
            "size": raw_source.stat().st_size,
            "mtime_ns": raw_source.stat().st_mtime_ns,
        }
        if raw_before != raw_after:
            raise RuntimeError("Raw prescriptions source changed during read-only audit")

        qc = {
            "contract_sha256": observed_contract_hash,
            "script_sha256": sha256(Path(__file__)),
            "a1_rows_n": a1_upgrade_n,
            "a2_rows_n": a2_upgrade_n,
            "a1_broad_admin_only_n": int(
                con.execute("SELECT count(*) FROM a1_admin_only_provenance").fetchone()[0]
            ),
            "a2_broad_admin_only_n": int(
                con.execute("SELECT count(*) FROM a2_window_provenance").fetchone()[0]
            ),
            "a2_hospital_order_units_n": int(hospital_rows),
            "raw_source_before": raw_before,
            "raw_source_after": raw_after,
            "base_database_read_only": True,
            "elapsed_seconds": time.time() - STARTED,
        }
        if qc["a1_broad_admin_only_n"] != 5_816:
            raise RuntimeError(f"A1 provenance denominator gate failed: {qc}")
        if qc["a2_broad_admin_only_n"] != 296:
            raise RuntimeError(f"A2 provenance denominator gate failed: {qc}")
        (MANIFESTS / "28_prereview_upgrade_analytics_manifest.json").write_text(
            json.dumps(qc, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log("PASS all analytic denominator and immutability gates")
    finally:
        con.close()

    session = "\n".join(
        [
            f"timestamp={datetime.now().astimezone().isoformat()}",
            f"python={sys.version}",
            f"platform={platform.platform()}",
            f"duckdb={duckdb.__version__}",
            f"pandas={pd.__version__}",
            f"script_sha256={sha256(Path(__file__))}",
            f"contract_sha256={observed_contract_hash}",
        ]
    )
    (ENVIRONMENT / "Python_sessionInfo_JAMIA_prereview_upgrade.txt").write_text(
        session + "\n", encoding="utf-8"
    )
    log(f"COMPLETE elapsed_seconds={time.time() - STARTED:.3f}")


if __name__ == "__main__":
    main()
