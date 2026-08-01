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
SCRATCH_DB = PROJECT / "cache" / "jamia_residual_provenance_v1_0.duckdb"
TMP = PROJECT / "cache" / "jamia_poe_temporal_mechanism_tmp"
OUTPUT = PROJECT / "outputs" / "jamia_residual_provenance_v1_0"
TABLES = OUTPUT / "tables"
LOGS = OUTPUT / "logs"
PLANS = OUTPUT / "plans"
MANIFESTS = OUTPUT / "manifests"
QA = OUTPUT / "qa"
ENVIRONMENT = PROJECT / "environment"
MIMIC = Path(os.environ["MIMIC_IV_ROOT"])
CONTRACT = (
    PROJECT
    / "contracts"
    / "jamia_poe_temporal_mechanism_addendum_v1.0_2026-08-01.md"
)
EXPECTED_CONTRACT_SHA256 = (
    "415a39ccd5bcef4bf03a9add7a68cf5e14a7e35edcbdec76927d4e12b84ed79a"
)

for directory in (TMP, TABLES, LOGS, PLANS, MANIFESTS, QA, ENVIRONMENT):
    directory.mkdir(parents=True, exist_ok=True)

LOG_PATH = LOGS / "42_build_poe_temporal_mechanism_audit.log"


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


def source_state(path: Path) -> dict[str, object]:
    item = path.stat()
    return {"path": str(path), "bytes": item.st_size, "mtime_ns": item.st_mtime_ns}


def explicit_csv(path: Path, columns: list[str]) -> str:
    mapping = ", ".join(f"'{name}':'VARCHAR'" for name in columns)
    return (
        f"read_csv('{sql_path(path)}', header=true, compression='gzip', "
        f"columns={{{mapping}}}, strict_mode=true, ignore_errors=false, "
        "null_padding=false, quote='\"', escape='\"')"
    )


def save_plan(con: duckdb.DuckDBPyConnection, name: str, query: str) -> None:
    plan = "\n".join(str(row[-1]) for row in con.execute("EXPLAIN " + query).fetchall())
    (PLANS / f"{name}.txt").write_text(plan, encoding="utf-8")
    upper = plan.upper()
    if "CROSS_PRODUCT" in upper or "BLOCKWISE_NL_JOIN" in upper:
        raise RuntimeError(f"Unsafe join operator in {name}:\n{plan}")
    log(f"PLAN {name} equality_join_gate=PASS")


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


def export_query(
    con: duckdb.DuckDBPyConnection, query: str, filename: str
) -> pd.DataFrame:
    frame = con.execute(query).fetchdf()
    frame.to_csv(TABLES / filename, index=False, encoding="utf-8-sig")
    log(f"CHECKPOINT file={filename} rows={len(frame)}")
    return frame


