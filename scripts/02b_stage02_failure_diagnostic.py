from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb
import pandas as pd

from common import (
    DB_PATH,
    MIMIC_ROOT,
    OUTPUTS,
    REPORTS,
    RunLogger,
    csv_scan,
    ensure_dirs,
    verify_frozen_contract,
    write_csv,
)


SCRIPT = Path(__file__).resolve()
AUDIT = OUTPUTS / "audit"
LOG = RunLogger("02b_stage02_failure_diagnostic")


def table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    return bool(
        con.execute(
            """
            SELECT count(*) > 0
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = ?
            """,
            [table],
        ).fetchone()[0]
    )


def committed_table_inventory(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    tables = [
        row[0]
        for row in con.execute("SHOW TABLES").fetchall()
    ]
    for table in tables:
        columns = con.execute(
            f"PRAGMA table_info('{table}')"
        ).fetchall()
        records.append(
            {
                "table_name": table,
                "row_count": int(
                    con.execute(
                        f'SELECT count(*) FROM "{table}"'
                    ).fetchone()[0]
                ),
                "column_count": len(columns),
                "columns": "|".join(
                    f"{row[1]}:{row[2]}" for row in columns
                ),
            }
        )
    result = pd.DataFrame(records).sort_values("table_name")
    write_csv(result, AUDIT / "02_committed_table_inventory.csv")
    return result


def legacy_prefilter_sql() -> str:
    prescriptions = csv_scan(
        MIMIC_ROOT / "hosp" / "prescriptions.csv.gz"
    )
    raw_name_text = (
        "lower(trim(coalesce(p.drug, '') || ' ' || "
        "coalesce(p.formulary_drug_cd, '')))"
    )
    return f"""
        WITH pharmacy_id_keys AS (
          SELECT DISTINCT
            subject_id, hadm_id, pharmacy_id
          FROM pharmacy_name_candidates
          WHERE pharmacy_id IS NOT NULL AND trim(pharmacy_id) <> ''
        ),
        pharmacy_poe_keys AS (
          SELECT DISTINCT
            subject_id, hadm_id, poe_id
          FROM pharmacy_name_candidates
          WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
        )
        SELECT
          TRY_CAST(p.subject_id AS BIGINT) AS subject_id,
          TRY_CAST(p.hadm_id AS BIGINT) AS hadm_id,
          p.pharmacy_id,
          p.poe_id,
          TRY_CAST(p.poe_seq AS BIGINT) AS poe_seq,
          TRY_CAST(p.starttime AS TIMESTAMP) AS starttime,
          TRY_CAST(p.stoptime AS TIMESTAMP) AS stoptime,
          p.drug_type,
          p.drug,
          p.formulary_drug_cd,
          p.gsn,
          p.ndc,
          p.prod_strength,
          p.dose_val_rx,
          p.dose_unit_rx,
          p.doses_per_24_hrs,
          p.route,
          nm.direct_ingredient
        FROM {prescriptions} p
        LEFT JOIN prescription_name_map nm
          ON {raw_name_text} = nm.name_key
        LEFT JOIN pharmacy_id_keys phi
          ON TRY_CAST(p.subject_id AS BIGINT) = phi.subject_id
         AND TRY_CAST(p.hadm_id AS BIGINT) = phi.hadm_id
         AND p.pharmacy_id IS NOT NULL
         AND trim(p.pharmacy_id) <> ''
         AND p.pharmacy_id = phi.pharmacy_id
        LEFT JOIN pharmacy_poe_keys php
          ON TRY_CAST(p.subject_id AS BIGINT) = php.subject_id
         AND TRY_CAST(p.hadm_id AS BIGINT) = php.hadm_id
         AND (p.pharmacy_id IS NULL OR trim(p.pharmacy_id) = '')
         AND p.poe_id IS NOT NULL
         AND trim(p.poe_id) <> ''
         AND p.poe_id = php.poe_id
        WHERE nm.direct_ingredient IS NOT NULL
           OR phi.pharmacy_id IS NOT NULL
           OR php.poe_id IS NOT NULL
    """


def write_legacy_explain(
    con: duckdb.DuckDBPyConnection,
) -> tuple[str, float]:
    LOG("START legacy prescription-prefilter EXPLAIN")
    started = time.time()
    rows = con.execute(
        "EXPLAIN " + legacy_prefilter_sql()
    ).fetchall()
    elapsed = time.time() - started
    plan = "\n".join(
        f"{row[0]}\n{row[1]}" if len(row) > 1 else str(row[0])
        for row in rows
    )
    (AUDIT / "02_legacy_prefilter_explain.txt").write_text(
        plan, encoding="utf-8"
    )
    LOG(
        "DONE legacy prescription-prefilter EXPLAIN "
        f"elapsed={elapsed:.3f}s"
    )
    return plan, elapsed


def key_profile(
    con: duckdb.DuckDBPyConnection,
    table: str,
    columns: list[str],
) -> tuple[int, int, int, int]:
    key_sql = ", ".join(f'"{column}"' for column in columns)
    nonmissing_sql = " AND ".join(
        f'"{column}" IS NOT NULL' for column in columns
    )
    result = con.execute(
            f"""
            SELECT
              count(*)::BIGINT AS unique_keys_n,
              coalesce(sum(rows_per_key), 0)::BIGINT AS nonmissing_rows_n,
              coalesce(max(rows_per_key), 0)::BIGINT AS max_rows_per_key,
              coalesce(
                sum(rows_per_key::HUGEINT * rows_per_key::HUGEINT), 0
              )::HUGEINT AS same_key_self_join_rows_n
            FROM (
              SELECT count(*)::BIGINT AS rows_per_key
              FROM "{table}"
              WHERE {nonmissing_sql}
              GROUP BY {key_sql}
            )
            """
        ).fetchone()
    return tuple(int(value) for value in result)


def key_cardinality_audit(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    specs = {
        "pharmacy_name_candidates": [
            ["subject_id"],
            ["hadm_id"],
            ["poe_id"],
            ["pharmacy_id"],
            ["subject_id", "hadm_id", "poe_id"],
            ["subject_id", "hadm_id", "pharmacy_id"],
        ],
        "poe_identity": [
            ["subject_id"],
            ["hadm_id"],
            ["poe_id"],
        ],
        "emar_medication_events": [
            ["subject_id"],
            ["hadm_id"],
            ["poe_id"],
            ["pharmacy_id"],
            ["poe_id", "drug_class"],
            ["subject_id", "hadm_id", "poe_id", "drug_class"],
            ["subject_id", "hadm_id", "pharmacy_id", "drug_class"],
        ],
    }
    records: list[dict[str, object]] = []
    for table, keys in specs.items():
        if not table_exists(con, table):
            continue
        total_rows = int(
            con.execute(
                f'SELECT count(*) FROM "{table}"'
            ).fetchone()[0]
        )
        for columns in keys:
            key_name = "+".join(columns)
            LOG(f"START key audit table={table} key={key_name}")
            started = time.time()
            (
                unique_n,
                nonmissing_rows_n,
                max_dup,
                same_key_self_join_rows_n,
            ) = key_profile(con, table, columns)
            records.append(
                {
                    "table_name": table,
                    "total_rows": total_rows,
                    "key": key_name,
                    "nonmissing_rows_n": nonmissing_rows_n,
                    "unique_nonmissing_keys_n": unique_n,
                    "max_rows_per_key": max_dup,
                    "mean_rows_per_nonmissing_key": (
                        nonmissing_rows_n / unique_n if unique_n else None
                    ),
                    "same_key_self_join_rows_n": same_key_self_join_rows_n,
                    "duplicate_excess_rows_n": (
                        nonmissing_rows_n - unique_n
                    ),
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            )
            write_csv(
                pd.DataFrame(records),
                AUDIT / "02_existing_key_cardinality.csv",
            )
            LOG(
                f"DONE key audit table={table} key={key_name} "
                f"unique={unique_n} max_dup={max_dup}"
            )
    return pd.DataFrame(records)


def render_report(
    inventory: pd.DataFrame,
    plan: str,
    explain_elapsed: float,
    cardinality: pd.DataFrame | None,
) -> str:
    nested_operators = [
        operator
        for operator in (
            "BLOCKWISE_NL_JOIN",
            "NESTED_LOOP_JOIN",
            "CROSS_PRODUCT",
        )
        if operator in plan
    ]
    operator_text = (
        ", ".join(nested_operators)
        if nested_operators
        else "none detected in EXPLAIN text"
    )
    lines = [
        "# Stage 02 implementation-failure diagnostic",
        "",
        "This is an implementation audit, not a statistical result.",
        "The frozen scientific contract was not changed.",
        "",
        "## Committed checkpoint inventory",
        "",
        "```text",
        inventory.to_string(index=False),
        "```",
        "",
        "The interrupted transaction did not commit",
        "`prescription_prefilter`; the active statement was its",
        "`CREATE OR REPLACE TABLE ... AS` query.",
        "",
        "## Legacy execution plan",
        "",
        f"EXPLAIN binding elapsed: {explain_elapsed:.3f} seconds.",
        f"High-risk join operators: {operator_text}.",
        "",
        "```text",
        plan,
        "```",
    ]
    if cardinality is not None:
        lines.extend(
            [
                "",
                "## Existing materialized-table key cardinality",
                "",
                "```text",
                cardinality.to_string(index=False),
                "```",
            ]
        )
    lines.extend(
        [
            "",
            "## Implementation conclusion",
            "",
            "The failed implementation placed conditional LEFT JOINs and",
            "post-join OR filtering directly above a full gzip CSV scan.",
            "The replacement must materialize a narrow prescription",
            "projection, split direct-name, pharmacy-id, and fallback-POE",
            "candidate paths, union/deduplicate them at the frozen order",
            "analysis unit, aggregate eMAR before joining, and checkpoint",
            "every stage.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Skip exact key-cardinality scans.",
    )
    args = parser.parse_args()

    ensure_dirs()
    AUDIT.mkdir(parents=True, exist_ok=True)
    verify_frozen_contract()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    con.execute("SET threads=4")
    inventory = committed_table_inventory(con)
    plan, elapsed = write_legacy_explain(con)
    cardinality = None
    if not args.plan_only:
        cardinality = key_cardinality_audit(con)
    con.close()

    (REPORTS / "02_stage02_failure_diagnostic.md").write_text(
        render_report(inventory, plan, elapsed, cardinality),
        encoding="utf-8",
    )
    LOG(
        "DONE Stage 02 failure diagnostic "
        f"plan_only={args.plan_only}"
    )


if __name__ == "__main__":
    main()
