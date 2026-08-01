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
PRIOR_DB = PROJECT / "cache" / "jamia_prereview_upgrade_v1_0.duckdb"
SCRATCH_DB = PROJECT / "cache" / "jamia_residual_provenance_v1_0.duckdb"
TMP = PROJECT / "cache" / "jamia_residual_provenance_tmp"
OUTPUT = PROJECT / "outputs" / "jamia_residual_provenance_v1_0"
TABLES = OUTPUT / "tables"
LOGS = OUTPUT / "logs"
PLANS = OUTPUT / "plans"
MANIFESTS = OUTPUT / "manifests"
ENVIRONMENT = PROJECT / "environment"
MIMIC = Path(os.environ["MIMIC_IV_ROOT"])
CONTRACT = (
    PROJECT
    / "contracts"
    / "jamia_residual_provenance_addendum_v1.0_2026-07-31.md"
)
EXPECTED_CONTRACT_SHA256 = (
    "af533e4d3a9b636c368dc6c76cc3e3ea472c77f9884476520d341ae09575dcfd"
)

for directory in (TMP, TABLES, LOGS, PLANS, MANIFESTS, ENVIRONMENT):
    directory.mkdir(parents=True, exist_ok=True)

LOG_PATH = LOGS / "34_build_residual_provenance_diagnostics.log"


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
    return {
        "path": str(path),
        "bytes": item.st_size,
        "mtime_ns": item.st_mtime_ns,
    }


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
    started = time.time()
    observed_hash = sha256(CONTRACT)
    if observed_hash != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError(
            f"Residual-provenance contract mismatch: {observed_hash}"
        )
    for database in (BASE_DB, PRIOR_DB):
        if not database.exists():
            raise FileNotFoundError(database)
    log("PASS residual-provenance contract hash")

    raw_sources = [
        MIMIC / "hosp" / "pharmacy.csv.gz",
        MIMIC / "hosp" / "prescriptions.csv.gz",
        MIMIC / "hosp" / "emar.csv.gz",
    ]
    raw_before = {path.name: source_state(path) for path in raw_sources}

    con = duckdb.connect(str(SCRATCH_DB))
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{sql_path(TMP)}'")
    try:
        con.execute(f"ATTACH '{sql_path(BASE_DB)}' AS base (READ_ONLY)")
        con.execute(f"ATTACH '{sql_path(PRIOR_DB)}' AS prior (READ_ONLY)")

        run_step(
            con,
            "freeze 184-stay A2 residual population",
            """
            CREATE OR REPLACE TABLE a2_residual_stays AS
            SELECT w.subject_id, w.hadm_id, w.stay_id, w.outcome,
                   a.intime, a.outtime
            FROM prior.a2_window_provenance w
            JOIN prior.a2_upgrade_input a USING (stay_id)
            WHERE w.provenance_category =
              'no_hospital_overlap_ppi_order_in_admission'
            """,
            "a2_residual_stays",
        )
        residual_n, residual_unique = con.execute(
            "SELECT count(*), count(DISTINCT stay_id) FROM a2_residual_stays"
        ).fetchone()
        if (int(residual_n), int(residual_unique)) != (184, 184):
            raise RuntimeError(
                f"Residual-population gate failed: rows={residual_n}, "
                f"unique={residual_unique}"
            )

        event_query = """
            SELECT * EXCLUDE (rn) FROM (
              SELECT e.subject_id, e.hadm_id, e.stay_id,
                     e.emar_id, e.emar_seq, e.poe_id, e.pharmacy_id,
                     e.charttime, e.medication, e.ingredient,
                     e.name_match_source, e.product_description,
                     e.product_description_other, e.route,
                     e.dose_given_num, e.dose_given_unit,
                     row_number() OVER (
                       PARTITION BY e.stay_id, e.emar_id, e.emar_seq
                       ORDER BY e.charttime
                     ) AS rn
              FROM base.emar_stay_events e
              JOIN a2_residual_stays s
                ON e.subject_id = s.subject_id
               AND e.hadm_id = s.hadm_id
               AND e.stay_id = s.stay_id
              WHERE e.drug_class = 'stress_ulcer_prophylaxis'
                AND e.subclass = 'PPI'
                AND e.event_category = 'given_strict'
                AND e.charttime BETWEEN s.intime
                                    AND least(s.outtime,
                                              s.intime + INTERVAL 48 HOUR)
            ) WHERE rn = 1
        """
        save_plan(con, "a2_residual_emar_events_explain", event_query)
        run_step(
            con,
            "materialize all qualifying A2 residual eMAR events",
            "CREATE OR REPLACE TABLE a2_residual_emar_events AS " + event_query,
            "a2_residual_emar_events",
        )
        event_n, event_stays = con.execute(
            """
            SELECT count(*), count(DISTINCT stay_id)
            FROM a2_residual_emar_events
            """
        ).fetchone()
        if int(event_stays) != 184 or int(event_n) < 184:
            raise RuntimeError(
                f"Residual-event gate failed: events={event_n}, stays={event_stays}"
            )

        raw_pharmacy_query = """
            SELECT e.stay_id, e.emar_id, e.emar_seq,
                   count(*) AS raw_pharmacy_rows_n,
                   count(DISTINCT nullif(trim(p.poe_id), ''))
                     AS raw_pharmacy_poe_ids_n,
                   bool_or(
                     nullif(trim(p.poe_id), '') = nullif(trim(e.poe_id), '')
                   ) AS any_pharmacy_poe_matches_emar_poe
            FROM a2_residual_emar_events e
            JOIN base.s02v2_raw_pharmacy_keys p
              ON e.subject_id = p.subject_id
             AND e.hadm_id = p.hadm_id
             AND e.pharmacy_id = p.pharmacy_id
            WHERE nullif(trim(e.pharmacy_id), '') IS NOT NULL
            GROUP BY e.stay_id, e.emar_id, e.emar_seq
        """
        mapped_pharmacy_query = """
            SELECT e.stay_id, e.emar_id, e.emar_seq,
                   count(*) AS mapped_pharmacy_rows_n,
                   count(*) FILTER (
                     WHERE p.drug_class = 'stress_ulcer_prophylaxis'
                       AND p.subclass = 'PPI'
                   ) AS ppi_pharmacy_rows_n,
                   count(DISTINCT p.pharmacy_medication) FILTER (
                     WHERE p.drug_class = 'stress_ulcer_prophylaxis'
                       AND p.subclass = 'PPI'
                   ) AS ppi_pharmacy_strings_n
            FROM a2_residual_emar_events e
            JOIN base.pharmacy_name_candidates p
              ON e.subject_id = p.subject_id
             AND e.hadm_id = p.hadm_id
             AND e.pharmacy_id = p.pharmacy_id
            WHERE nullif(trim(e.pharmacy_id), '') IS NOT NULL
            GROUP BY e.stay_id, e.emar_id, e.emar_seq
        """
        raw_prescription_query = """
            SELECT e.stay_id, e.emar_id, e.emar_seq,
                   count(*) AS raw_prescription_rows_n,
                   count(DISTINCT nullif(trim(p.poe_id), ''))
                     AS raw_prescription_poe_ids_n,
                   count(*) FILTER (
                     WHERE nullif(trim(p.route), '') IS NOT NULL
                   ) AS raw_prescription_route_rows_n
            FROM a2_residual_emar_events e
            JOIN base.s02v2_prescriptions_projected p
              ON e.subject_id = p.subject_id
             AND e.hadm_id = p.hadm_id
             AND e.pharmacy_id = p.pharmacy_id
            WHERE nullif(trim(e.pharmacy_id), '') IS NOT NULL
            GROUP BY e.stay_id, e.emar_id, e.emar_seq
        """
        direct_ppi_prescription_query = """
            SELECT e.stay_id, e.emar_id, e.emar_seq,
                   count(*) AS direct_ppi_prescription_rows_n,
                   count(DISTINCT nullif(trim(p.poe_id), ''))
                     AS direct_ppi_prescription_poe_ids_n
            FROM a2_residual_emar_events e
            JOIN base.prescription_candidates p
              ON e.subject_id = p.subject_id
             AND e.hadm_id = p.hadm_id
             AND e.pharmacy_id = p.pharmacy_id
            WHERE nullif(trim(e.pharmacy_id), '') IS NOT NULL
              AND p.drug_class = 'stress_ulcer_prophylaxis'
              AND p.subclass = 'PPI'
            GROUP BY e.stay_id, e.emar_id, e.emar_seq
        """
        for name, query in [
            ("a2_direct_raw_pharmacy_explain", raw_pharmacy_query),
            ("a2_direct_mapped_pharmacy_explain", mapped_pharmacy_query),
            ("a2_direct_raw_prescription_explain", raw_prescription_query),
            ("a2_direct_ppi_prescription_explain", direct_ppi_prescription_query),
        ]:
            save_plan(con, name, query)

        pilot_tables = []
        for name, query in [
            ("pilot_raw_pharmacy", raw_pharmacy_query),
            ("pilot_mapped_pharmacy", mapped_pharmacy_query),
            ("pilot_raw_prescription", raw_prescription_query),
            ("pilot_direct_ppi_prescription", direct_ppi_prescription_query),
        ]:
            pilot_query = query.replace(
                "FROM a2_residual_emar_events e",
                "FROM (SELECT * FROM a2_residual_emar_events "
                "ORDER BY stay_id, charttime LIMIT 20) e",
                1,
            )
            table_name = f"{name}_20"
            run_step(
                con,
                f"20-event {name} pilot",
                f"CREATE OR REPLACE TEMP TABLE {table_name} AS {pilot_query}",
                table_name,
            )
            pilot_tables.append(table_name)

        run_step(
            con,
            "preaggregate direct raw pharmacy links",
            "CREATE OR REPLACE TABLE a2_direct_raw_pharmacy AS "
            + raw_pharmacy_query,
            "a2_direct_raw_pharmacy",
        )
        run_step(
            con,
            "preaggregate direct mapped pharmacy links",
            "CREATE OR REPLACE TABLE a2_direct_mapped_pharmacy AS "
            + mapped_pharmacy_query,
            "a2_direct_mapped_pharmacy",
        )
        run_step(
            con,
            "preaggregate direct raw prescription links",
            "CREATE OR REPLACE TABLE a2_direct_raw_prescription AS "
            + raw_prescription_query,
            "a2_direct_raw_prescription",
        )
        run_step(
            con,
            "preaggregate direct PPI prescription links",
            "CREATE OR REPLACE TABLE a2_direct_ppi_prescription AS "
            + direct_ppi_prescription_query,
            "a2_direct_ppi_prescription",
        )

        pharmacy_poe_keys_query = """
            SELECT DISTINCT e.subject_id, e.hadm_id, e.stay_id,
                   e.emar_id, e.emar_seq,
                   nullif(trim(p.poe_id), '') AS pharmacy_poe_id
            FROM a2_residual_emar_events e
            JOIN base.s02v2_raw_pharmacy_keys p
              ON e.subject_id = p.subject_id
             AND e.hadm_id = p.hadm_id
             AND e.pharmacy_id = p.pharmacy_id
            WHERE nullif(trim(e.pharmacy_id), '') IS NOT NULL
              AND nullif(trim(p.poe_id), '') IS NOT NULL
        """
        save_plan(con, "a2_pharmacy_poe_keys_explain", pharmacy_poe_keys_query)
        run_step(
            con,
            "deduplicate pharmacy POE keys before prescription link",
            "CREATE OR REPLACE TABLE a2_pharmacy_poe_keys AS "
            + pharmacy_poe_keys_query,
            "a2_pharmacy_poe_keys",
        )

        pharmacy_poe_ppi_query = """
            SELECT k.stay_id, k.emar_id, k.emar_seq,
                   count(*) AS pharmacy_poe_ppi_prescription_rows_n,
                   count(DISTINCT k.pharmacy_poe_id)
                     AS pharmacy_poe_with_ppi_prescription_n
            FROM a2_pharmacy_poe_keys k
            JOIN base.prescription_candidates p
              ON k.subject_id = p.subject_id
             AND k.hadm_id = p.hadm_id
             AND k.pharmacy_poe_id = p.poe_id
            WHERE p.drug_class = 'stress_ulcer_prophylaxis'
              AND p.subclass = 'PPI'
            GROUP BY k.stay_id, k.emar_id, k.emar_seq
        """
        save_plan(con, "a2_pharmacy_poe_to_ppi_explain", pharmacy_poe_ppi_query)
        run_step(
            con,
            "preaggregate pharmacy-POE to PPI prescription links",
            "CREATE OR REPLACE TABLE a2_pharmacy_poe_ppi AS "
            + pharmacy_poe_ppi_query,
            "a2_pharmacy_poe_ppi",
        )

        admission_ppi_query = """
            SELECT s.stay_id, count(*) AS admission_ppi_prescription_rows_n,
                   count(DISTINCT nullif(trim(p.poe_id), ''))
                     AS admission_ppi_poe_ids_n,
                   min(p.starttime) AS first_admission_ppi_start,
                   max(p.stoptime) AS last_admission_ppi_stop
            FROM a2_residual_stays s
            JOIN base.prescription_candidates p
              ON s.subject_id = p.subject_id
             AND s.hadm_id = p.hadm_id
            WHERE p.drug_class = 'stress_ulcer_prophylaxis'
              AND p.subclass = 'PPI'
            GROUP BY s.stay_id
        """
        save_plan(con, "a2_any_admission_ppi_explain", admission_ppi_query)
        run_step(
            con,
            "preaggregate any mapped PPI prescription in admission",
            "CREATE OR REPLACE TABLE a2_any_admission_ppi AS "
            + admission_ppi_query,
            "a2_any_admission_ppi",
        )

        run_step(
            con,
            "assemble one-row-per-eMAR link facts",
            """
            CREATE OR REPLACE TABLE a2_residual_event_link_facts AS
            SELECT e.*,
                   coalesce(rp.raw_pharmacy_rows_n, 0)
                     AS raw_pharmacy_rows_n,
                   coalesce(mp.ppi_pharmacy_rows_n, 0)
                     AS ppi_pharmacy_rows_n,
                   coalesce(rr.raw_prescription_rows_n, 0)
                     AS raw_prescription_rows_n,
                   coalesce(dp.direct_ppi_prescription_rows_n, 0)
                     AS direct_ppi_prescription_rows_n,
                   coalesce(pp.pharmacy_poe_ppi_prescription_rows_n, 0)
                     AS pharmacy_poe_ppi_prescription_rows_n,
                   coalesce(ap.admission_ppi_prescription_rows_n, 0)
                     AS admission_ppi_prescription_rows_n,
                   coalesce(rp.raw_pharmacy_rows_n, 0) > 0
                     AS any_raw_pharmacy_link,
                   coalesce(mp.ppi_pharmacy_rows_n, 0) > 0
                     AS any_ppi_pharmacy_link,
                   coalesce(rr.raw_prescription_rows_n, 0) > 0
                     AS any_raw_prescription_link,
                   coalesce(dp.direct_ppi_prescription_rows_n, 0) > 0
                     AS any_direct_ppi_prescription_link,
                   coalesce(pp.pharmacy_poe_ppi_prescription_rows_n, 0) > 0
                     AS any_pharmacy_poe_ppi_prescription_link,
                   coalesce(ap.admission_ppi_prescription_rows_n, 0) > 0
                     AS any_admission_ppi_prescription
            FROM a2_residual_emar_events e
            LEFT JOIN a2_direct_raw_pharmacy rp
              USING (stay_id, emar_id, emar_seq)
            LEFT JOIN a2_direct_mapped_pharmacy mp
              USING (stay_id, emar_id, emar_seq)
            LEFT JOIN a2_direct_raw_prescription rr
              USING (stay_id, emar_id, emar_seq)
            LEFT JOIN a2_direct_ppi_prescription dp
              USING (stay_id, emar_id, emar_seq)
            LEFT JOIN a2_pharmacy_poe_ppi pp
              USING (stay_id, emar_id, emar_seq)
            LEFT JOIN a2_any_admission_ppi ap USING (stay_id)
            """,
            "a2_residual_event_link_facts",
        )
        fact_n, fact_unique = con.execute(
            """
            SELECT count(*), count(DISTINCT (stay_id, emar_id, emar_seq))
            FROM a2_residual_event_link_facts
            """
        ).fetchone()
        if int(fact_n) != int(fact_unique) or int(fact_n) != int(event_n):
            raise RuntimeError(
                f"Event-fact multiplicity gate failed: rows={fact_n}, "
                f"unique={fact_unique}, source={event_n}"
            )

        run_step(
            con,
            "classify each residual stay once",
            """
            CREATE OR REPLACE TABLE a2_residual_patient_classification AS
            WITH event_rollup AS (
              SELECT stay_id,
                     bool_or(any_direct_ppi_prescription_link)
                       AS direct_ppi,
                     bool_or(any_pharmacy_poe_ppi_prescription_link)
                       AS pharmacy_poe_ppi,
                     bool_or(any_admission_ppi_prescription)
                       AS admission_ppi,
                     bool_or(any_ppi_pharmacy_link) AS ppi_pharmacy,
                     bool_or(any_raw_pharmacy_link) AS raw_pharmacy,
                     bool_or(any_raw_prescription_link) AS raw_prescription,
                     count(*) AS qualifying_emar_events_n
              FROM a2_residual_event_link_facts GROUP BY stay_id
            )
            SELECT s.stay_id, s.outcome, r.qualifying_emar_events_n,
                   r.direct_ppi, r.pharmacy_poe_ppi, r.admission_ppi,
                   r.ppi_pharmacy, r.raw_pharmacy, r.raw_prescription,
                   CASE
                     WHEN r.direct_ppi
                       THEN 'direct_pharmacy_id_to_ppi_prescription'
                     WHEN r.pharmacy_poe_ppi
                       THEN 'pharmacy_poe_to_ppi_prescription'
                     WHEN r.admission_ppi
                       THEN 'ppi_prescription_elsewhere_in_admission'
                     WHEN r.ppi_pharmacy
                       THEN 'ppi_pharmacy_record_without_ppi_prescription'
                     WHEN r.raw_pharmacy
                       THEN 'pharmacy_record_without_mapped_ppi_prescription'
                     ELSE 'no_resolved_pharmacy_record_or_ppi_prescription'
                   END AS trace_category
            FROM a2_residual_stays s
            JOIN event_rollup r USING (stay_id)
            """,
            "a2_residual_patient_classification",
        )
        classified_n = int(
            con.execute(
                "SELECT count(*) FROM a2_residual_patient_classification"
            ).fetchone()[0]
        )
        if classified_n != 184:
            raise RuntimeError(f"Patient classification gate failed: {classified_n}")

        event_paths = export_query(
            con,
            """
            WITH paths AS (
              SELECT 'raw_pharmacy_id_link' AS link_path,
                     any_raw_pharmacy_link AS linked, stay_id
              FROM a2_residual_event_link_facts
              UNION ALL
              SELECT 'ppi_pharmacy_id_link', any_ppi_pharmacy_link, stay_id
              FROM a2_residual_event_link_facts
              UNION ALL
              SELECT 'raw_prescription_by_pharmacy_id',
                     any_raw_prescription_link, stay_id
              FROM a2_residual_event_link_facts
              UNION ALL
              SELECT 'ppi_prescription_by_pharmacy_id',
                     any_direct_ppi_prescription_link, stay_id
              FROM a2_residual_event_link_facts
              UNION ALL
              SELECT 'ppi_prescription_by_pharmacy_poe',
                     any_pharmacy_poe_ppi_prescription_link, stay_id
              FROM a2_residual_event_link_facts
              UNION ALL
              SELECT 'any_ppi_prescription_in_admission',
                     any_admission_ppi_prescription, stay_id
              FROM a2_residual_event_link_facts
            )
            SELECT link_path,
                   count(*) FILTER (WHERE linked) AS linked_events_n,
                   count(DISTINCT stay_id) FILTER (WHERE linked)
                     AS linked_patients_n,
                   count(*) AS eligible_events_n,
                   100.0 * count(*) FILTER (WHERE linked) / count(*)
                     AS linked_events_pct
            FROM paths GROUP BY link_path ORDER BY link_path
            """,
            TABLES / "a2_residual_event_link_path_summary.csv",
        )
        patient_summary = export_query(
            con,
            """
            SELECT trace_category, count(*) AS patients_n,
                   sum(outcome) AS deaths_90d_n,
                   100.0 * avg(outcome) AS death_90d_pct,
                   sum(qualifying_emar_events_n) AS qualifying_emar_events_n
            FROM a2_residual_patient_classification
            GROUP BY trace_category ORDER BY patients_n DESC, trace_category
            """,
            TABLES / "a2_residual_patient_trace_summary.csv",
        )
        medication_strings = export_query(
            con,
            """
            WITH counts AS (
              SELECT coalesce(nullif(trim(medication), ''), '<blank>')
                       AS emar_medication,
                     ingredient, name_match_source,
                     count(*) AS events_n,
                     count(DISTINCT stay_id) AS patients_n
              FROM a2_residual_emar_events
              GROUP BY emar_medication, ingredient, name_match_source
            ), ranked AS (
              SELECT *, row_number() OVER (
                       ORDER BY events_n DESC, emar_medication
                     ) AS frequency_rank,
                     100.0 * events_n / sum(events_n) OVER () AS events_pct
              FROM counts
            )
            SELECT frequency_rank, emar_medication, ingredient,
                   name_match_source, events_n, patients_n, events_pct,
                   sum(events_pct) OVER (
                     ORDER BY frequency_rank ROWS UNBOUNDED PRECEDING
                   ) AS cumulative_events_pct
            FROM ranked WHERE frequency_rank <= 10 ORDER BY frequency_rank
            """,
            TABLES / "a2_residual_emar_medication_top10.csv",
        )
        product_strings = export_query(
            con,
            """
            WITH values AS (
              SELECT nullif(trim(product_description), '') AS product_description,
                     stay_id
              FROM a2_residual_emar_events
              UNION ALL
              SELECT nullif(trim(product_description_other), ''), stay_id
              FROM a2_residual_emar_events
            ), counts AS (
              SELECT product_description, count(*) AS occurrences_n,
                     count(DISTINCT stay_id) AS patients_n
              FROM values WHERE product_description IS NOT NULL
              GROUP BY product_description
            )
            SELECT row_number() OVER (
                     ORDER BY occurrences_n DESC, product_description
                   ) AS frequency_rank,
                   product_description, occurrences_n, patients_n
            FROM counts
            QUALIFY frequency_rank <= 10
            ORDER BY frequency_rank
            """,
            TABLES / "a2_residual_product_description_top10.csv",
        )

        route_comparison = export_query(
            con,
            """
            WITH p AS (
              SELECT drug_class,
                     count(*) AS prescription_rows_n,
                     count(*) FILTER (
                       WHERE nullif(trim(route), '') IS NOT NULL
                     ) AS prescription_route_available_n,
                     100.0 * count(*) FILTER (
                       WHERE nullif(trim(route), '') IS NOT NULL
                     ) / count(*) AS prescription_route_available_pct,
                     count(DISTINCT lower(trim(route))) FILTER (
                       WHERE nullif(trim(route), '') IS NOT NULL
                     ) AS prescription_route_values_n
              FROM base.prescription_candidates GROUP BY drug_class
            ), o AS (
              SELECT drug_class,
                     count(*) AS eligible_order_units_n,
                     count(*) FILTER (
                       WHERE nullif(trim(route), '') IS NOT NULL
                     ) AS eligible_order_route_available_n,
                     100.0 * count(*) FILTER (
                       WHERE nullif(trim(route), '') IS NOT NULL
                     ) / count(*) AS eligible_order_route_available_pct
              FROM base.eligible_order_clusters GROUP BY drug_class
            ), e AS (
              SELECT drug_class,
                     count(*) AS strict_emar_events_n,
                     count(*) FILTER (
                       WHERE nullif(trim(route), '') IS NOT NULL
                     ) AS strict_emar_route_available_n,
                     100.0 * count(*) FILTER (
                       WHERE nullif(trim(route), '') IS NOT NULL
                     ) / count(*) AS strict_emar_route_available_pct
              FROM base.emar_stay_events
              WHERE event_category = 'given_strict'
              GROUP BY drug_class
            )
            SELECT p.drug_class, p.prescription_rows_n,
                   p.prescription_route_available_n,
                   p.prescription_route_available_pct,
                   p.prescription_route_values_n,
                   o.eligible_order_units_n,
                   o.eligible_order_route_available_n,
                   o.eligible_order_route_available_pct,
                   e.strict_emar_events_n,
                   e.strict_emar_route_available_n,
                   e.strict_emar_route_available_pct
            FROM p JOIN o USING (drug_class) JOIN e USING (drug_class)
            ORDER BY p.drug_class
            """,
            TABLES / "source_route_availability_by_class.csv",
        )
        a1_route = export_query(
            con,
            """
            WITH order_side AS (
              SELECT 'eligible order unit' AS source_layer,
                     count(*) AS records_n,
                     count(*) FILTER (
                       WHERE nullif(trim(o.route), '') IS NOT NULL
                     ) AS route_available_n,
                     count(*) FILTER (
                       WHERE regexp_matches(
                         lower(coalesce(o.route, '')),
                         'subcut|(^|[^a-z])(sc|sq)([^a-z]|$)'
                       )
                     ) AS subcutaneous_compatible_n
              FROM base.eligible_order_clusters o
              JOIN prior.a1_upgrade_input a USING (stay_id)
              WHERE o.drug_class = 'vte_prophylaxis'
                AND o.ingredient IN ('heparin', 'enoxaparin')
            ), admin_side AS (
              SELECT 'strict eMAR administration' AS source_layer,
                     count(*) AS records_n,
                     count(*) FILTER (
                       WHERE nullif(trim(route), '') IS NOT NULL
                     ) AS route_available_n,
                     count(*) FILTER (
                       WHERE regexp_matches(
                         lower(coalesce(route, '')),
                         'subcut|(^|[^a-z])(sc|sq)([^a-z]|$)'
                       )
                     ) AS subcutaneous_compatible_n
              FROM prior.a1_given_events
            )
            SELECT *, 100.0 * route_available_n / records_n
                       AS route_available_pct,
                     100.0 * subcutaneous_compatible_n / records_n
                       AS subcutaneous_compatible_pct
            FROM order_side
            UNION ALL
            SELECT *, 100.0 * route_available_n / records_n,
                     100.0 * subcutaneous_compatible_n / records_n
            FROM admin_side
            """,
            TABLES / "a1_order_vs_emar_route_availability.csv",
        )
        export_query(
            con,
            """
            WITH counts AS (
              SELECT lower(trim(o.route)) AS route,
                     count(*) AS order_units_n
              FROM base.eligible_order_clusters o
              JOIN prior.a1_upgrade_input a USING (stay_id)
              WHERE o.drug_class = 'vte_prophylaxis'
                AND o.ingredient IN ('heparin', 'enoxaparin')
                AND nullif(trim(o.route), '') IS NOT NULL
              GROUP BY lower(trim(o.route))
            )
            SELECT row_number() OVER (
                     ORDER BY order_units_n DESC, route
                   ) AS frequency_rank,
                   route, order_units_n
            FROM counts ORDER BY frequency_rank
            """,
            TABLES / "a1_order_route_values.csv",
        )
        export_query(
            con,
            """
            WITH counts AS (
              SELECT drug_class, lower(trim(route)) AS route,
                     count(*) AS prescription_rows_n
              FROM base.prescription_candidates
              WHERE nullif(trim(route), '') IS NOT NULL
              GROUP BY drug_class, lower(trim(route))
            ), ranked AS (
              SELECT *, row_number() OVER (
                PARTITION BY drug_class
                ORDER BY prescription_rows_n DESC, route
              ) AS frequency_rank
              FROM counts
            )
            SELECT drug_class, frequency_rank, route, prescription_rows_n
            FROM ranked WHERE frequency_rank <= 10
            ORDER BY drug_class, frequency_rank
            """,
            TABLES / "prescription_route_top_values_by_class.csv",
        )

        pilot_cardinality = export_query(
            con,
            """
            SELECT 'residual stays' AS checkpoint, count(*) AS rows_n,
                   count(DISTINCT stay_id) AS distinct_stays_n
            FROM a2_residual_stays
            UNION ALL
            SELECT 'qualifying eMAR events', count(*), count(DISTINCT stay_id)
            FROM a2_residual_emar_events
            UNION ALL
            SELECT 'event link facts', count(*), count(DISTINCT stay_id)
            FROM a2_residual_event_link_facts
            UNION ALL
            SELECT 'patient classifications', count(*), count(DISTINCT stay_id)
            FROM a2_residual_patient_classification
            """,
            TABLES / "residual_provenance_checkpoint_cardinality.csv",
        )

        raw_after = {path.name: source_state(path) for path in raw_sources}
        if raw_before != raw_after:
            raise RuntimeError("A raw MIMIC source changed during diagnostics")

        categories = {
            row[0]: int(row[1])
            for row in con.execute(
                """
                SELECT trace_category, count(*)
                FROM a2_residual_patient_classification
                GROUP BY trace_category
                """
            ).fetchall()
        }
        top10_coverage = float(medication_strings["events_pct"].sum())
        a1_route_records = {
            row["source_layer"]: {
                "records_n": int(row["records_n"]),
                "route_available_pct": float(row["route_available_pct"]),
                "subcutaneous_compatible_pct": float(
                    row["subcutaneous_compatible_pct"]
                ),
            }
            for _, row in a1_route.iterrows()
        }
        manifest = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "script": Path(__file__).name,
            "script_sha256": sha256(Path(__file__)),
            "contract_sha256": observed_hash,
            "base_database_read_only": True,
            "prior_database_read_only": True,
            "raw_sources_before": raw_before,
            "raw_sources_after": raw_after,
            "a2_residual_stays_n": int(residual_n),
            "a2_residual_emar_events_n": int(event_n),
            "a2_trace_categories": categories,
            "a2_top10_medication_event_coverage_pct": top10_coverage,
            "a1_route_comparison": a1_route_records,
            "route_class_rows_n": int(route_comparison.shape[0]),
            "event_link_path_rows_n": int(event_paths.shape[0]),
            "patient_trace_rows_n": int(patient_summary.shape[0]),
            "product_top10_rows_n": int(product_strings.shape[0]),
            "checkpoint_rows_n": int(pilot_cardinality.shape[0]),
            "elapsed_seconds": time.time() - started,
        }
        (MANIFESTS / "34_residual_provenance_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        pd.DataFrame(
            [
                {
                    "file": CONTRACT.name,
                    "expected_sha256": EXPECTED_CONTRACT_SHA256,
                    "observed_sha256": observed_hash,
                    "match": observed_hash == EXPECTED_CONTRACT_SHA256,
                }
            ]
        ).to_csv(
            MANIFESTS / "34_contract_verification.csv",
            index=False,
            encoding="utf-8-sig",
        )
        (ENVIRONMENT / "Python_sessionInfo_residual_provenance.txt").write_text(
            "\n".join(
                [
                    f"python={sys.version}",
                    f"platform={platform.platform()}",
                    f"duckdb={duckdb.__version__}",
                    f"pandas={pd.__version__}",
                    f"contract_sha256={observed_hash}",
                    "raw_sources_modified=false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        log("PASS residual-provenance diagnostics complete")
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
