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
TMP = PROJECT / "cache" / "jamia_cross_poe_pairing_tmp"
OUTPUT = PROJECT / "outputs" / "jamia_residual_provenance_v1_0"
TABLES = OUTPUT / "tables"
LOGS = OUTPUT / "logs"
PLANS = OUTPUT / "plans"
MANIFESTS = OUTPUT / "manifests"
QA = OUTPUT / "qa"
ENVIRONMENT = PROJECT / "environment"
MIMIC = Path(os.environ["MIMIC_IV_ROOT"])
CONTRACT = (
    PROJECT / "contracts" / "jamia_cross_poe_pairing_addendum_v1.0_2026-08-01.md"
)
EXPECTED_CONTRACT_SHA256 = (
    "4fe73818ca3b3e9d6bb21142f65693b9a8f05e7844420a38c40bbb1ee2bfc873"
)

for directory in (TMP, TABLES, LOGS, PLANS, MANIFESTS, QA, ENVIRONMENT):
    directory.mkdir(parents=True, exist_ok=True)

LOG_PATH = LOGS / "43_build_cross_poe_pairing_audit.log"


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
) -> None:
    started = time.time()
    log(f"START {name}")
    con.execute(sql)
    rows = None
    if table:
        rows = int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    log(
        f"DONE {name} rows={rows} elapsed_seconds={time.time() - started:.3f}"
    )


def export_query(
    con: duckdb.DuckDBPyConnection, query: str, filename: str
) -> pd.DataFrame:
    frame = con.execute(query).fetchdf()
    frame.to_csv(TABLES / filename, index=False, encoding="utf-8-sig")
    log(f"CHECKPOINT file={filename} rows={len(frame)}")
    return frame


