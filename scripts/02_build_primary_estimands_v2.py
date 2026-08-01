from __future__ import annotations

import argparse
import importlib.util
import math
import time
from datetime import datetime
from pathlib import Path
from types import ModuleType

import duckdb
import pandas as pd

from common import (
    DB_PATH,
    MANIFESTS,
    MIMIC_ROOT,
    OUTPUTS,
    REPORTS,
    TABLES,
    RunLogger,
    connect_duckdb,
    ensure_dirs,
    load_whitelist,
    script_metadata,
    sql_path,
    sql_quote,
    verify_frozen_contract,
    write_csv,
    write_json,
)


SCRIPT = Path(__file__).resolve()
LEGACY_SCRIPT = SCRIPT.with_name("02_build_primary_estimands.py")
AUDIT = OUTPUTS / "audit"
PLANS = AUDIT / "02_v2_plans"
LOG = RunLogger("02_build_primary_estimands_v2")
RUN_ID = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
FORBIDDEN_PLAN_OPERATORS = (
    "BLOCKWISE_NL_JOIN",
    "NESTED_LOOP_JOIN",
    "CROSS_PRODUCT",
)


def load_legacy_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "n1_stage02_legacy_helpers", LEGACY_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {LEGACY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def row_count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return int(
        con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
    )


def file_state(path: Path) -> tuple[int, str]:
    if not path.exists():
        return 0, ""
    stat = path.stat()
    return stat.st_size, datetime.fromtimestamp(
        stat.st_mtime
    ).astimezone().isoformat(timespec="seconds")


def append_checkpoint(record: dict[str, object]) -> None:
    path = AUDIT / "02_v2_checkpoints.csv"
    frame = pd.DataFrame([record])
    if path.exists():
        existing = pd.read_csv(path)
        frame = pd.concat([existing, frame], ignore_index=True)
    write_csv(frame, path)


def render_plan(rows: list[tuple[object, ...]]) -> str:
    return "\n".join(
        f"{row[0]}\n{row[1]}" if len(row) > 1 else str(row[0])
        for row in rows
    )


def explain_guard(
    con: duckdb.DuckDBPyConnection,
    step: str,
    select_sql: str,
    *,
    analyze: bool = False,
) -> str:
    mode = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
    started = time.time()
    plan = render_plan(
        con.execute(f"{mode} {select_sql}").fetchall()
    )
    suffix = "analyze" if analyze else "plan"
    PLANS.mkdir(parents=True, exist_ok=True)
    (PLANS / f"{step}_{suffix}.txt").write_text(
        plan, encoding="utf-8"
    )
    forbidden = [
        operator
        for operator in FORBIDDEN_PLAN_OPERATORS
        if operator in plan
    ]
    LOG(
        f"{mode} step={step} elapsed={time.time() - started:.3f}s "
        f"forbidden={forbidden or 'none'}"
    )
    if forbidden:
        raise RuntimeError(
            f"Unsafe execution plan for {step}: {forbidden}"
        )
    return plan


def materialize(
    con: duckdb.DuckDBPyConnection,
    *,
    step: str,
    table: str,
    select_sql: str,
    analyze: bool = False,
    resume: bool = True,
    allow_empty: bool = False,
) -> int:
    if resume and table_exists(con, table):
        existing_rows = row_count(con, table)
        if existing_rows > 0 or allow_empty:
            LOG(f"RESUME step={step} table={table} rows={existing_rows}")
            append_checkpoint(
                {
                    "run_id": RUN_ID,
                    "step": step,
                    "table_name": table,
                    "status": "resumed",
                    "row_count": existing_rows,
                    "elapsed_seconds": 0.0,
                    "db_bytes": file_state(DB_PATH)[0],
                    "wal_bytes": file_state(Path(f"{DB_PATH}.wal"))[0],
                    "finished_at": datetime.now()
                    .astimezone()
                    .isoformat(timespec="seconds"),
                }
            )
            return existing_rows

    explain_guard(con, step, select_sql)
    if analyze:
        explain_guard(con, step, select_sql, analyze=True)
    LOG(f"START step={step} table={table}")
    started = time.time()
    con.execute(
        f'CREATE OR REPLACE TABLE "{table}" AS {select_sql}'
    )
    rows = row_count(con, table)
    con.execute("CHECKPOINT")
    elapsed = time.time() - started
    db_bytes, _ = file_state(DB_PATH)
    wal_bytes, _ = file_state(Path(f"{DB_PATH}.wal"))
    append_checkpoint(
        {
            "run_id": RUN_ID,
            "step": step,
            "table_name": table,
            "status": "completed",
            "row_count": rows,
            "elapsed_seconds": round(elapsed, 3),
            "db_bytes": db_bytes,
            "wal_bytes": wal_bytes,
            "finished_at": datetime.now()
            .astimezone()
            .isoformat(timespec="seconds"),
        }
    )
    LOG(
        f"DONE step={step} table={table} rows={rows} "
        f"elapsed={elapsed:.3f}s db_bytes={db_bytes} wal_bytes={wal_bytes}"
    )
    return rows


def assert_unique(
    con: duckdb.DuckDBPyConnection,
    table: str,
    columns: list[str],
) -> dict[str, object]:
    key_sql = ", ".join(f'"{column}"' for column in columns)
    result = con.execute(
        f"""
        SELECT
          count(*) AS unique_keys_n,
          coalesce(sum(rows_per_key), 0) AS rows_n,
          coalesce(max(rows_per_key), 0) AS max_rows_per_key
        FROM (
          SELECT count(*) AS rows_per_key
          FROM "{table}"
          GROUP BY {key_sql}
        )
        """
    ).fetchone()
    gate = {
        "table_name": table,
        "key": "+".join(columns),
        "unique_keys_n": int(result[0]),
        "rows_n": int(result[1]),
        "max_rows_per_key": int(result[2]),
        "pass": int(result[2]) <= 1,
    }
    if not gate["pass"]:
        raise RuntimeError(f"Uniqueness gate failed: {gate}")
    return gate


def assert_required_columns(
    con: duckdb.DuckDBPyConnection,
    table: str,
    required: set[str],
) -> None:
    observed = {
        str(row[1])
        for row in con.execute(f"PRAGMA table_info('{table}')").fetchall()
    }
    missing = sorted(required - observed)
    if missing:
        raise RuntimeError(
            f"Table {table} is not a Stage 02 v2 table; "
            f"missing columns={missing}"
        )


def key_profile(
    con: duckdb.DuckDBPyConnection,
    table: str,
    columns: list[str],
) -> dict[str, object]:
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
    total_rows = row_count(con, table)
    unique_n = int(result[0])
    nonmissing_n = int(result[1])
    return {
        "table_name": table,
        "total_rows": total_rows,
        "key": "+".join(columns),
        "nonmissing_rows_n": nonmissing_n,
        "unique_nonmissing_keys_n": unique_n,
        "max_rows_per_key": int(result[2]),
        "mean_rows_per_nonmissing_key": (
            nonmissing_n / unique_n if unique_n else None
        ),
        "same_key_self_join_rows_n": int(result[3]),
        "duplicate_excess_rows_n": nonmissing_n - unique_n,
    }


def assert_row_equality(
    con: duckdb.DuckDBPyConnection,
    *,
    left_table: str,
    right_table: str,
    gate_name: str,
) -> dict[str, object]:
    left_n = row_count(con, left_table)
    right_n = row_count(con, right_table)
    gate = {
        "gate": gate_name,
        "left_table": left_table,
        "right_table": right_table,
        "left_rows_n": left_n,
        "right_rows_n": right_n,
        "pass": left_n == right_n,
    }
    if not gate["pass"]:
        raise RuntimeError(f"Row-equality gate failed: {gate}")
    return gate


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


PHARMACY_COLUMNS = [
    "subject_id",
    "hadm_id",
    "pharmacy_id",
    "poe_id",
    "starttime",
    "stoptime",
    "medication",
    "proc_type",
    "status",
    "entertime",
    "verifiedtime",
    "route",
    "frequency",
    "disp_sched",
    "infusion_type",
    "sliding_scale",
    "lockout_interval",
    "basal_rate",
    "one_hr_max",
    "doses_per_24_hrs",
    "duration",
    "duration_interval",
    "expiration_value",
    "expiration_unit",
    "expirationdate",
    "dispensation",
    "fill_quantity",
]


EMAR_COLUMNS = [
    "subject_id",
    "hadm_id",
    "emar_id",
    "emar_seq",
    "poe_id",
    "pharmacy_id",
    "enter_provider_id",
    "charttime",
    "medication",
    "event_txt",
    "scheduletime",
    "storetime",
]


def fixed_varchar_scan(path: Path, columns: list[str]) -> str:
    schema = ", ".join(
        f"{sql_quote(column)}: 'VARCHAR'"
        for column in columns
    )
    return (
        f"read_csv('{sql_path(path)}', header=true, "
        f"auto_detect=false, columns={{{schema}}}, "
        "ignore_errors=false, strict_mode=true, null_padding=false)"
    )


def prescriptions_scan() -> str:
    return fixed_varchar_scan(
        MIMIC_ROOT / "hosp" / "prescriptions.csv.gz",
        PRESCRIPTION_COLUMNS,
    )


def prescription_projection_sql(
    *,
    limit_rows: int | None = None,
    source_where: str | None = None,
) -> str:
    source = prescriptions_scan()
    if source_where is not None or limit_rows is not None:
        where_sql = (
            f"WHERE {source_where}" if source_where is not None else ""
        )
        limit_sql = (
            f"LIMIT {int(limit_rows)}"
            if limit_rows is not None
            else ""
        )
        source = (
            f"(SELECT * FROM {source} {where_sql} {limit_sql})"
        )
    return f"""
        SELECT
          row_number() OVER ()::BIGINT AS prescription_row_id,
          TRY_CAST(p.subject_id AS BIGINT) AS subject_id,
          TRY_CAST(p.hadm_id AS BIGINT) AS hadm_id,
          nullif(trim(p.pharmacy_id), '') AS pharmacy_id,
          nullif(trim(p.poe_id), '') AS poe_id,
          TRY_CAST(p.poe_seq AS BIGINT) AS poe_seq,
          TRY_CAST(p.starttime AS TIMESTAMP) AS starttime,
          TRY_CAST(p.stoptime AS TIMESTAMP) AS stoptime,
          p.drug,
          p.formulary_drug_cd,
          p.dose_val_rx,
          p.dose_unit_rx,
          p.doses_per_24_hrs,
          p.route,
          lower(trim(
            coalesce(p.drug, '') || ' ' ||
            coalesce(p.formulary_drug_cd, '')
          )) AS name_key
        FROM {source} p
    """


def ingredient_map_values(whitelist: pd.DataFrame) -> str:
    mapping = whitelist[
        ["ingredient", "drug_class", "subclass"]
    ].drop_duplicates()
    if len(mapping) != whitelist["ingredient"].nunique():
        raise RuntimeError(
            "Frozen strict ingredients are not one-to-one with class/subclass"
        )
    rows = [
        "("
        + ", ".join(
            (
                sql_quote(row.ingredient),
                sql_quote(row.drug_class),
                sql_quote(row.subclass),
            )
        )
        + ")"
        for row in mapping.itertuples(index=False)
    ]
    return ",\n".join(rows)


def build_reference_units(
    con: duckdb.DuckDBPyConnection,
    whitelist: pd.DataFrame,
) -> list[dict[str, object]]:
    gates: list[dict[str, object]] = []
    materialize(
        con,
        step="ingredient_map",
        table="s02v2_ingredient_map",
        select_sql=f"""
            SELECT *
            FROM (
              VALUES {ingredient_map_values(whitelist)}
            ) AS t(ingredient, drug_class, subclass)
        """,
    )
    gates.append(
        assert_unique(
            con, "s02v2_ingredient_map", ["ingredient"]
        )
    )

    materialize(
        con,
        step="pharmacy_by_id",
        table="s02v2_pharmacy_by_id",
        select_sql="""
            SELECT * EXCLUDE (unit_rank)
            FROM (
              SELECT
                subject_id, hadm_id, pharmacy_id,
                drug_class, ingredient, subclass,
                pharmacy_medication, pharmacy_route, pharmacy_status,
                row_number() OVER (
                  PARTITION BY subject_id, hadm_id, pharmacy_id
                  ORDER BY
                    coalesce(
                      pharmacy_starttime, TIMESTAMP '9999-12-31'
                    ),
                    drug_class, ingredient, pharmacy_medication
                ) AS unit_rank
              FROM pharmacy_name_candidates
              WHERE pharmacy_id IS NOT NULL
            )
            WHERE unit_rank = 1
        """,
    )
    gates.append(
        assert_unique(
            con,
            "s02v2_pharmacy_by_id",
            ["subject_id", "hadm_id", "pharmacy_id"],
        )
    )

    materialize(
        con,
        step="pharmacy_by_poe",
        table="s02v2_pharmacy_by_poe",
        select_sql="""
            SELECT * EXCLUDE (unit_rank)
            FROM (
              SELECT
                subject_id, hadm_id, poe_id,
                drug_class, ingredient, subclass,
                pharmacy_medication, pharmacy_route, pharmacy_status,
                row_number() OVER (
                  PARTITION BY subject_id, hadm_id, poe_id
                  ORDER BY
                    coalesce(
                      pharmacy_starttime, TIMESTAMP '9999-12-31'
                    ),
                    drug_class, ingredient, pharmacy_medication
                ) AS unit_rank
              FROM pharmacy_name_candidates
              WHERE poe_id IS NOT NULL
            )
            WHERE unit_rank = 1
        """,
    )
    gates.append(
        assert_unique(
            con,
            "s02v2_pharmacy_by_poe",
            ["subject_id", "hadm_id", "poe_id"],
        )
    )
    return gates


def direct_candidate_sql(projected_table: str) -> str:
    return f"""
        SELECT
          p.*,
          im.drug_class,
          nm.direct_ingredient AS ingredient,
          im.subclass,
          CAST(NULL AS VARCHAR) AS pharmacy_medication,
          CAST(NULL AS VARCHAR) AS pharmacy_route,
          CAST(NULL AS VARCHAR) AS pharmacy_status,
          'prescriptions' AS order_name_match_source,
          1::INTEGER AS match_priority
        FROM "{projected_table}" p
        INNER JOIN prescription_name_map nm
          ON p.name_key = nm.name_key
        INNER JOIN s02v2_ingredient_map im
          ON nm.direct_ingredient = im.ingredient
        WHERE nm.direct_ingredient IS NOT NULL
    """


def pharmacy_id_candidate_sql(projected_table: str) -> str:
    return f"""
        SELECT
          p.*,
          ph.drug_class,
          ph.ingredient,
          ph.subclass,
          ph.pharmacy_medication,
          ph.pharmacy_route,
          ph.pharmacy_status,
          'pharmacy_id_recovery' AS order_name_match_source,
          2::INTEGER AS match_priority
        FROM (
          SELECT *
          FROM "{projected_table}"
          WHERE pharmacy_id IS NOT NULL
        ) p
        INNER JOIN s02v2_pharmacy_by_id ph
          ON p.subject_id = ph.subject_id
         AND p.hadm_id = ph.hadm_id
         AND p.pharmacy_id = ph.pharmacy_id
    """


def pharmacy_poe_candidate_sql(projected_table: str) -> str:
    return f"""
        SELECT
          p.*,
          ph.drug_class,
          ph.ingredient,
          ph.subclass,
          ph.pharmacy_medication,
          ph.pharmacy_route,
          ph.pharmacy_status,
          'pharmacy_poe_fallback' AS order_name_match_source,
          3::INTEGER AS match_priority
        FROM (
          SELECT *
          FROM "{projected_table}"
          WHERE pharmacy_id IS NULL AND poe_id IS NOT NULL
        ) p
        INNER JOIN s02v2_pharmacy_by_poe ph
          ON p.subject_id = ph.subject_id
         AND p.hadm_id = ph.hadm_id
         AND p.poe_id = ph.poe_id
    """


def final_candidate_sql(
    direct_table: str,
    id_table: str,
    poe_table: str,
) -> str:
    return f"""
        SELECT
          * EXCLUDE (candidate_rank, match_priority, name_key),
          TRY_CAST(
            nullif(
              regexp_extract(
                coalesce(dose_val_rx, ''),
                '([0-9]+(?:[.][0-9]+)?)',
                1
              ),
              ''
            ) AS DOUBLE
          ) AS parsed_dose
        FROM (
          SELECT
            u.*,
            row_number() OVER (
              PARTITION BY prescription_row_id
              ORDER BY match_priority
            ) AS candidate_rank
          FROM (
            SELECT * FROM "{direct_table}"
            UNION ALL BY NAME
            SELECT * FROM "{id_table}"
            UNION ALL BY NAME
            SELECT * FROM "{poe_table}"
          ) u
        )
        WHERE candidate_rank = 1
    """


def build_prescription_candidates(
    con: duckdb.DuckDBPyConnection,
    *,
    projected_table: str,
    prefix: str,
    analyze: bool,
    final_table: str,
) -> dict[str, int]:
    direct_table = f"{prefix}_direct"
    id_table = f"{prefix}_pharmacy_id"
    poe_table = f"{prefix}_pharmacy_poe"
    direct_n = materialize(
        con,
        step=f"{prefix}_direct",
        table=direct_table,
        select_sql=direct_candidate_sql(projected_table),
        analyze=analyze,
    )
    id_n = materialize(
        con,
        step=f"{prefix}_pharmacy_id",
        table=id_table,
        select_sql=pharmacy_id_candidate_sql(projected_table),
        analyze=analyze,
    )
    poe_n = materialize(
        con,
        step=f"{prefix}_pharmacy_poe",
        table=poe_table,
        select_sql=pharmacy_poe_candidate_sql(projected_table),
        analyze=analyze,
        allow_empty=True,
    )
    final_n = materialize(
        con,
        step=f"{prefix}_deduplicated",
        table=final_table,
        select_sql=final_candidate_sql(
            direct_table, id_table, poe_table
        ),
        analyze=analyze,
    )
    assert_unique(con, final_table, ["prescription_row_id"])
    projected_n = row_count(con, projected_table)
    if final_n > projected_n:
        raise RuntimeError(
            "Candidate fan-out gate failed: "
            f"projected={projected_n} final={final_n}"
        )
    return {
        "projected_rows_n": projected_n,
        "direct_rows_n": direct_n,
        "pharmacy_id_rows_n": id_n,
        "pharmacy_poe_rows_n": poe_n,
        "candidate_union_rows_n": direct_n + id_n + poe_n,
        "deduplicated_candidate_rows_n": final_n,
        "duplicate_paths_removed_n": direct_n + id_n + poe_n - final_n,
    }


def run_pilot(
    con: duckdb.DuckDBPyConnection,
    whitelist: pd.DataFrame,
    pilot_rows: int,
) -> pd.DataFrame:
    gates = build_reference_units(con, whitelist)
    projected_table = f"s02v2_pilot_prescriptions_{pilot_rows}"
    materialize(
        con,
        step=f"pilot_projection_{pilot_rows}",
        table=projected_table,
        select_sql=prescription_projection_sql(limit_rows=pilot_rows),
        analyze=True,
        resume=True,
        allow_empty=True,
    )
    metrics = build_prescription_candidates(
        con,
        projected_table=projected_table,
        prefix=f"s02v2_pilot_{pilot_rows}",
        analyze=True,
        final_table=f"s02v2_pilot_candidates_{pilot_rows}",
    )
    fallback_rows = min(50_000, pilot_rows)
    fallback_projection = (
        f"s02v2_pilot_missing_pharmacy_{fallback_rows}"
    )
    materialize(
        con,
        step=f"pilot_missing_pharmacy_projection_{fallback_rows}",
        table=fallback_projection,
        select_sql=prescription_projection_sql(
            limit_rows=fallback_rows,
            source_where=(
                "(pharmacy_id IS NULL OR trim(pharmacy_id) = '') "
                "AND poe_id IS NOT NULL AND trim(poe_id) <> ''"
            ),
        ),
        analyze=True,
        resume=True,
        allow_empty=True,
    )
    fallback_match_table = (
        f"s02v2_pilot_missing_pharmacy_matches_{fallback_rows}"
    )
    fallback_matches_n = materialize(
        con,
        step=f"pilot_missing_pharmacy_match_{fallback_rows}",
        table=fallback_match_table,
        select_sql=pharmacy_poe_candidate_sql(
            fallback_projection
        ),
        analyze=True,
        resume=True,
        allow_empty=True,
    )
    fallback_source_rows_n = row_count(con, fallback_projection)
    pilot_gates = gates + [
        {
            "table_name": f"s02v2_pilot_candidates_{pilot_rows}",
            "key": "candidate_rows_not_above_projected",
            "unique_keys_n": metrics[
                "deduplicated_candidate_rows_n"
            ],
            "rows_n": metrics["projected_rows_n"],
            "max_rows_per_key": 1,
            "pass": (
                metrics["deduplicated_candidate_rows_n"]
                <= metrics["projected_rows_n"]
            ),
        },
        {
            "table_name": f"s02v2_pilot_candidates_{pilot_rows}",
            "key": "candidate_count_positive",
            "unique_keys_n": metrics[
                "deduplicated_candidate_rows_n"
            ],
            "rows_n": metrics[
                "deduplicated_candidate_rows_n"
            ],
            "max_rows_per_key": 1,
            "pass": metrics["deduplicated_candidate_rows_n"] > 0,
        },
        {
            "table_name": fallback_match_table,
            "key": "poe_fallback_path_exercised",
            "unique_keys_n": fallback_matches_n,
            "rows_n": fallback_source_rows_n,
            "max_rows_per_key": 1,
            "pass": (
                fallback_source_rows_n == 0
                or fallback_matches_n > 0
            ),
            "gate_status": (
                "not_applicable_no_missing_pharmacy_id_with_poe_id"
                if fallback_source_rows_n == 0
                else "exercised"
            ),
        },
    ]
    gate_frame = pd.DataFrame(pilot_gates)
    for key, value in metrics.items():
        gate_frame[key] = value
    gate_frame["targeted_fallback_matches_n"] = fallback_matches_n
    gate_frame["targeted_fallback_source_rows_n"] = (
        fallback_source_rows_n
    )
    write_csv(gate_frame, AUDIT / "02_v2_pilot_gates.csv")
    if not gate_frame["pass"].all():
        raise RuntimeError(
            "Stage 02 v2 pilot gates failed:\n"
            + gate_frame.to_string(index=False)
        )
    (REPORTS / "02_stage02_v2_pilot.md").write_text(
        "\n".join(
            [
                "# Stage 02 v2 limited-range pilot",
                "",
                "The frozen scientific contract was unchanged.",
                "The pilot tests implementation shape only.",
                "",
                "## Metrics",
                "",
                "```text",
                pd.DataFrame([metrics]).to_string(index=False),
                "```",
                "",
                "## Gates",
                "",
                "```text",
                gate_frame.to_string(index=False),
                "```",
                "",
                "All candidate-path joins use plans without",
                "BLOCKWISE_NL_JOIN, NESTED_LOOP_JOIN, or CROSS_PRODUCT.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    LOG(f"DONE v2 pilot metrics={metrics}")
    return gate_frame


def run_full_prescription_stage(
    con: duckdb.DuckDBPyConnection,
    whitelist: pd.DataFrame,
) -> dict[str, int]:
    pilot_gate_path = AUDIT / "02_v2_pilot_gates.csv"
    if not pilot_gate_path.exists():
        raise RuntimeError("Run --pilot-only before full Stage 02 v2")
    pilot_gates = pd.read_csv(pilot_gate_path)
    if pilot_gates.empty or not pilot_gates["pass"].all():
        raise RuntimeError("Stage 02 v2 pilot gates are not all passing")
    build_reference_units(con, whitelist)
    materialize(
        con,
        step="full_prescription_projection",
        table="s02v2_prescriptions_projected",
        select_sql=prescription_projection_sql(),
    )
    expected_rows = int(
        con.execute(
            "SELECT sum(source_rows_n) "
            "FROM prescription_name_dictionary"
        ).fetchone()[0]
    )
    observed_rows = row_count(con, "s02v2_prescriptions_projected")
    if observed_rows != expected_rows:
        raise RuntimeError(
            "Full prescription projection row gate failed: "
            f"expected={expected_rows} observed={observed_rows}"
        )
    metrics = build_prescription_candidates(
        con,
        projected_table="s02v2_prescriptions_projected",
        prefix="s02v2_full",
        analyze=False,
        final_table="prescription_candidates",
    )
    write_csv(
        pd.DataFrame([metrics]),
        AUDIT / "02_v2_full_prescription_metrics.csv",
    )
    LOG(f"DONE full v2 prescription stage metrics={metrics}")
    return metrics


def raw_interface_key_projection_sql(
    *,
    path: Path,
    columns: list[str],
) -> str:
    source = fixed_varchar_scan(path, columns)
    return f"""
        SELECT
          TRY_CAST(subject_id AS BIGINT) AS subject_id,
          TRY_CAST(hadm_id AS BIGINT) AS hadm_id,
          nullif(trim(poe_id), '') AS poe_id,
          nullif(trim(pharmacy_id), '') AS pharmacy_id
        FROM {source}
    """


def build_raw_interface_key_tables(
    con: duckdb.DuckDBPyConnection,
) -> None:
    materialize(
        con,
        step="raw_pharmacy_key_projection",
        table="s02v2_raw_pharmacy_keys",
        select_sql=raw_interface_key_projection_sql(
            path=MIMIC_ROOT / "hosp" / "pharmacy.csv.gz",
            columns=PHARMACY_COLUMNS,
        ),
    )
    materialize(
        con,
        step="raw_emar_key_projection",
        table="s02v2_raw_emar_keys",
        select_sql=raw_interface_key_projection_sql(
            path=MIMIC_ROOT / "hosp" / "emar.csv.gz",
            columns=EMAR_COLUMNS,
        ),
    )


def write_full_key_cardinality_audit(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    specs = [
        (
            "prescriptions",
            "raw_full",
            "s02v2_prescriptions_projected",
            [
                ["subject_id"],
                ["hadm_id"],
                ["poe_id"],
                ["pharmacy_id"],
                ["subject_id", "hadm_id", "poe_id"],
                ["subject_id", "hadm_id", "pharmacy_id"],
            ],
        ),
        (
            "pharmacy",
            "raw_full",
            "s02v2_raw_pharmacy_keys",
            [
                ["subject_id"],
                ["hadm_id"],
                ["poe_id"],
                ["pharmacy_id"],
                ["subject_id", "hadm_id", "poe_id"],
                ["subject_id", "hadm_id", "pharmacy_id"],
            ],
        ),
        (
            "POE",
            "raw_full_unique_poe_projection",
            "poe_identity",
            [["subject_id"], ["hadm_id"], ["poe_id"]],
        ),
        (
            "eMAR",
            "raw_full",
            "s02v2_raw_emar_keys",
            [
                ["subject_id"],
                ["hadm_id"],
                ["poe_id"],
                ["pharmacy_id"],
                ["subject_id", "hadm_id", "poe_id"],
                ["subject_id", "hadm_id", "pharmacy_id"],
            ],
        ),
        (
            "prescriptions",
            "frozen_whitelist_candidate_subset",
            "prescription_candidates",
            [
                ["subject_id"],
                ["hadm_id"],
                ["poe_id"],
                ["pharmacy_id"],
                ["subject_id", "hadm_id", "poe_id"],
                ["subject_id", "hadm_id", "pharmacy_id"],
            ],
        ),
        (
            "pharmacy",
            "frozen_whitelist_name_subset",
            "pharmacy_name_candidates",
            [
                ["subject_id"],
                ["hadm_id"],
                ["poe_id"],
                ["pharmacy_id"],
                ["subject_id", "hadm_id", "poe_id"],
                ["subject_id", "hadm_id", "pharmacy_id"],
            ],
        ),
        (
            "eMAR",
            "frozen_whitelist_event_subset",
            "emar_medication_events",
            [
                ["subject_id"],
                ["hadm_id"],
                ["poe_id"],
                ["pharmacy_id"],
                ["subject_id", "hadm_id", "poe_id", "drug_class"],
                [
                    "subject_id",
                    "hadm_id",
                    "pharmacy_id",
                    "drug_class",
                ],
            ],
        ),
        (
            "eMAR",
            "preaggregated_order_key",
            "s02v2_emar_order_key_agg",
            [
                [
                    "subject_id",
                    "hadm_id",
                    "stay_id",
                    "drug_class",
                    "poe_id",
                ]
            ],
        ),
    ]
    records: list[dict[str, object]] = []
    output_path = AUDIT / "02_v2_full_key_cardinality.csv"
    for logical_table, scope, table, keys in specs:
        for columns in keys:
            LOG(
                "START full key audit "
                f"table={logical_table} scope={scope} "
                f"key={'+'.join(columns)}"
            )
            started = time.time()
            profile = key_profile(con, table, columns)
            profile = {
                "logical_table": logical_table,
                "scope": scope,
                "materialized_table": table,
                **profile,
                "elapsed_seconds": round(time.time() - started, 3),
            }
            records.append(profile)
            write_csv(pd.DataFrame(records), output_path)
            LOG(
                "DONE full key audit "
                f"table={logical_table} scope={scope} "
                f"key={profile['key']} unique="
                f"{profile['unique_nonmissing_keys_n']} max_dup="
                f"{profile['max_rows_per_key']}"
            )
    return pd.DataFrame(records)


def candidate_poe_keys_sql(candidate_table: str) -> str:
    return f"""
        SELECT DISTINCT poe_id
        FROM "{candidate_table}"
        WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
    """


def poe_for_candidates_sql(poe_key_table: str) -> str:
    return f"""
        SELECT i.*
        FROM poe_identity i
        INNER JOIN "{poe_key_table}" k USING (poe_id)
    """


def order_identity_sql(
    candidate_table: str,
    candidate_poe_table: str,
) -> str:
    return f"""
        SELECT
          p.*,
          i.first_ordertime AS ordertime,
          i.subject_id AS poe_subject_id,
          i.hadm_id AS poe_hadm_id,
          i.poe_id IS NOT NULL AS poe_any_link,
          (
            i.poe_id IS NOT NULL
            AND i.subject_id = p.subject_id
            AND (
              i.hadm_id = p.hadm_id
              OR (i.hadm_id IS NULL AND p.hadm_id IS NULL)
            )
          ) AS poe_identity_link
        FROM "{candidate_table}" p
        LEFT JOIN "{candidate_poe_table}" i USING (poe_id)
        WHERE p.drug_class IS NOT NULL
    """


def assigned_order_rows_sql(order_identity_table: str) -> str:
    return f"""
        SELECT * EXCLUDE (stay_assignment_rank)
        FROM (
          SELECT
            i.*,
            s.stay_id, s.intime, s.outtime,
            s.subject_stay_order, s.hadm_stay_order,
            count(*) OVER (
              PARTITION BY i.prescription_row_id
            ) AS stay_candidate_count,
            row_number() OVER (
              PARTITION BY i.prescription_row_id
              ORDER BY
                CASE
                  WHEN i.ordertime BETWEEN s.intime AND s.outtime
                    THEN 0 ELSE 1
                END,
                s.intime, s.stay_id
            ) AS stay_assignment_rank
          FROM "{order_identity_table}" i
          INNER JOIN adult_stays s
            ON i.subject_id = s.subject_id
           AND i.hadm_id = s.hadm_id
           AND i.ordertime BETWEEN
               s.intime - INTERVAL 6 HOUR AND s.outtime
           AND coalesce(i.starttime, i.ordertime) <= s.outtime
           AND coalesce(i.stoptime, s.outtime) >= s.intime
        )
        WHERE stay_assignment_rank = 1
    """


def order_clusters_sql(assigned_table: str) -> str:
    return f"""
        SELECT
          subject_id, hadm_id, stay_id, drug_class, poe_id,
          min(ordertime) AS ordertime,
          min(starttime) AS prescription_starttime,
          max(stoptime) AS prescription_stoptime,
          arg_min(drug, coalesce(starttime, ordertime)) AS drug,
          arg_min(ingredient, coalesce(starttime, ordertime)) AS ingredient,
          arg_min(subclass, coalesce(starttime, ordertime)) AS subclass,
          arg_min(route, coalesce(starttime, ordertime)) AS route,
          arg_min(dose_val_rx, coalesce(starttime, ordertime))
            AS dose_val_rx,
          arg_min(dose_unit_rx, coalesce(starttime, ordertime))
            AS dose_unit_rx,
          arg_min(parsed_dose, coalesce(starttime, ordertime))
            AS parsed_dose,
          arg_min(doses_per_24_hrs, coalesce(starttime, ordertime))
            AS doses_per_24_hrs,
          bool_or(poe_any_link) AS poe_any_link,
          bool_or(poe_identity_link) AS poe_identity_link,
          count(*) AS prescription_rows_n
        FROM "{assigned_table}"
        WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
        GROUP BY subject_id, hadm_id, stay_id, drug_class, poe_id
    """


def eligible_order_clusters_sql(cluster_table: str) -> str:
    return f"""
        SELECT
          o.*,
          s.intime,
          s.outtime,
          CASE
            WHEN o.drug_class <> 'vte_prophylaxis' THEN TRUE
            WHEN regexp_matches(
              lower(coalesce(o.route, '')), '(sc|sq|subcut)'
            )
             AND (
               (
                 o.ingredient = 'heparin'
                 AND o.parsed_dose IN (5000, 7500)
               )
               OR (
                 o.ingredient = 'enoxaparin'
                 AND o.parsed_dose BETWEEN 20 AND 60
               )
             )
            THEN TRUE
            ELSE FALSE
          END AS route_dose_eligible
        FROM "{cluster_table}" o
        INNER JOIN adult_stays s USING (subject_id, hadm_id, stay_id)
        WHERE o.poe_identity_link
          AND (
            o.drug_class <> 'vte_prophylaxis'
            OR (
              regexp_matches(
                lower(coalesce(o.route, '')), '(sc|sq|subcut)'
              )
              AND (
                (
                  o.ingredient = 'heparin'
                  AND o.parsed_dose IN (5000, 7500)
                )
                OR (
                  o.ingredient = 'enoxaparin'
                  AND o.parsed_dose BETWEEN 20 AND 60
                )
              )
            )
          )
    """


def pilot_emar_source_sql(eligible_table: str) -> str:
    return f"""
        SELECT e.*
        FROM emar_medication_events e
        INNER JOIN (
          SELECT DISTINCT
            subject_id, hadm_id, poe_id, drug_class
          FROM "{eligible_table}"
        ) k
          ON e.subject_id = k.subject_id
         AND e.hadm_id = k.hadm_id
         AND e.poe_id = k.poe_id
         AND e.drug_class = k.drug_class
    """


def emar_stay_events_sql(event_source_table: str) -> str:
    return f"""
        SELECT * EXCLUDE (stay_assignment_rank)
        FROM (
          SELECT
            e.*,
            s.stay_id, s.intime, s.outtime,
            s.first_careunit, s.anchor_era,
            count(*) OVER (
              PARTITION BY e.emar_id, e.emar_seq, e.drug_class
            ) AS stay_candidate_count,
            row_number() OVER (
              PARTITION BY e.emar_id, e.emar_seq, e.drug_class
              ORDER BY s.intime, s.stay_id
            ) AS stay_assignment_rank
          FROM "{event_source_table}" e
          INNER JOIN adult_stays s
            ON e.subject_id = s.subject_id
           AND e.hadm_id = s.hadm_id
           AND e.charttime BETWEEN s.intime AND s.outtime
        )
        WHERE stay_assignment_rank = 1
    """


def emar_order_key_agg_sql(stay_event_table: str) -> str:
    return f"""
        SELECT
          subject_id, hadm_id, stay_id, drug_class, poe_id,
          count(*)::BIGINT AS events_n,
          count(*) FILTER (
            WHERE event_category = 'given_strict'
          )::BIGINT AS given_strict_events_n,
          count(*) FILTER (
            WHERE event_category = 'not_given'
          )::BIGINT AS not_given_events_n,
          list(charttime ORDER BY charttime) FILTER (
            WHERE event_category = 'given_strict'
          ) AS qualifying_given_times,
          list(charttime ORDER BY charttime) FILTER (
            WHERE event_category = 'not_given'
          ) AS not_given_times
        FROM "{stay_event_table}"
        WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
        GROUP BY subject_id, hadm_id, stay_id, drug_class, poe_id
    """


def order_conversion_sql(
    eligible_table: str,
    emar_agg_table: str,
) -> str:
    return f"""
        WITH joined AS (
          SELECT
            o.*,
            o.ordertime - INTERVAL 2 HOUR
              AS conversion_window_start,
            least(
              coalesce(
                o.prescription_stoptime + INTERVAL 6 HOUR,
                o.outtime
              ),
              o.outtime
            ) AS conversion_window_end,
            e.events_n AS linked_key_events_n,
            e.qualifying_given_times,
            e.not_given_times
          FROM "{eligible_table}" o
          LEFT JOIN "{emar_agg_table}" e
            ON o.subject_id = e.subject_id
           AND o.hadm_id = e.hadm_id
           AND o.stay_id = e.stay_id
           AND o.drug_class = e.drug_class
           AND o.poe_id = e.poe_id
        ),
        windowed AS (
          SELECT
            *,
            list_filter(
              qualifying_given_times,
              event_time -> event_time BETWEEN
                conversion_window_start AND conversion_window_end
            ) AS windowed_given_times,
            list_filter(
              not_given_times,
              event_time -> event_time BETWEEN
                conversion_window_start AND conversion_window_end
            ) AS windowed_not_given_times
          FROM joined
        )
        SELECT
          * EXCLUDE (
            qualifying_given_times, not_given_times,
            windowed_given_times, windowed_not_given_times
          ),
          list_min(windowed_given_times) AS first_administration_time,
          coalesce(list_count(windowed_given_times), 0)::BIGINT
            AS linked_given_events_n,
          coalesce(list_count(windowed_not_given_times), 0)::BIGINT
            AS linked_not_given_events_n
        FROM windowed
    """


def order_conversion_complete_sql(conversion_table: str) -> str:
    return f"""
        SELECT
          *,
          first_administration_time IS NOT NULL AS converted,
          date_diff(
            'second', ordertime, first_administration_time
          ) / 3600.0 AS first_dose_lag_hours,
          CASE
            WHEN first_administration_time IS NULL THEN 'not_converted'
            WHEN first_administration_time < ordertime
              THEN 'negative_minus2_to_0'
            WHEN first_administration_time
                 <= ordertime + INTERVAL 24 HOUR
              THEN '0_to_24h'
            WHEN first_administration_time
                 <= ordertime + INTERVAL 7 DAY
              THEN '24h_to_7d'
            ELSE 'over_7d'
          END AS lag_audit_category
        FROM "{conversion_table}"
    """


def build_order_analysis_units(
    con: duckdb.DuckDBPyConnection,
    *,
    candidate_table: str,
    names: dict[str, str],
    analyze: bool,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    gates: list[dict[str, object]] = []
    materialize(
        con,
        step=names["poe_keys"],
        table=names["poe_keys"],
        select_sql=candidate_poe_keys_sql(candidate_table),
        analyze=analyze,
    )
    gates.append(assert_unique(con, names["poe_keys"], ["poe_id"]))

    materialize(
        con,
        step=names["poe_for_candidates"],
        table=names["poe_for_candidates"],
        select_sql=poe_for_candidates_sql(names["poe_keys"]),
        analyze=analyze,
    )
    gates.append(
        assert_unique(con, names["poe_for_candidates"], ["poe_id"])
    )

    materialize(
        con,
        step=names["order_identity"],
        table=names["order_identity"],
        select_sql=order_identity_sql(
            candidate_table, names["poe_for_candidates"]
        ),
        analyze=analyze,
    )
    assert_required_columns(
        con,
        names["order_identity"],
        {"prescription_row_id", "poe_any_link", "poe_identity_link"},
    )
    gates.append(
        assert_unique(
            con, names["order_identity"], ["prescription_row_id"]
        )
    )
    gates.append(
        assert_row_equality(
            con,
            left_table=candidate_table,
            right_table=names["order_identity"],
            gate_name="candidate_to_poe_identity_no_fanout",
        )
    )

    materialize(
        con,
        step=names["assigned"],
        table=names["assigned"],
        select_sql=assigned_order_rows_sql(names["order_identity"]),
        analyze=analyze,
    )
    assert_required_columns(
        con,
        names["assigned"],
        {"prescription_row_id", "stay_candidate_count"},
    )
    gates.append(
        assert_unique(
            con, names["assigned"], ["prescription_row_id"]
        )
    )

    materialize(
        con,
        step=names["clusters"],
        table=names["clusters"],
        select_sql=order_clusters_sql(names["assigned"]),
        analyze=analyze,
    )
    order_key = [
        "subject_id",
        "hadm_id",
        "stay_id",
        "drug_class",
        "poe_id",
    ]
    gates.append(assert_unique(con, names["clusters"], order_key))

    materialize(
        con,
        step=names["eligible"],
        table=names["eligible"],
        select_sql=eligible_order_clusters_sql(names["clusters"]),
        analyze=analyze,
        resume=False,
    )
    gates.append(assert_unique(con, names["eligible"], order_key))

    stay_metrics = con.execute(
        f"""
        SELECT
          count(*)::BIGINT AS assigned_rows_n,
          coalesce(sum(stay_candidate_count), 0)::BIGINT
            AS pre_rank_join_rows_n,
          coalesce(max(stay_candidate_count), 0)::BIGINT
            AS max_stay_candidates_per_order
        FROM "{names['assigned']}"
        """
    ).fetchone()
    maximum_hadm_stays = int(
        con.execute(
            "SELECT coalesce(max(hadm_icu_stays_n), 0) FROM adult_stays"
        ).fetchone()[0]
    )
    stay_fanout_gate = {
        "gate": "order_to_stay_fanout_bounded_by_hadm_stays",
        "left_table": names["order_identity"],
        "right_table": names["assigned"],
        "left_rows_n": row_count(con, names["order_identity"]),
        "right_rows_n": int(stay_metrics[0]),
        "pre_rank_join_rows_n": int(stay_metrics[1]),
        "max_rows_per_left_key": int(stay_metrics[2]),
        "allowed_max_rows_per_left_key": maximum_hadm_stays,
        "pass": int(stay_metrics[2]) <= maximum_hadm_stays,
    }
    if not stay_fanout_gate["pass"]:
        raise RuntimeError(
            f"Order-to-stay fanout gate failed: {stay_fanout_gate}"
        )
    gates.append(stay_fanout_gate)

    metrics: dict[str, object] = {
        "candidate_rows_n": row_count(con, candidate_table),
        "candidate_poe_keys_n": row_count(con, names["poe_keys"]),
        "candidate_poe_identity_rows_n": row_count(
            con, names["poe_for_candidates"]
        ),
        "poe_any_link_rows_n": int(
            con.execute(
                f'SELECT count(*) FROM "{names["order_identity"]}" '
                "WHERE poe_any_link"
            ).fetchone()[0]
        ),
        "poe_identity_link_rows_n": int(
            con.execute(
                f'SELECT count(*) FROM "{names["order_identity"]}" '
                "WHERE poe_identity_link"
            ).fetchone()[0]
        ),
        "assigned_order_rows_n": int(stay_metrics[0]),
        "order_to_stay_pre_rank_rows_n": int(stay_metrics[1]),
        "max_stay_candidates_per_order": int(stay_metrics[2]),
        "order_clusters_all_n": row_count(con, names["clusters"]),
        "eligible_order_clusters_n": row_count(
            con, names["eligible"]
        ),
    }
    return metrics, gates


def build_emar_conversion_units(
    con: duckdb.DuckDBPyConnection,
    *,
    event_source_table: str,
    eligible_table: str,
    names: dict[str, str],
    analyze: bool,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    gates: list[dict[str, object]] = []
    materialize(
        con,
        step=names["stay_events"],
        table=names["stay_events"],
        select_sql=emar_stay_events_sql(event_source_table),
        analyze=analyze,
        resume=False,
    )
    event_key = ["emar_id", "emar_seq", "drug_class"]
    gates.append(assert_unique(con, names["stay_events"], event_key))

    materialize(
        con,
        step=names["emar_agg"],
        table=names["emar_agg"],
        select_sql=emar_order_key_agg_sql(names["stay_events"]),
        analyze=analyze,
        resume=False,
    )
    order_key = [
        "subject_id",
        "hadm_id",
        "stay_id",
        "drug_class",
        "poe_id",
    ]
    gates.append(assert_unique(con, names["emar_agg"], order_key))

    materialize(
        con,
        step=names["conversion"],
        table=names["conversion"],
        select_sql=order_conversion_sql(
            eligible_table, names["emar_agg"]
        ),
        analyze=analyze,
        resume=False,
    )
    gates.append(assert_unique(con, names["conversion"], order_key))
    gates.append(
        assert_row_equality(
            con,
            left_table=eligible_table,
            right_table=names["conversion"],
            gate_name="aggregated_emar_join_no_fanout",
        )
    )

    materialize(
        con,
        step=names["conversion_complete"],
        table=names["conversion_complete"],
        select_sql=order_conversion_complete_sql(names["conversion"]),
        analyze=analyze,
        resume=False,
    )
    gates.append(
        assert_row_equality(
            con,
            left_table=names["conversion"],
            right_table=names["conversion_complete"],
            gate_name="conversion_completion_no_row_change",
        )
    )

    stay_totals = con.execute(
        f"""
        SELECT
          count(*)::BIGINT,
          count(*) FILTER (
            WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
          )::BIGINT,
          count(*) FILTER (
            WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
              AND event_category = 'given_strict'
          )::BIGINT,
          count(*) FILTER (
            WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
              AND event_category = 'not_given'
          )::BIGINT,
          coalesce(max(stay_candidate_count), 0)::BIGINT
        FROM "{names['stay_events']}"
        """
    ).fetchone()
    agg_totals = con.execute(
        f"""
        SELECT
          coalesce(sum(events_n), 0)::BIGINT,
          coalesce(sum(given_strict_events_n), 0)::BIGINT,
          coalesce(sum(not_given_events_n), 0)::BIGINT,
          coalesce(max(events_n), 0)::BIGINT
        FROM "{names['emar_agg']}"
        """
    ).fetchone()
    event_conservation_gate = {
        "gate": "emar_preaggregation_event_conservation",
        "left_table": names["stay_events"],
        "right_table": names["emar_agg"],
        "left_rows_n": int(stay_totals[1]),
        "right_rows_n": int(agg_totals[0]),
        "left_given_n": int(stay_totals[2]),
        "right_given_n": int(agg_totals[1]),
        "left_not_given_n": int(stay_totals[3]),
        "right_not_given_n": int(agg_totals[2]),
        "pass": (
            int(stay_totals[1]) == int(agg_totals[0])
            and int(stay_totals[2]) == int(agg_totals[1])
            and int(stay_totals[3]) == int(agg_totals[2])
        ),
    }
    if not event_conservation_gate["pass"]:
        raise RuntimeError(
            "eMAR preaggregation conservation gate failed: "
            f"{event_conservation_gate}"
        )
    gates.append(event_conservation_gate)

    join_metrics = con.execute(
        f"""
        SELECT
          count(*)::BIGINT AS post_aggregate_join_rows_n,
          count(*) FILTER (
            WHERE linked_key_events_n IS NOT NULL
          )::BIGINT AS matched_order_keys_n,
          coalesce(sum(linked_key_events_n), 0)::BIGINT
            AS matched_event_rows_n,
          coalesce(sum(
            CASE
              WHEN linked_key_events_n IS NULL THEN 1
              ELSE linked_key_events_n
            END
          ), 0)::BIGINT AS event_level_left_join_rows_estimated,
          coalesce(max(linked_key_events_n), 0)::BIGINT
            AS max_event_level_rows_per_order_key
        FROM "{names['conversion']}"
        """
    ).fetchone()
    metrics: dict[str, object] = {
        "event_source_rows_n": row_count(con, event_source_table),
        "emar_stay_events_n": int(stay_totals[0]),
        "emar_stay_events_with_poe_n": int(stay_totals[1]),
        "max_stay_candidates_per_emar_event": int(stay_totals[4]),
        "emar_order_key_groups_n": row_count(con, names["emar_agg"]),
        "max_emar_events_per_order_key": int(agg_totals[3]),
        "eligible_order_clusters_n": row_count(con, eligible_table),
        "matched_order_keys_n": int(join_metrics[1]),
        "matched_event_rows_n": int(join_metrics[2]),
        "event_level_left_join_rows_estimated": int(join_metrics[3]),
        "post_aggregate_join_rows_n": int(join_metrics[0]),
        "event_level_expansion_rows_avoided_n": (
            int(join_metrics[3]) - int(join_metrics[0])
        ),
        "max_event_level_rows_per_order_key": int(join_metrics[4]),
        "converted_order_clusters_n": int(
            con.execute(
                f'SELECT count(*) FROM "{names["conversion_complete"]}" '
                "WHERE converted"
            ).fetchone()[0]
        ),
    }
    return metrics, gates


def downstream_table_names(
    *,
    prefix: str,
    compatible: bool,
) -> tuple[dict[str, str], dict[str, str]]:
    if compatible:
        order_names = {
            "poe_keys": "s02v2_candidate_poe_keys",
            "poe_for_candidates": "s02v2_poe_for_candidates",
            "order_identity": "s02v2_order_identity",
            "assigned": "assigned_order_rows",
            "clusters": "order_clusters_all",
            "eligible": "eligible_order_clusters",
        }
        emar_names = {
            "stay_events": "emar_stay_events",
            "emar_agg": "s02v2_emar_order_key_agg",
            "conversion": "order_conversion",
            "conversion_complete": "order_conversion_complete",
        }
    else:
        order_names = {
            "poe_keys": f"{prefix}_poe_keys",
            "poe_for_candidates": f"{prefix}_poe_for_candidates",
            "order_identity": f"{prefix}_order_identity",
            "assigned": f"{prefix}_assigned_order_rows",
            "clusters": f"{prefix}_order_clusters_all",
            "eligible": f"{prefix}_eligible_order_clusters",
        }
        emar_names = {
            "stay_events": f"{prefix}_emar_stay_events",
            "emar_agg": f"{prefix}_emar_order_key_agg",
            "conversion": f"{prefix}_order_conversion",
            "conversion_complete": f"{prefix}_order_conversion_complete",
        }
    return order_names, emar_names


def run_downstream_pilot(
    con: duckdb.DuckDBPyConnection,
    pilot_rows: int,
) -> pd.DataFrame:
    if not table_exists(con, "prescription_candidates"):
        raise RuntimeError(
            "Run --through-prescriptions before --pilot-downstream"
        )
    prefix = f"s02v2_pilot_downstream_{pilot_rows}"
    candidate_table = f"{prefix}_candidates"
    materialize(
        con,
        step=candidate_table,
        table=candidate_table,
        select_sql=f"""
            SELECT *
            FROM prescription_candidates
            ORDER BY prescription_row_id
            LIMIT {int(pilot_rows)}
        """,
        analyze=True,
    )
    gates: list[dict[str, object]] = [
        assert_unique(con, candidate_table, ["prescription_row_id"])
    ]
    candidate_n = row_count(con, candidate_table)
    gates.append(
        {
            "gate": "pilot_candidate_count_positive",
            "left_table": "prescription_candidates",
            "right_table": candidate_table,
            "left_rows_n": row_count(con, "prescription_candidates"),
            "right_rows_n": candidate_n,
            "pass": candidate_n > 0,
        }
    )

    order_names, emar_names = downstream_table_names(
        prefix=prefix, compatible=False
    )
    order_metrics, order_gates = build_order_analysis_units(
        con,
        candidate_table=candidate_table,
        names=order_names,
        analyze=True,
    )
    gates.extend(order_gates)
    eligible_n = row_count(con, order_names["eligible"])
    gates.append(
        {
            "gate": "pilot_eligible_order_count_positive",
            "left_table": order_names["clusters"],
            "right_table": order_names["eligible"],
            "left_rows_n": row_count(con, order_names["clusters"]),
            "right_rows_n": eligible_n,
            "pass": eligible_n > 0,
        }
    )

    pilot_event_source = f"{prefix}_emar_source"
    materialize(
        con,
        step=pilot_event_source,
        table=pilot_event_source,
        select_sql=pilot_emar_source_sql(order_names["eligible"]),
        analyze=True,
        resume=False,
    )
    pilot_event_n = row_count(con, pilot_event_source)
    gates.append(
        {
            "gate": "pilot_linked_emar_count_positive",
            "left_table": "emar_medication_events",
            "right_table": pilot_event_source,
            "left_rows_n": row_count(con, "emar_medication_events"),
            "right_rows_n": pilot_event_n,
            "pass": pilot_event_n > 0,
        }
    )
    emar_metrics, emar_gates = build_emar_conversion_units(
        con,
        event_source_table=pilot_event_source,
        eligible_table=order_names["eligible"],
        names=emar_names,
        analyze=True,
    )
    gates.extend(emar_gates)

    gate_frame = pd.DataFrame(gates)
    gate_frame.insert(0, "pilot_rows_requested", int(pilot_rows))
    write_csv(
        gate_frame,
        AUDIT / "02_v2_downstream_pilot_gates.csv",
    )
    if gate_frame.empty or not gate_frame["pass"].fillna(False).all():
        raise RuntimeError(
            "Stage 02 v2 downstream pilot gates failed:\n"
            + gate_frame.to_string(index=False)
        )

    metrics_frame = pd.concat(
        [
            pd.DataFrame([{"domain": "orders", **order_metrics}]),
            pd.DataFrame([{"domain": "emar_conversion", **emar_metrics}]),
        ],
        ignore_index=True,
    )
    write_csv(
        metrics_frame,
        AUDIT / "02_v2_downstream_pilot_metrics.csv",
    )
    (REPORTS / "02_stage02_v2_downstream_pilot.md").write_text(
        "\n".join(
            [
                "# Stage 02 v2 downstream limited-range pilot",
                "",
                "This pilot validates implementation shape only. The frozen",
                "six-class whitelist, exposure windows, event semantics, and",
                "VTE route/dose rule were not changed.",
                "",
                "## Metrics",
                "",
                "```text",
                metrics_frame.to_string(index=False),
                "```",
                "",
                "## Gates",
                "",
                "```text",
                gate_frame.to_string(index=False),
                "```",
                "",
                "All materialized joins passed the plan guard against",
                "BLOCKWISE_NL_JOIN, NESTED_LOOP_JOIN, and CROSS_PRODUCT.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    LOG(
        "DONE downstream pilot "
        f"order_metrics={order_metrics} emar_metrics={emar_metrics}"
    )
    return gate_frame


def write_join_fanout_audit(
    con: duckdb.DuckDBPyConnection,
    *,
    prescription_metrics: dict[str, int],
    order_metrics: dict[str, object],
    emar_metrics: dict[str, object],
) -> pd.DataFrame:
    identity_n = row_count(con, "s02v2_order_identity")
    assigned_n = row_count(con, "assigned_order_rows")
    order_clusters_n = row_count(con, "order_clusters_all")
    eligible_n = row_count(con, "eligible_order_clusters")
    conversion_n = row_count(con, "order_conversion")
    records = [
        {
            "join_step": "raw_prescription_to_direct_name",
            "left_table": "s02v2_prescriptions_projected",
            "right_table": "prescription_name_map",
            "left_rows_n": prescription_metrics["projected_rows_n"],
            "right_rows_n": row_count(con, "prescription_name_map"),
            "preaggregation_rows_n": prescription_metrics[
                "projected_rows_n"
            ],
            "post_join_rows_n": prescription_metrics["direct_rows_n"],
            "max_right_rows_per_key": 1,
            "fanout_detected": False,
            "implementation_status": "hash_join_pass",
        },
        {
            "join_step": "raw_prescription_to_pharmacy_id",
            "left_table": "s02v2_prescriptions_projected",
            "right_table": "s02v2_pharmacy_by_id",
            "left_rows_n": prescription_metrics["projected_rows_n"],
            "right_rows_n": row_count(con, "s02v2_pharmacy_by_id"),
            "preaggregation_rows_n": prescription_metrics[
                "projected_rows_n"
            ],
            "post_join_rows_n": prescription_metrics[
                "pharmacy_id_rows_n"
            ],
            "max_right_rows_per_key": 1,
            "fanout_detected": False,
            "implementation_status": "hash_join_pass",
        },
        {
            "join_step": "candidate_path_union_to_order_unit",
            "left_table": "three_candidate_paths",
            "right_table": "prescription_row_id",
            "left_rows_n": prescription_metrics[
                "candidate_union_rows_n"
            ],
            "right_rows_n": prescription_metrics[
                "projected_rows_n"
            ],
            "preaggregation_rows_n": prescription_metrics[
                "candidate_union_rows_n"
            ],
            "post_join_rows_n": prescription_metrics[
                "deduplicated_candidate_rows_n"
            ],
            "max_right_rows_per_key": 1,
            "fanout_detected": (
                prescription_metrics["duplicate_paths_removed_n"] > 0
            ),
            "implementation_status": "deduplicated_by_frozen_priority",
        },
        {
            "join_step": "candidate_to_poe_identity",
            "left_table": "prescription_candidates",
            "right_table": "s02v2_poe_for_candidates",
            "left_rows_n": prescription_metrics[
                "deduplicated_candidate_rows_n"
            ],
            "right_rows_n": order_metrics[
                "candidate_poe_identity_rows_n"
            ],
            "preaggregation_rows_n": prescription_metrics[
                "deduplicated_candidate_rows_n"
            ],
            "post_join_rows_n": identity_n,
            "max_right_rows_per_key": 1,
            "fanout_detected": False,
            "implementation_status": "left_hash_join_no_fanout",
        },
        {
            "join_step": "order_identity_to_icu_stay_pre_rank",
            "left_table": "s02v2_order_identity",
            "right_table": "adult_stays",
            "left_rows_n": identity_n,
            "right_rows_n": row_count(con, "adult_stays"),
            "preaggregation_rows_n": order_metrics[
                "order_to_stay_pre_rank_rows_n"
            ],
            "post_join_rows_n": assigned_n,
            "max_right_rows_per_key": order_metrics[
                "max_stay_candidates_per_order"
            ],
            "fanout_detected": (
                int(order_metrics["order_to_stay_pre_rank_rows_n"])
                > assigned_n
            ),
            "implementation_status": "ranked_to_one_stay",
        },
        {
            "join_step": "assigned_prescription_rows_to_order_clusters",
            "left_table": "assigned_order_rows",
            "right_table": "poe_id_drug_class_order_unit",
            "left_rows_n": assigned_n,
            "right_rows_n": order_clusters_n,
            "preaggregation_rows_n": assigned_n,
            "post_join_rows_n": order_clusters_n,
            "max_right_rows_per_key": None,
            "fanout_detected": False,
            "implementation_status": "grouped_before_emar_join",
        },
        {
            "join_step": "eligible_orders_to_event_level_emar_estimate",
            "left_table": "eligible_order_clusters",
            "right_table": "emar_stay_events",
            "left_rows_n": eligible_n,
            "right_rows_n": emar_metrics["emar_stay_events_n"],
            "preaggregation_rows_n": emar_metrics[
                "event_level_left_join_rows_estimated"
            ],
            "post_join_rows_n": emar_metrics[
                "event_level_left_join_rows_estimated"
            ],
            "max_right_rows_per_key": emar_metrics[
                "max_event_level_rows_per_order_key"
            ],
            "fanout_detected": (
                int(
                    emar_metrics[
                        "event_level_left_join_rows_estimated"
                    ]
                )
                > eligible_n
            ),
            "implementation_status": "not_executed_estimate_only",
        },
        {
            "join_step": "eligible_orders_to_preaggregated_emar",
            "left_table": "eligible_order_clusters",
            "right_table": "s02v2_emar_order_key_agg",
            "left_rows_n": eligible_n,
            "right_rows_n": emar_metrics["emar_order_key_groups_n"],
            "preaggregation_rows_n": eligible_n,
            "post_join_rows_n": conversion_n,
            "max_right_rows_per_key": 1,
            "fanout_detected": False,
            "implementation_status": "left_hash_join_no_fanout",
        },
    ]
    frame = pd.DataFrame(records)
    frame["row_ratio_post_to_left"] = (
        frame["post_join_rows_n"] / frame["left_rows_n"]
    )
    write_csv(frame, AUDIT / "02_v2_join_fanout_audit.csv")
    return frame


def write_vte_route_expression_audit(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    summary = con.execute(
        """
        SELECT
          count(*)::BIGINT AS identity_linked_vte_clusters_n,
          count(*) FILTER (
            WHERE lower(coalesce(route, '')) SIMILAR TO
              '%(sc|sq|subcut)%'
          )::BIGINT AS legacy_similar_to_matches_n,
          count(*) FILTER (
            WHERE regexp_matches(
              lower(coalesce(route, '')), '(sc|sq|subcut)'
            )
          )::BIGINT AS frozen_route_rule_matches_n,
          count(*) FILTER (
            WHERE (
              ingredient = 'heparin'
              AND parsed_dose IN (5000, 7500)
            )
            OR (
              ingredient = 'enoxaparin'
              AND parsed_dose BETWEEN 20 AND 60
            )
          )::BIGINT AS frozen_dose_rule_matches_n,
          count(*) FILTER (
            WHERE regexp_matches(
              lower(coalesce(route, '')), '(sc|sq|subcut)'
            )
              AND (
                (
                  ingredient = 'heparin'
                  AND parsed_dose IN (5000, 7500)
                )
                OR (
                  ingredient = 'enoxaparin'
                  AND parsed_dose BETWEEN 20 AND 60
                )
              )
          )::BIGINT AS frozen_joint_rule_matches_n
        FROM order_clusters_all
        WHERE drug_class = 'vte_prophylaxis'
          AND poe_identity_link
        """
    ).fetchdf()
    routes = con.execute(
        """
        SELECT coalesce(route, '<NULL>') AS route, count(*)::BIGINT AS rows_n
        FROM order_clusters_all
        WHERE drug_class = 'vte_prophylaxis'
          AND poe_identity_link
        GROUP BY route
        ORDER BY rows_n DESC, route
        """
    ).fetchdf()
    write_csv(summary, AUDIT / "02_vte_route_expression_audit.csv")
    write_csv(routes, AUDIT / "02_vte_route_distribution.csv")
    (REPORTS / "02_vte_route_expression_fix.md").write_text(
        "\n".join(
            [
                "# Stage 02 VTE route-expression implementation audit",
                "",
                "The frozen semantic rule remains SC/SQ/subcutaneous route",
                "plus heparin 5,000/7,500 units or enoxaparin 20–60 mg.",
                "",
                "DuckDB 1.5.3 returned zero matches for the legacy",
                "`SIMILAR TO '%(sc|sq|subcut)%'` implementation even though",
                "the source route distribution contains `SC`. The v2",
                "implementation therefore uses `regexp_matches` to express",
                "the same pre-frozen contains rule. No route or dose category",
                "was added, removed, or selected from outcome results.",
                "",
                "```text",
                summary.to_string(index=False),
                "```",
                "",
                "```text",
                routes.head(25).to_string(index=False),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return summary


def write_vte_administration_field_audit(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    summary = con.execute(
        """
        SELECT
          count(*)::BIGINT AS vte_emar_stay_events_n,
          count(*) FILTER (
            WHERE event_category = 'given_strict'
          )::BIGINT AS strict_given_events_n,
          count(*) FILTER (
            WHERE event_category = 'given_strict'
              AND route IS NOT NULL AND trim(route) <> ''
          )::BIGINT AS strict_given_route_nonmissing_n,
          count(*) FILTER (
            WHERE event_category = 'given_strict'
              AND dose_given_num IS NOT NULL
          )::BIGINT AS strict_given_numeric_dose_nonmissing_n,
          count(*) FILTER (
            WHERE event_category = 'not_given'
          )::BIGINT AS not_given_events_n
        FROM emar_stay_events
        WHERE drug_class = 'vte_prophylaxis'
        """
    ).fetchdf()
    write_csv(
        summary,
        AUDIT / "02_vte_administration_field_availability.csv",
    )
    (REPORTS / "02_vte_administration_field_audit.md").write_text(
        "\n".join(
            [
                "# Stage 02 VTE administration-field audit",
                "",
                "Contract section 4.1 applies the frozen subcutaneous route",
                "and prophylactic-dose rule to strict VTE orders. Section 4.2",
                "defines actual administration by strict class match, ICU",
                "timing, positive event semantics, and absence of a",
                "complete-dose-not-given override; it explicitly does not",
                "require a numeric administered dose.",
                "",
                "The route and numeric-dose fields below are therefore",
                "availability audit fields, not additional administration",
                "eligibility gates.",
                "",
                "```text",
                summary.to_string(index=False),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return summary


def run_full_downstream_stage(
    con: duckdb.DuckDBPyConnection,
    whitelist: pd.DataFrame,
    *,
    started: float,
) -> dict[str, object]:
    pilot_gate_path = AUDIT / "02_v2_downstream_pilot_gates.csv"
    if not pilot_gate_path.exists():
        raise RuntimeError("Run --pilot-downstream before --full")
    pilot_gates = pd.read_csv(pilot_gate_path)
    pilot_pass = (
        pilot_gates["pass"]
        .astype(str)
        .str.strip()
        .str.lower()
        .eq("true")
    )
    if pilot_gates.empty or not pilot_pass.all():
        raise RuntimeError(
            "Stage 02 v2 downstream pilot gates are not all passing"
        )

    prescription_metrics = run_full_prescription_stage(con, whitelist)
    order_names, emar_names = downstream_table_names(
        prefix="s02v2_full", compatible=True
    )
    order_metrics, order_gates = build_order_analysis_units(
        con,
        candidate_table="prescription_candidates",
        names=order_names,
        analyze=False,
    )
    vte_route_audit = write_vte_route_expression_audit(con)
    emar_metrics, emar_gates = build_emar_conversion_units(
        con,
        event_source_table="emar_medication_events",
        eligible_table=order_names["eligible"],
        names=emar_names,
        analyze=False,
    )
    vte_administration_audit = write_vte_administration_field_audit(
        con
    )

    full_gates = pd.DataFrame(order_gates + emar_gates)
    write_csv(full_gates, AUDIT / "02_v2_full_downstream_gates.csv")
    if full_gates.empty or not full_gates["pass"].fillna(False).all():
        raise RuntimeError(
            "Stage 02 v2 full downstream gates failed:\n"
            + full_gates.to_string(index=False)
        )
    full_metrics = pd.concat(
        [
            pd.DataFrame(
                [{"domain": "prescriptions", **prescription_metrics}]
            ),
            pd.DataFrame([{"domain": "orders", **order_metrics}]),
            pd.DataFrame(
                [{"domain": "emar_conversion", **emar_metrics}]
            ),
        ],
        ignore_index=True,
    )
    write_csv(full_metrics, AUDIT / "02_v2_full_downstream_metrics.csv")

    build_raw_interface_key_tables(con)
    cardinality = write_full_key_cardinality_audit(con)
    join_audit = write_join_fanout_audit(
        con,
        prescription_metrics=prescription_metrics,
        order_metrics=order_metrics,
        emar_metrics=emar_metrics,
    )

    legacy = load_legacy_module()
    summary = legacy.summarize_primary(con)
    (REPORTS / "02_primary_estimands.md").write_text(
        legacy.render_report(summary), encoding="utf-8"
    )
    implementation_report = "\n".join(
        [
            "# Stage 02 v2 implementation and production audit",
            "",
            "The frozen scientific contract, six drug classes, strict name",
            "whitelist, VTE route/dose rule, event semantics, and time windows",
            "were unchanged. This is an implementation audit, not a new",
            "statistical or causal analysis.",
            "",
            "## Failure cause and correction",
            "",
            "The legacy full-gzip prescription query used two conditional",
            "BLOCKWISE_NL_JOIN operators. The v2 query split direct-name,",
            "pharmacy-id, and unreachable POE-fallback paths; each path used",
            "a guarded equality plan and was deduplicated by the frozen",
            "priority before downstream joins.",
            "",
            "eMAR was assigned to ICU stays and aggregated to one row per",
            "subject/hadm/stay/drug-class/poe_id key before joining to the",
            "order unit. Ordered timestamp lists preserve the frozen",
            "order-specific window without event-level many-to-many expansion.",
            "",
            "For VTE, the frozen subcutaneous route/prophylactic-dose rule is",
            "applied to the strict order as specified in contract section 4.1.",
            "The administration event follows section 4.2 and is not",
            "discarded for missing eMAR_detail route or numeric dose.",
            "",
            "## Full metrics",
            "",
            "```text",
            full_metrics.to_string(index=False),
            "```",
            "",
            "## Join fanout audit",
            "",
            "```text",
            join_audit.to_string(index=False),
            "```",
            "",
            "## Key-cardinality audit",
            "",
            "The complete machine-readable table contains raw full-table and",
            "frozen-whitelist subset profiles for prescriptions, pharmacy,",
            "POE, and eMAR.",
            "",
            "```text",
            cardinality.to_string(index=False),
            "```",
            "",
            "The abandoned multi-hour run remains classified as an",
            "implementation failure. No statistical result was inferred from",
            "that run.",
            "",
        ]
    )
    (REPORTS / "02_stage02_v2_implementation.md").write_text(
        implementation_report, encoding="utf-8"
    )

    metadata = script_metadata(started, SCRIPT)
    metadata.update(summary)
    metadata["prescription_metrics"] = prescription_metrics
    metadata["order_metrics"] = order_metrics
    metadata["emar_metrics"] = emar_metrics
    metadata["vte_route_expression_audit"] = (
        vte_route_audit.to_dict(orient="records")
    )
    metadata["vte_administration_field_audit"] = (
        vte_administration_audit.to_dict(orient="records")
    )
    metadata["all_full_gates_pass"] = bool(
        full_gates["pass"].fillna(False).all()
    )
    write_json(
        metadata,
        MANIFESTS / "02_build_primary_estimands_v2.json",
    )
    LOG(
        "DONE full downstream Stage 02 v2 "
        f"summary={summary} order_metrics={order_metrics} "
        f"emar_metrics={emar_metrics}"
    )
    return metadata


def main() -> None:
    started = time.time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument("--through-prescriptions", action="store_true")
    parser.add_argument("--pilot-downstream", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--pilot-rows", type=int, default=250_000)
    args = parser.parse_args()
    if not any(
        (
            args.pilot_only,
            args.through_prescriptions,
            args.pilot_downstream,
            args.full,
        )
    ):
        parser.error(
            "Select --pilot-only, --through-prescriptions, or "
            "--pilot-downstream, or --full."
        )

    ensure_dirs()
    AUDIT.mkdir(parents=True, exist_ok=True)
    PLANS.mkdir(parents=True, exist_ok=True)
    verify_frozen_contract()
    whitelist = load_whitelist("strict")
    if whitelist["drug_class"].nunique() != 6:
        raise RuntimeError("Frozen strict whitelist no longer has six classes")
    con = connect_duckdb()
    required = (
        "adult_stays",
        "pharmacy_name_candidates",
        "poe_identity",
        "prescription_name_map",
        "emar_medication_events",
    )
    missing = [table for table in required if not table_exists(con, table)]
    if missing:
        raise RuntimeError(f"Missing prerequisite tables: {missing}")
    if args.pilot_only:
        run_pilot(con, whitelist, args.pilot_rows)
    if args.through_prescriptions:
        run_full_prescription_stage(con, whitelist)
    if args.pilot_downstream:
        run_downstream_pilot(con, args.pilot_rows)
    if args.full:
        run_full_downstream_stage(
            con, whitelist, started=started
        )
    con.close()
    LOG(
        "DONE Stage 02 v2 entrypoint "
        f"pilot_only={args.pilot_only} "
        f"through_prescriptions={args.through_prescriptions} "
        f"pilot_downstream={args.pilot_downstream} "
        f"full={args.full}"
    )


if __name__ == "__main__":
    main()