def main() -> None:
    started = time.time()
    observed_contract_hash = sha256(CONTRACT)
    if observed_contract_hash != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError(
            f"POE mechanism contract mismatch: {observed_contract_hash}"
        )
    if not BASE_DB.exists() or not SCRATCH_DB.exists():
        raise FileNotFoundError("Required DuckDB cache is missing")

    poe_path = MIMIC / "hosp" / "poe.csv.gz"
    admissions_path = MIMIC / "hosp" / "admissions.csv.gz"
    prescriptions_path = MIMIC / "hosp" / "prescriptions.csv.gz"
    raw_sources = [poe_path, admissions_path, prescriptions_path]
    raw_before = {path.name: source_state(path) for path in raw_sources}

    poe_columns = [
        "poe_id",
        "poe_seq",
        "subject_id",
        "hadm_id",
        "ordertime",
        "order_type",
        "order_subtype",
        "transaction_type",
        "discontinue_of_poe_id",
        "discontinued_by_poe_id",
        "order_provider_id",
        "order_status",
    ]
    admission_columns = [
        "subject_id",
        "hadm_id",
        "admittime",
        "dischtime",
        "deathtime",
        "admission_type",
        "admit_provider_id",
        "admission_location",
        "discharge_location",
        "insurance",
        "language",
        "marital_status",
        "race",
        "edregtime",
        "edouttime",
        "hospital_expire_flag",
    ]
    poe_scan = explicit_csv(poe_path, poe_columns)
    admissions_scan = explicit_csv(admissions_path, admission_columns)

    con = duckdb.connect(str(SCRATCH_DB))
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{sql_path(TMP)}'")
    try:
        con.execute(f"ATTACH '{sql_path(BASE_DB)}' AS base (READ_ONLY)")

        run_step(
            con,
            "freeze row-level replication units",
            """
            CREATE OR REPLACE TABLE a2_poe_prescription_rows AS
            SELECT subject_id, hadm_id, stay_id, pharmacy_id,
                   prescription_poe_id, prescription_row_id,
                   min(emar_charttime) AS first_linked_admin,
                   min(starttime) AS prescription_starttime,
                   max(stoptime) AS prescription_stoptime,
                   min(drug) AS drug,
                   min(route) AS route
            FROM a2_residual_linked_prescription_rows
            GROUP BY subject_id, hadm_id, stay_id, pharmacy_id,
                     prescription_poe_id, prescription_row_id
            """,
            "a2_poe_prescription_rows",
        )
        row_units = int(
            con.execute("SELECT count(*) FROM a2_poe_prescription_rows").fetchone()[0]
        )
        if row_units != 256:
            raise RuntimeError(f"Expected 256 row-level units, observed {row_units}")

        run_step(
            con,
            "deduplicate primary pharmacy-POE order units",
            """
            CREATE OR REPLACE TABLE a2_poe_order_units AS
            SELECT subject_id, hadm_id, stay_id, pharmacy_id,
                   prescription_poe_id,
                   count(*) AS prescription_rows_n,
                   min(first_linked_admin) AS first_linked_admin,
                   min(prescription_starttime) AS prescription_starttime,
                   max(prescription_stoptime) AS prescription_stoptime,
                   string_agg(DISTINCT coalesce(nullif(trim(drug), ''), '<blank>'),
                              ' | ' ORDER BY coalesce(nullif(trim(drug), ''), '<blank>'))
                     AS drug_values,
                   string_agg(DISTINCT coalesce(nullif(trim(route), ''), '<blank>'),
                              ' | ' ORDER BY coalesce(nullif(trim(route), ''), '<blank>'))
                     AS route_values
            FROM a2_poe_prescription_rows
            GROUP BY subject_id, hadm_id, stay_id, pharmacy_id,
                     prescription_poe_id
            """,
            "a2_poe_order_units",
        )
        primary_units, primary_stays = con.execute(
            "SELECT count(*), count(DISTINCT stay_id) FROM a2_poe_order_units"
        ).fetchone()
        if int(primary_stays) != 183 or int(primary_units) > 256:
            raise RuntimeError(
                f"Primary-unit gate failed: units={primary_units}, stays={primary_stays}"
            )

        direct_poe_query = f"""
            SELECT k.subject_id, k.hadm_id, k.stay_id, k.pharmacy_id,
                   k.prescription_poe_id, k.prescription_rows_n,
                   k.first_linked_admin, k.prescription_starttime,
                   k.prescription_stoptime, k.drug_values, k.route_values,
                   TRY_CAST(p.poe_seq AS BIGINT) AS poe_seq,
                   TRY_CAST(p.ordertime AS TIMESTAMP) AS ordertime,
                   nullif(trim(p.order_type), '') AS order_type,
                   nullif(trim(p.order_subtype), '') AS order_subtype,
                   nullif(trim(p.transaction_type), '') AS transaction_type,
                   nullif(trim(p.discontinue_of_poe_id), '')
                     AS discontinue_of_poe_id,
                   nullif(trim(p.discontinued_by_poe_id), '')
                     AS discontinued_by_poe_id,
                   nullif(trim(p.order_status), '') AS order_status
            FROM a2_poe_order_units k
            JOIN {poe_scan} p
              ON TRY_CAST(p.subject_id AS BIGINT) = k.subject_id
             AND TRY_CAST(p.hadm_id AS BIGINT) = k.hadm_id
             AND p.poe_id = k.prescription_poe_id
        """
        save_plan(con, "a2_poe_direct_rows_explain", direct_poe_query)
        pilot_query = direct_poe_query.replace(
            "FROM a2_poe_order_units k",
            "FROM (SELECT * FROM a2_poe_order_units "
            "ORDER BY stay_id, pharmacy_id LIMIT 20) k",
            1,
        )
        run_step(
            con,
            "20-unit POE exact-key pilot",
            "CREATE OR REPLACE TEMP TABLE a2_poe_direct_pilot AS " + pilot_query,
            "a2_poe_direct_pilot",
        )
        pilot_units, pilot_rows = con.execute(
            "SELECT count(DISTINCT (stay_id, pharmacy_id, prescription_poe_id)), "
            "count(*) FROM a2_poe_direct_pilot"
        ).fetchone()
        if int(pilot_rows) > 100 * int(pilot_units):
            raise RuntimeError(
                f"Unsafe pilot POE multiplicity: rows={pilot_rows}, units={pilot_units}"
            )

        run_step(
            con,
            "materialize exact-key raw POE rows",
            "CREATE OR REPLACE TABLE a2_poe_direct_rows AS " + direct_poe_query,
            "a2_poe_direct_rows",
        )
        direct_rows, linked_units = con.execute(
            "SELECT count(*), count(DISTINCT "
            "(stay_id, pharmacy_id, prescription_poe_id)) FROM a2_poe_direct_rows"
        ).fetchone()
        if int(linked_units) != int(primary_units):
            raise RuntimeError(
                f"POE linkage incomplete: linked={linked_units}, expected={primary_units}"
            )

        multiplicity_mismatches = int(
            con.execute(
                """
                WITH observed AS (
                  SELECT prescription_poe_id AS poe_id, count(*) AS rows_n
                  FROM a2_poe_direct_rows GROUP BY prescription_poe_id
                )
                SELECT count(*)
                FROM observed o JOIN base.poe_identity i USING (poe_id)
                WHERE o.rows_n <> i.poe_rows_n
                """
            ).fetchone()[0]
        )
        if multiplicity_mismatches:
            raise RuntimeError(
                f"Raw/base POE multiplicity mismatches={multiplicity_mismatches}"
            )

        run_step(
            con,
            "project exact admissions",
            f"""
            CREATE OR REPLACE TABLE a2_poe_admissions AS
            SELECT DISTINCT k.subject_id, k.hadm_id,
                   TRY_CAST(a.admittime AS TIMESTAMP) AS admittime,
                   TRY_CAST(a.dischtime AS TIMESTAMP) AS dischtime
            FROM (SELECT DISTINCT subject_id, hadm_id
                  FROM a2_poe_order_units) k
            JOIN {admissions_scan} a
              ON TRY_CAST(a.subject_id AS BIGINT) = k.subject_id
             AND TRY_CAST(a.hadm_id AS BIGINT) = k.hadm_id
            """,
            "a2_poe_admissions",
        )

        run_step(
            con,
            "aggregate POE fields and timing to primary order units",
            """
            CREATE OR REPLACE TABLE a2_poe_unit_facts AS
            WITH p AS (
              SELECT subject_id, hadm_id, stay_id, pharmacy_id,
                     prescription_poe_id,
                     min(prescription_rows_n) AS prescription_rows_n,
                     min(first_linked_admin) AS first_linked_admin,
                     min(prescription_starttime) AS prescription_starttime,
                     min(drug_values) AS drug_values,
                     min(route_values) AS route_values,
                     count(*) AS raw_poe_rows_n,
                     min(ordertime) AS first_poe_ordertime,
                     max(ordertime) AS last_poe_ordertime,
                     string_agg(DISTINCT coalesce(order_type, '<blank>'),
                                ' | ' ORDER BY coalesce(order_type, '<blank>'))
                       AS order_type_values,
                     string_agg(DISTINCT coalesce(order_subtype, '<blank>'),
                                ' | ' ORDER BY coalesce(order_subtype, '<blank>'))
                       AS order_subtype_values,
                     string_agg(DISTINCT coalesce(transaction_type, '<blank>'),
                                ' | ' ORDER BY coalesce(transaction_type, '<blank>'))
                       AS transaction_type_values,
                     string_agg(DISTINCT coalesce(order_status, '<blank>'),
                                ' | ' ORDER BY coalesce(order_status, '<blank>'))
                       AS order_status_values,
                     bool_or(discontinue_of_poe_id IS NOT NULL)
                       AS has_discontinue_of_poe_id,
                     bool_or(discontinued_by_poe_id IS NOT NULL)
                       AS has_discontinued_by_poe_id
              FROM a2_poe_direct_rows
              GROUP BY subject_id, hadm_id, stay_id, pharmacy_id,
                       prescription_poe_id
            )
            SELECT p.*, r.intime, a.admittime, a.dischtime,
                   date_diff('minute', p.first_linked_admin,
                             p.first_poe_ordertime) / 60.0
                     AS order_minus_admin_hours,
                   date_diff('minute', r.intime, p.first_poe_ordertime) / 60.0
                     AS order_from_icu_hours,
                   date_diff('minute', a.admittime,
                             p.first_poe_ordertime) / 60.0
                     AS order_from_admission_hours,
                   date_diff('minute', a.dischtime,
                             p.first_poe_ordertime) / 60.0
                     AS order_minus_discharge_hours,
                   date_diff('minute', p.first_linked_admin,
                             p.prescription_starttime) / 60.0
                     AS start_minus_admin_hours
            FROM p
            JOIN a2_residual_stays r
              ON p.stay_id = r.stay_id
            JOIN a2_poe_admissions a
              ON p.subject_id = a.subject_id
             AND p.hadm_id = a.hadm_id
            """,
            "a2_poe_unit_facts",
        )

        run_step(
            con,
            "stage one-hop POE references",
            """
            CREATE OR REPLACE TABLE a2_poe_reference_keys AS
            SELECT DISTINCT subject_id, hadm_id, discontinue_of_poe_id AS poe_id,
                   'discontinue_of' AS reference_role
            FROM a2_poe_direct_rows
            WHERE discontinue_of_poe_id IS NOT NULL
            UNION ALL
            SELECT DISTINCT subject_id, hadm_id, discontinued_by_poe_id,
                   'discontinued_by'
            FROM a2_poe_direct_rows
            WHERE discontinued_by_poe_id IS NOT NULL
            """,
            "a2_poe_reference_keys",
        )
        reference_key_n = int(
            con.execute("SELECT count(*) FROM a2_poe_reference_keys").fetchone()[0]
        )
        if reference_key_n:
            reference_query = f"""
                SELECT k.subject_id, k.hadm_id, k.poe_id, k.reference_role,
                       TRY_CAST(p.poe_seq AS BIGINT) AS poe_seq,
                       TRY_CAST(p.ordertime AS TIMESTAMP) AS ordertime,
                       nullif(trim(p.order_type), '') AS order_type,
                       nullif(trim(p.transaction_type), '') AS transaction_type,
                       nullif(trim(p.order_status), '') AS order_status
                FROM a2_poe_reference_keys k
                JOIN {poe_scan} p
                  ON TRY_CAST(p.subject_id AS BIGINT) = k.subject_id
                 AND TRY_CAST(p.hadm_id AS BIGINT) = k.hadm_id
                 AND p.poe_id = k.poe_id
            """
            save_plan(con, "a2_poe_reference_rows_explain", reference_query)
            run_step(
                con,
                "resolve one-hop POE references",
                "CREATE OR REPLACE TABLE a2_poe_reference_rows AS "
                + reference_query,
                "a2_poe_reference_rows",
            )
        else:
            con.execute(
                """
                CREATE OR REPLACE TABLE a2_poe_reference_rows AS
                SELECT CAST(NULL AS BIGINT) AS subject_id,
                       CAST(NULL AS BIGINT) AS hadm_id,
                       CAST(NULL AS VARCHAR) AS poe_id,
                       CAST(NULL AS VARCHAR) AS reference_role,
                       CAST(NULL AS BIGINT) AS poe_seq,
                       CAST(NULL AS TIMESTAMP) AS ordertime,
                       CAST(NULL AS VARCHAR) AS order_type,
                       CAST(NULL AS VARCHAR) AS transaction_type,
                       CAST(NULL AS VARCHAR) AS order_status
                WHERE false
                """
            )

        checkpoints = export_query(
            con,
            """
            SELECT 'prescription-row replication units' AS checkpoint,
                   count(*) AS rows_n, count(DISTINCT stay_id) AS stays_n
            FROM a2_poe_prescription_rows
            UNION ALL
            SELECT 'primary pharmacy-POE units', count(*), count(DISTINCT stay_id)
            FROM a2_poe_order_units
            UNION ALL
            SELECT 'raw direct POE rows', count(*), count(DISTINCT stay_id)
            FROM a2_poe_direct_rows
            UNION ALL
            SELECT 'unit-level POE facts', count(*), count(DISTINCT stay_id)
            FROM a2_poe_unit_facts
            UNION ALL
            SELECT 'one-hop POE reference rows', count(*), NULL
            FROM a2_poe_reference_rows
            """,
            "a2_poe_mechanism_checkpoint_cardinality.csv",
        )

        row_distribution = export_query(
            con,
            """
            WITH long AS (
              SELECT unnest(['order_type','order_subtype','transaction_type',
                             'order_status']) AS field,
                     unnest([coalesce(order_type, '<blank>'),
                             coalesce(order_subtype, '<blank>'),
                             coalesce(transaction_type, '<blank>'),
                             coalesce(order_status, '<blank>')]) AS value
              FROM a2_poe_direct_rows
            )
            SELECT field, value, count(*) AS raw_poe_rows_n,
                   round(100.0 * count(*) /
                         sum(count(*)) OVER (PARTITION BY field), 4) AS pct
            FROM long GROUP BY field, value
            ORDER BY field, raw_poe_rows_n DESC, value
            """,
            "a2_poe_field_distribution_raw_rows.csv",
        )

        unit_distribution = export_query(
            con,
            """
            WITH long AS (
              SELECT unnest(['order_type','order_subtype','transaction_type',
                             'order_status']) AS field,
                     unnest([order_type_values, order_subtype_values,
                             transaction_type_values, order_status_values]) AS value
              FROM a2_poe_unit_facts
            )
            SELECT field, value, count(*) AS primary_order_units_n,
                   round(100.0 * count(*) /
                         sum(count(*)) OVER (PARTITION BY field), 4) AS pct
            FROM long GROUP BY field, value
            ORDER BY field, primary_order_units_n DESC, value
            """,
            "a2_poe_field_distribution_primary_units.csv",
        )

        timing_summary = export_query(
            con,
            """
            WITH long AS (
              SELECT unnest(['POE ordertime minus first administration',
                             'POE ordertime from ICU entry',
                             'POE ordertime from hospital admission',
                             'POE ordertime minus hospital discharge',
                             'prescription starttime minus first administration'])
                       AS timing_metric,
                     unnest([order_minus_admin_hours, order_from_icu_hours,
                             order_from_admission_hours,
                             order_minus_discharge_hours,
                             start_minus_admin_hours]) AS hours
              FROM a2_poe_unit_facts
            )
            SELECT timing_metric, count(hours) AS units_with_timing_n,
                   min(hours) AS min_h,
                   quantile_cont(hours, 0.25) AS q1_h,
                   median(hours) AS median_h,
                   quantile_cont(hours, 0.75) AS q3_h,
                   max(hours) AS max_h
            FROM long GROUP BY timing_metric ORDER BY timing_metric
            """,
            "a2_poe_timing_summary_primary_units.csv",
        )

        discharge_bins = export_query(
            con,
            """
            WITH labeled AS (
              SELECT CASE
                WHEN order_minus_discharge_hours < -48 THEN '<-48 h'
                WHEN order_minus_discharge_hours < -24 THEN '-48 to <-24 h'
                WHEN order_minus_discharge_hours < 0 THEN '-24 to <0 h'
                WHEN order_minus_discharge_hours <= 24 THEN '0 to <=24 h'
                ELSE '>24 h' END AS discharge_relative_bin
              FROM a2_poe_unit_facts
              WHERE order_minus_discharge_hours IS NOT NULL
            )
            SELECT discharge_relative_bin, count(*) AS primary_order_units_n,
                   round(100.0 * count(*) / sum(count(*)) OVER (), 4) AS pct
            FROM labeled GROUP BY discharge_relative_bin
            ORDER BY CASE discharge_relative_bin
              WHEN '<-48 h' THEN 1 WHEN '-48 to <-24 h' THEN 2
              WHEN '-24 to <0 h' THEN 3 WHEN '0 to <=24 h' THEN 4 ELSE 5 END
            """,
            "a2_poe_discharge_relative_bins.csv",
        )

        discontinuation = export_query(
            con,
            """
            SELECT 'has discontinue_of_poe_id' AS diagnostic,
                   count(*) FILTER (WHERE has_discontinue_of_poe_id)
                     AS primary_order_units_n,
                   100.0 * count(*) FILTER (WHERE has_discontinue_of_poe_id)
                     / count(*) AS pct,
                   (SELECT count(DISTINCT (subject_id, hadm_id, poe_id))
                    FROM a2_poe_reference_rows
                    WHERE reference_role = 'discontinue_of') AS resolved_reference_ids_n
            FROM a2_poe_unit_facts
            UNION ALL
            SELECT 'has discontinued_by_poe_id',
                   count(*) FILTER (WHERE has_discontinued_by_poe_id),
                   100.0 * count(*) FILTER (WHERE has_discontinued_by_poe_id)
                     / count(*),
                   (SELECT count(DISTINCT (subject_id, hadm_id, poe_id))
                    FROM a2_poe_reference_rows
                    WHERE reference_role = 'discontinued_by')
            FROM a2_poe_unit_facts
            """,
            "a2_poe_discontinuation_summary.csv",
        )

        multiplicity = export_query(
            con,
            """
            SELECT prescription_rows_n, count(*) AS primary_order_units_n,
                   count(DISTINCT stay_id) AS stays_n,
                   round(100.0 * count(*) / sum(count(*)) OVER (), 4) AS pct
            FROM a2_poe_order_units GROUP BY prescription_rows_n
            ORDER BY prescription_rows_n
            """,
            "a2_prescription_row_multiplicity_by_primary_unit.csv",
        )

        multirow = export_query(
            con,
            """
            SELECT drug_values, route_values, prescription_rows_n,
                   count(*) AS primary_order_units_n,
                   count(DISTINCT stay_id) AS stays_n
            FROM a2_poe_order_units
            WHERE prescription_rows_n > 1
            GROUP BY drug_values, route_values, prescription_rows_n
            ORDER BY primary_order_units_n DESC, drug_values, route_values
            """,
            "a2_multirow_order_drug_route_combinations.csv",
        )

        mechanism_summary = export_query(
            con,
            """
            SELECT count(*) AS primary_order_units_n,
                   count(DISTINCT stay_id) AS linked_stays_n,
                   sum(prescription_rows_n) AS replicated_prescription_rows_n,
                   count(*) FILTER (WHERE prescription_rows_n > 1)
                     AS multirow_primary_units_n,
                   sum(prescription_rows_n - 1) AS duplicate_prescription_rows_n,
                   count(*) FILTER (WHERE first_poe_ordertime > first_linked_admin)
                     AS poe_after_admin_units_n,
                   100.0 * count(*) FILTER (
                     WHERE first_poe_ordertime > first_linked_admin
                   ) / count(*) AS poe_after_admin_pct,
                   median(order_minus_admin_hours)
                     AS order_minus_admin_median_h,
                   quantile_cont(order_minus_admin_hours, 0.25)
                     AS order_minus_admin_q1_h,
                   quantile_cont(order_minus_admin_hours, 0.75)
                     AS order_minus_admin_q3_h,
                   median(order_minus_discharge_hours)
                     AS order_minus_discharge_median_h,
                   count(*) FILTER (
                     WHERE order_minus_discharge_hours BETWEEN -24 AND 24
                   ) AS within_24h_of_discharge_n,
                   count(*) FILTER (WHERE has_discontinue_of_poe_id)
                     AS discontinue_of_units_n,
                   count(*) FILTER (WHERE has_discontinued_by_poe_id)
                     AS discontinued_by_units_n
            FROM a2_poe_unit_facts
            """,
            "a2_poe_temporal_mechanism_summary.csv",
        )

        summary = mechanism_summary.iloc[0]
        checks = [
            {
                "check": "contract_hash_match",
                "passed": observed_contract_hash == EXPECTED_CONTRACT_SHA256,
                "detail": observed_contract_hash,
            },
            {
                "check": "row_level_replication_256",
                "passed": row_units == 256,
                "detail": str(row_units),
            },
            {
                "check": "linked_stays_183",
                "passed": int(primary_stays) == 183,
                "detail": str(primary_stays),
            },
            {
                "check": "all_primary_units_link_to_raw_poe",
                "passed": int(linked_units) == int(primary_units),
                "detail": f"{linked_units}/{primary_units}",
            },
            {
                "check": "raw_base_poe_multiplicity_match",
                "passed": multiplicity_mismatches == 0,
                "detail": str(multiplicity_mismatches),
            },
            {
                "check": "all_primary_units_timestamped_after_admin",
                "passed": int(summary["poe_after_admin_units_n"])
                == int(summary["primary_order_units_n"]),
                "detail": (
                    f"{int(summary['poe_after_admin_units_n'])}/"
                    f"{int(summary['primary_order_units_n'])}"
                ),
            },
        ]
        validation = pd.DataFrame(checks)
        validation.to_csv(
            QA / "poe_temporal_mechanism_validation.csv",
            index=False,
            encoding="utf-8-sig",
        )
        if not bool(validation["passed"].all()):
            raise RuntimeError(f"POE mechanism validation failed:\n{validation}")

        raw_after = {path.name: source_state(path) for path in raw_sources}
        if raw_before != raw_after:
            raise RuntimeError("A raw MIMIC source changed during POE diagnostics")

        manifest = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "script": Path(__file__).name,
            "script_sha256": sha256(Path(__file__)),
            "contract_sha256": observed_contract_hash,
            "base_database_read_only": True,
            "raw_sources_before": raw_before,
            "raw_sources_after": raw_after,
            "row_level_replication_units_n": row_units,
            "primary_order_units_n": int(primary_units),
            "primary_linked_stays_n": int(primary_stays),
            "raw_direct_poe_rows_n": int(direct_rows),
            "linked_primary_units_n": int(linked_units),
            "one_hop_reference_keys_n": reference_key_n,
            "checkpoint_rows_n": int(checkpoints.shape[0]),
            "row_field_distribution_rows_n": int(row_distribution.shape[0]),
            "unit_field_distribution_rows_n": int(unit_distribution.shape[0]),
            "timing_summary_rows_n": int(timing_summary.shape[0]),
            "discharge_bin_rows_n": int(discharge_bins.shape[0]),
            "discontinuation_rows_n": int(discontinuation.shape[0]),
            "multiplicity_rows_n": int(multiplicity.shape[0]),
            "multirow_combination_rows_n": int(multirow.shape[0]),
            "validation_passed": bool(validation["passed"].all()),
            "elapsed_seconds": time.time() - started,
        }
        (MANIFESTS / "42_poe_temporal_mechanism_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (ENVIRONMENT / "Python_sessionInfo_poe_temporal_mechanism.txt").write_text(
            "\n".join(
                [
                    f"timestamp={manifest['generated_at']}",
                    f"python={sys.version}",
                    f"platform={platform.platform()}",
                    f"duckdb={duckdb.__version__}",
                    f"pandas={pd.__version__}",
                    f"script={Path(__file__).name}",
                    f"script_sha256={manifest['script_sha256']}",
                    f"contract_sha256={observed_contract_hash}",
                    "raw_sources_modified=false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        log("PASS POE temporal-mechanism audit complete")
        print(json.dumps(manifest, indent=2, ensure_ascii=False), flush=True)
    finally:
        con.close()


if __name__ == "__main__":
    main()