def main() -> None:
    started = time.time()
    contract_hash = sha256(CONTRACT)
    if contract_hash != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError(f"Cross-POE contract mismatch: {contract_hash}")
    for path in (BASE_DB, SCRATCH_DB):
        if not path.exists():
            raise FileNotFoundError(path)

    poe_path = MIMIC / "hosp" / "poe.csv.gz"
    raw_before = source_state(poe_path)
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
    poe_scan = explicit_csv(poe_path, poe_columns)

    con = duckdb.connect(str(SCRATCH_DB))
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{sql_path(TMP)}'")
    try:
        con.execute(f"ATTACH '{sql_path(BASE_DB)}' AS base (READ_ONLY)")

        run_step(
            con,
            "enumerate exact eMAR/prescription POE pairs",
            """
            CREATE OR REPLACE TABLE a2_cross_poe_pairs AS
            SELECT DISTINCT u.subject_id, u.hadm_id, u.stay_id,
                   u.pharmacy_id, u.prescription_poe_id,
                   nullif(trim(l.emar_poe_id), '') AS emar_poe_id,
                   u.first_linked_admin, u.prescription_starttime,
                   u.prescription_rows_n
            FROM a2_poe_order_units u
            JOIN a2_residual_linked_prescription_rows l
              ON u.subject_id = l.subject_id
             AND u.hadm_id = l.hadm_id
             AND u.stay_id = l.stay_id
             AND u.pharmacy_id = l.pharmacy_id
             AND u.prescription_poe_id = l.prescription_poe_id
            WHERE nullif(trim(l.emar_poe_id), '') IS NOT NULL
            """,
            "a2_cross_poe_pairs",
        )
        pair_rows, pair_units, pair_stays, emar_poes = con.execute(
            """
            SELECT count(*),
                   count(DISTINCT (stay_id, pharmacy_id, prescription_poe_id)),
                   count(DISTINCT stay_id), count(DISTINCT emar_poe_id)
            FROM a2_cross_poe_pairs
            """
        ).fetchone()
        if int(pair_units) != 183 or int(pair_stays) != 183:
            raise RuntimeError(
                f"Paired-unit gate failed: rows={pair_rows}, units={pair_units}, "
                f"stays={pair_stays}"
            )

        emar_poe_query = f"""
            SELECT k.subject_id, k.hadm_id, k.stay_id, k.pharmacy_id,
                   k.prescription_poe_id, k.emar_poe_id,
                   k.first_linked_admin, k.prescription_starttime,
                   TRY_CAST(p.poe_seq AS BIGINT) AS poe_seq,
                   TRY_CAST(p.ordertime AS TIMESTAMP) AS emar_poe_ordertime,
                   nullif(trim(p.order_type), '') AS emar_poe_order_type,
                   nullif(trim(p.order_subtype), '') AS emar_poe_order_subtype,
                   nullif(trim(p.transaction_type), '')
                     AS emar_poe_transaction_type,
                   nullif(trim(p.discontinue_of_poe_id), '')
                     AS emar_poe_discontinue_of,
                   nullif(trim(p.discontinued_by_poe_id), '')
                     AS emar_poe_discontinued_by,
                   nullif(trim(p.order_status), '') AS emar_poe_order_status
            FROM a2_cross_poe_pairs k
            JOIN {poe_scan} p
              ON TRY_CAST(p.subject_id AS BIGINT) = k.subject_id
             AND TRY_CAST(p.hadm_id AS BIGINT) = k.hadm_id
             AND p.poe_id = k.emar_poe_id
        """
        save_plan(con, "a2_cross_poe_emar_rows_explain", emar_poe_query)
        pilot_query = emar_poe_query.replace(
            "FROM a2_cross_poe_pairs k",
            "FROM (SELECT * FROM a2_cross_poe_pairs "
            "ORDER BY stay_id, pharmacy_id LIMIT 20) k",
            1,
        )
        run_step(
            con,
            "20-unit paired eMAR-POE pilot",
            "CREATE OR REPLACE TEMP TABLE a2_cross_poe_pilot AS " + pilot_query,
            "a2_cross_poe_pilot",
        )
        pilot_rows = int(
            con.execute("SELECT count(*) FROM a2_cross_poe_pilot").fetchone()[0]
        )
        if pilot_rows > 2000:
            raise RuntimeError(f"Unsafe paired pilot multiplicity: {pilot_rows}")

        run_step(
            con,
            "materialize exact raw eMAR-POE rows",
            "CREATE OR REPLACE TABLE a2_cross_poe_emar_rows AS " + emar_poe_query,
            "a2_cross_poe_emar_rows",
        )
        emar_raw_rows, emar_linked_units = con.execute(
            """
            SELECT count(*),
                   count(DISTINCT (stay_id, pharmacy_id, prescription_poe_id))
            FROM a2_cross_poe_emar_rows
            """
        ).fetchone()

        run_step(
            con,
            "aggregate paired POE roles",
            """
            CREATE OR REPLACE TABLE a2_cross_poe_unit_facts AS
            WITH e AS (
              SELECT subject_id, hadm_id, stay_id, pharmacy_id,
                     prescription_poe_id,
                     count(DISTINCT emar_poe_id) AS emar_poe_ids_n,
                     string_agg(DISTINCT emar_poe_id, ' | ' ORDER BY emar_poe_id)
                       AS emar_poe_ids,
                     min(first_linked_admin) AS first_linked_admin,
                     min(prescription_starttime) AS prescription_starttime,
                     min(emar_poe_ordertime) AS first_emar_poe_ordertime,
                     string_agg(DISTINCT coalesce(emar_poe_order_type, '<blank>'),
                                ' | ' ORDER BY coalesce(emar_poe_order_type, '<blank>'))
                       AS emar_poe_order_type_values,
                     string_agg(DISTINCT coalesce(emar_poe_transaction_type, '<blank>'),
                                ' | ' ORDER BY coalesce(emar_poe_transaction_type, '<blank>'))
                       AS emar_poe_transaction_type_values,
                     string_agg(DISTINCT coalesce(emar_poe_order_status, '<blank>'),
                                ' | ' ORDER BY coalesce(emar_poe_order_status, '<blank>'))
                       AS emar_poe_order_status_values,
                     bool_or(emar_poe_discontinue_of = prescription_poe_id)
                       AS emar_discontinues_prescription_poe,
                     bool_or(emar_poe_discontinued_by = prescription_poe_id)
                       AS emar_discontinued_by_prescription_poe
              FROM a2_cross_poe_emar_rows
              GROUP BY subject_id, hadm_id, stay_id, pharmacy_id,
                       prescription_poe_id
            ), p AS (
              SELECT subject_id, hadm_id, stay_id, pharmacy_id,
                     prescription_poe_id, first_poe_ordertime,
                     order_type_values AS prescription_poe_order_type_values,
                     transaction_type_values
                       AS prescription_poe_transaction_type_values,
                     order_status_values AS prescription_poe_order_status_values,
                     bool_or(discontinue_of_poe_id IN (
                       SELECT emar_poe_id FROM a2_cross_poe_pairs x
                       WHERE x.subject_id = r.subject_id
                         AND x.hadm_id = r.hadm_id
                         AND x.stay_id = r.stay_id
                         AND x.pharmacy_id = r.pharmacy_id
                         AND x.prescription_poe_id = r.prescription_poe_id
                     )) AS prescription_discontinues_emar_poe,
                     bool_or(discontinued_by_poe_id IN (
                       SELECT emar_poe_id FROM a2_cross_poe_pairs x
                       WHERE x.subject_id = r.subject_id
                         AND x.hadm_id = r.hadm_id
                         AND x.stay_id = r.stay_id
                         AND x.pharmacy_id = r.pharmacy_id
                         AND x.prescription_poe_id = r.prescription_poe_id
                     )) AS prescription_discontinued_by_emar_poe
              FROM a2_poe_direct_rows r
              JOIN a2_poe_unit_facts u
                USING (subject_id, hadm_id, stay_id, pharmacy_id,
                       prescription_poe_id)
              GROUP BY subject_id, hadm_id, stay_id, pharmacy_id,
                       prescription_poe_id, first_poe_ordertime,
                       order_type_values, transaction_type_values,
                       order_status_values
            )
            SELECT e.*, p.first_poe_ordertime,
                   p.prescription_poe_order_type_values,
                   p.prescription_poe_transaction_type_values,
                   p.prescription_poe_order_status_values,
                   e.emar_discontinues_prescription_poe,
                   e.emar_discontinued_by_prescription_poe,
                   p.prescription_discontinues_emar_poe,
                   p.prescription_discontinued_by_emar_poe,
                   date_diff('minute', e.first_linked_admin,
                             e.first_emar_poe_ordertime) / 60.0
                     AS emar_poe_minus_admin_hours,
                   date_diff('minute', e.first_linked_admin,
                             p.first_poe_ordertime) / 60.0
                     AS prescription_poe_minus_admin_hours,
                   date_diff('minute', e.first_emar_poe_ordertime,
                             p.first_poe_ordertime) / 60.0
                     AS prescription_minus_emar_poe_hours
            FROM e JOIN p
              USING (subject_id, hadm_id, stay_id, pharmacy_id,
                     prescription_poe_id)
            """,
            "a2_cross_poe_unit_facts",
        )

        run_step(
            con,
            "resolve eMAR POE to prescription and pharmacy records",
            """
            CREATE OR REPLACE TABLE a2_emar_poe_resolution AS
            WITH exact_rx AS (
              SELECT x.subject_id, x.hadm_id, x.stay_id, x.pharmacy_id,
                     x.prescription_poe_id, x.emar_poe_id,
                     count(*) AS exact_poe_prescription_rows_n,
                     bool_or(p.pharmacy_id = x.pharmacy_id)
                       AS any_same_pharmacy_id,
                     bool_or(p.pharmacy_id <> x.pharmacy_id)
                       AS any_different_pharmacy_id,
                     count(DISTINCT p.pharmacy_id) AS exact_poe_pharmacy_ids_n
              FROM a2_cross_poe_pairs x
              JOIN base.prescription_candidates p
                ON x.subject_id = p.subject_id
               AND x.hadm_id = p.hadm_id
               AND x.emar_poe_id = p.poe_id
              GROUP BY x.subject_id, x.hadm_id, x.stay_id, x.pharmacy_id,
                       x.prescription_poe_id, x.emar_poe_id
            ), exact_pharm AS (
              SELECT x.subject_id, x.hadm_id, x.stay_id, x.pharmacy_id,
                     x.prescription_poe_id, x.emar_poe_id,
                     count(*) AS exact_poe_pharmacy_rows_n,
                     bool_or(p.pharmacy_id = x.pharmacy_id)
                       AS any_pharmacy_row_same_id,
                     bool_or(p.pharmacy_id <> x.pharmacy_id)
                       AS any_pharmacy_row_different_id
              FROM a2_cross_poe_pairs x
              JOIN base.s02v2_raw_pharmacy_keys p
                ON x.subject_id = p.subject_id
               AND x.hadm_id = p.hadm_id
               AND x.emar_poe_id = p.poe_id
              GROUP BY x.subject_id, x.hadm_id, x.stay_id, x.pharmacy_id,
                       x.prescription_poe_id, x.emar_poe_id
            )
            SELECT x.*,
                   coalesce(r.exact_poe_prescription_rows_n, 0)
                     AS exact_poe_prescription_rows_n,
                   coalesce(r.any_same_pharmacy_id, false)
                     AS any_prescription_same_pharmacy_id,
                   coalesce(r.any_different_pharmacy_id, false)
                     AS any_prescription_different_pharmacy_id,
                   coalesce(r.exact_poe_pharmacy_ids_n, 0)
                     AS exact_poe_pharmacy_ids_n,
                   coalesce(f.exact_poe_pharmacy_rows_n, 0)
                     AS exact_poe_pharmacy_rows_n,
                   coalesce(f.any_pharmacy_row_same_id, false)
                     AS any_pharmacy_row_same_id,
                   coalesce(f.any_pharmacy_row_different_id, false)
                     AS any_pharmacy_row_different_id
            FROM a2_cross_poe_pairs x
            LEFT JOIN exact_rx r
              USING (subject_id, hadm_id, stay_id, pharmacy_id,
                     prescription_poe_id, emar_poe_id)
            LEFT JOIN exact_pharm f
              USING (subject_id, hadm_id, stay_id, pharmacy_id,
                     prescription_poe_id, emar_poe_id)
            """,
            "a2_emar_poe_resolution",
        )

        checkpoints = export_query(
            con,
            """
            SELECT 'primary pharmacy-prescription POE units' AS checkpoint,
                   count(*) AS rows_n, count(DISTINCT stay_id) AS stays_n
            FROM a2_poe_order_units
            UNION ALL
            SELECT 'distinct eMAR/prescription POE pairs', count(*),
                   count(DISTINCT stay_id) FROM a2_cross_poe_pairs
            UNION ALL
            SELECT 'raw eMAR-POE rows', count(*), count(DISTINCT stay_id)
            FROM a2_cross_poe_emar_rows
            UNION ALL
            SELECT 'paired unit facts', count(*), count(DISTINCT stay_id)
            FROM a2_cross_poe_unit_facts
            UNION ALL
            SELECT 'eMAR-POE exact-source resolutions', count(*),
                   count(DISTINCT stay_id) FROM a2_emar_poe_resolution
            """,
            "a2_cross_poe_checkpoint_cardinality.csv",
        )

        role_fields = export_query(
            con,
            """
            WITH long AS (
              SELECT unnest(['eMAR POE','eMAR POE','eMAR POE',
                             'prescription POE','prescription POE',
                             'prescription POE']) AS poe_role,
                     unnest(['order_type','transaction_type','order_status',
                             'order_type','transaction_type','order_status'])
                       AS field,
                     unnest([emar_poe_order_type_values,
                             emar_poe_transaction_type_values,
                             emar_poe_order_status_values,
                             prescription_poe_order_type_values,
                             prescription_poe_transaction_type_values,
                             prescription_poe_order_status_values]) AS value
              FROM a2_cross_poe_unit_facts
            )
            SELECT poe_role, field, value,
                   count(*) AS primary_order_units_n,
                   round(100.0 * count(*) /
                         sum(count(*)) OVER (PARTITION BY poe_role, field), 4)
                     AS pct
            FROM long GROUP BY poe_role, field, value
            ORDER BY poe_role, field, primary_order_units_n DESC, value
            """,
            "a2_cross_poe_field_distribution.csv",
        )

        timing = export_query(
            con,
            """
            WITH long AS (
              SELECT unnest(['eMAR POE ordertime minus first administration',
                             'prescription POE ordertime minus first administration',
                             'prescription POE ordertime minus eMAR POE ordertime'])
                       AS timing_metric,
                     unnest([emar_poe_minus_admin_hours,
                             prescription_poe_minus_admin_hours,
                             prescription_minus_emar_poe_hours]) AS hours
              FROM a2_cross_poe_unit_facts
            )
            SELECT timing_metric, count(hours) AS primary_order_units_n,
                   min(hours) AS min_h,
                   quantile_cont(hours, 0.25) AS q1_h,
                   median(hours) AS median_h,
                   quantile_cont(hours, 0.75) AS q3_h,
                   max(hours) AS max_h
            FROM long GROUP BY timing_metric ORDER BY timing_metric
            """,
            "a2_cross_poe_timing_summary.csv",
        )

        chain = export_query(
            con,
            """
            WITH long AS (
              SELECT unnest([
                'eMAR POE discontinue_of = prescription POE',
                'eMAR POE discontinued_by = prescription POE',
                'prescription POE discontinue_of = eMAR POE',
                'prescription POE discontinued_by = eMAR POE'
              ]) AS cross_reference,
              unnest([emar_discontinues_prescription_poe,
                      emar_discontinued_by_prescription_poe,
                      prescription_discontinues_emar_poe,
                      prescription_discontinued_by_emar_poe]) AS present
              FROM a2_cross_poe_unit_facts
            )
            SELECT cross_reference,
                   count(*) FILTER (WHERE present) AS primary_order_units_n,
                   round(100.0 * count(*) FILTER (WHERE present) / count(*), 4)
                     AS pct
            FROM long GROUP BY cross_reference ORDER BY cross_reference
            """,
            "a2_cross_poe_chain_reference_summary.csv",
        )

        resolution = export_query(
            con,
            """
            SELECT count(*) AS emar_poe_pairs_n,
                   count(DISTINCT stay_id) AS linked_stays_n,
                   count(*) FILTER (WHERE exact_poe_prescription_rows_n > 0)
                     AS pairs_with_exact_poe_prescription_n,
                   count(*) FILTER (WHERE any_prescription_same_pharmacy_id)
                     AS pairs_with_same_pharmacy_prescription_n,
                   count(*) FILTER (WHERE any_prescription_different_pharmacy_id)
                     AS pairs_with_different_pharmacy_prescription_n,
                   count(*) FILTER (WHERE exact_poe_pharmacy_rows_n > 0)
                     AS pairs_with_exact_poe_pharmacy_n,
                   count(*) FILTER (WHERE any_pharmacy_row_same_id)
                     AS pairs_with_same_pharmacy_row_n,
                   count(*) FILTER (WHERE any_pharmacy_row_different_id)
                     AS pairs_with_different_pharmacy_row_n
            FROM a2_emar_poe_resolution
            """,
            "a2_emar_poe_exact_source_resolution_summary.csv",
        )

        mechanism = export_query(
            con,
            """
            SELECT count(*) AS primary_order_units_n,
                   count(DISTINCT stay_id) AS linked_stays_n,
                   sum(emar_poe_ids_n) AS distinct_emar_poe_links_n,
                   count(*) FILTER (
                     WHERE first_emar_poe_ordertime <= first_linked_admin
                   ) AS emar_poe_by_admin_units_n,
                   count(*) FILTER (
                     WHERE first_poe_ordertime > first_linked_admin
                   ) AS prescription_poe_after_admin_units_n,
                   count(*) FILTER (
                     WHERE first_emar_poe_ordertime < first_poe_ordertime
                   ) AS emar_poe_earlier_than_prescription_poe_n,
                   median(emar_poe_minus_admin_hours)
                     AS emar_poe_minus_admin_median_h,
                   median(prescription_poe_minus_admin_hours)
                     AS prescription_poe_minus_admin_median_h,
                   median(prescription_minus_emar_poe_hours)
                     AS prescription_minus_emar_poe_median_h,
                   count(*) FILTER (
                     WHERE emar_discontinues_prescription_poe
                        OR emar_discontinued_by_prescription_poe
                        OR prescription_discontinues_emar_poe
                        OR prescription_discontinued_by_emar_poe
                   ) AS directly_cross_referenced_units_n
            FROM a2_cross_poe_unit_facts
            """,
            "a2_cross_poe_mechanism_summary.csv",
        )

        mechanism_row = mechanism.iloc[0]
        validation = pd.DataFrame(
            [
                {
                    "check": "contract_hash_match",
                    "passed": contract_hash == EXPECTED_CONTRACT_SHA256,
                    "detail": contract_hash,
                },
                {
                    "check": "primary_pair_units_183",
                    "passed": int(pair_units) == 183,
                    "detail": str(pair_units),
                },
                {
                    "check": "all_pair_units_link_raw_emar_poe",
                    "passed": int(emar_linked_units) == int(pair_units),
                    "detail": f"{emar_linked_units}/{pair_units}",
                },
                {
                    "check": "paired_unit_facts_complete",
                    "passed": int(mechanism_row["primary_order_units_n"])
                    == int(pair_units),
                    "detail": (
                        f"{int(mechanism_row['primary_order_units_n'])}/"
                        f"{int(pair_units)}"
                    ),
                },
            ]
        )
        validation.to_csv(
            QA / "cross_poe_pairing_validation.csv",
            index=False,
            encoding="utf-8-sig",
        )
        if not bool(validation["passed"].all()):
            raise RuntimeError(f"Cross-POE validation failed:\n{validation}")

        raw_after = source_state(poe_path)
        if raw_before != raw_after:
            raise RuntimeError("Raw POE source changed during paired audit")

        manifest = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "script": Path(__file__).name,
            "script_sha256": sha256(Path(__file__)),
            "contract_sha256": contract_hash,
            "base_database_read_only": True,
            "raw_poe_before": raw_before,
            "raw_poe_after": raw_after,
            "pair_rows_n": int(pair_rows),
            "pair_primary_units_n": int(pair_units),
            "pair_stays_n": int(pair_stays),
            "distinct_emar_poe_ids_n": int(emar_poes),
            "raw_emar_poe_rows_n": int(emar_raw_rows),
            "linked_primary_units_n": int(emar_linked_units),
            "checkpoint_rows_n": int(checkpoints.shape[0]),
            "field_distribution_rows_n": int(role_fields.shape[0]),
            "timing_summary_rows_n": int(timing.shape[0]),
            "chain_summary_rows_n": int(chain.shape[0]),
            "resolution_summary_rows_n": int(resolution.shape[0]),
            "validation_passed": bool(validation["passed"].all()),
            "elapsed_seconds": time.time() - started,
        }
        (MANIFESTS / "43_cross_poe_pairing_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (ENVIRONMENT / "Python_sessionInfo_cross_poe_pairing.txt").write_text(
            "\n".join(
                [
                    f"timestamp={manifest['generated_at']}",
                    f"python={sys.version}",
                    f"platform={platform.platform()}",
                    f"duckdb={duckdb.__version__}",
                    f"pandas={pd.__version__}",
                    f"script={Path(__file__).name}",
                    f"script_sha256={manifest['script_sha256']}",
                    f"contract_sha256={contract_hash}",
                    "raw_sources_modified=false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        log("PASS cross-POE pairing audit complete")
        print(json.dumps(manifest, indent=2, ensure_ascii=False), flush=True)
    finally:
        con.close()


if __name__ == "__main__":
    main()
