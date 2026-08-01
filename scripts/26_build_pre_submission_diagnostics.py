from __future__ import annotations

import hashlib
import os
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
CACHE = PROJECT / "cache"
BASE_DB = CACHE / "n1_validity.duckdb"
SCRATCH_DB = CACHE / "jamia_pre_submission_v1_0.duckdb"
TMP = CACHE / "jamia_pre_submission_tmp"
OUTPUT = PROJECT / "outputs" / "jamia_pre_submission_v1_0"
TABLES = OUTPUT / "tables"
MODEL_INPUTS = OUTPUT / "model_inputs"
LOGS = OUTPUT / "logs"
PLANS = OUTPUT / "plans"
MANIFESTS = OUTPUT / "manifests"
REPORTS = PROJECT / "reports"
CONTRACTS = PROJECT / "contracts"
MIMIC = Path(os.environ["MIMIC_IV_ROOT"])
CALENDAR_CSV = (
    PROJECT
    / "outputs"
    / "jamia_observability_v1_1"
    / "tables"
    / "stay_calendar_alignment_audit.csv"
)
A1_POST_CSV = (
    PROJECT
    / "outputs"
    / "jamia_observability_v1_1"
    / "model_inputs"
    / "anchor_a1_corrected_post.csv"
)
A2_POST_CSV = (
    PROJECT
    / "outputs"
    / "jamia_observability_v1_1"
    / "model_inputs"
    / "anchor_a2_corrected_post.csv"
)
CONTRACT_FILES = {
    "jamia_pre_submission_sensitivity_addendum_v1.0.md":
        "219b75672c02498b149ee33ae0c39202a9bb9d5819670dff352e9c6e96f164e6",
    "jamia_pre_submission_sensitivity_status_clarification_v1.0.md":
        "8aedeec9bb44d7d6c1b47479e8a470161c2ab6ea0b082369dd6e9b6a1a1195b1",
    "jamia_pre_submission_nonconversion_timing_correction_v1.0.md":
        "9569090405cac52ec1e9bbae742dac82e95bf8960ffae87be8cf79547327ba32",
}
START = time.time()


for path in (TMP, TABLES, MODEL_INPUTS, LOGS, PLANS, MANIFESTS, REPORTS):
    path.mkdir(parents=True, exist_ok=True)

LOG_PATH = LOGS / "26_build_pre_submission_diagnostics.log"


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
    mapping = ", ".join(f"'{name}':'VARCHAR'" for name in columns)
    return (
        f"read_csv('{sql_path(path)}', header=true, compression='gzip', "
        f"columns={{{mapping}}}, strict_mode=true, ignore_errors=false, "
        "null_padding=false, quote='\"', escape='\"')"
    )


def verify_contracts() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for name, expected in CONTRACT_FILES.items():
        path = CONTRACTS / name
        observed = sha256(path)
        checks.append(
            {
                "file": name,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "match": expected == observed,
            }
        )
    if not checks or not all(bool(row["match"]) for row in checks):
        raise RuntimeError(f"Sensitivity contract verification failed: {checks}")
    return checks


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


def save_plan(con: duckdb.DuckDBPyConnection, name: str, query: str) -> str:
    plan_rows = con.execute("EXPLAIN " + query).fetchall()
    plan = "\n".join(str(row[-1]) for row in plan_rows)
    (PLANS / f"{name}.txt").write_text(plan, encoding="utf-8")
    upper = plan.upper()
    if "CROSS_PRODUCT" in upper or "BLOCKWISE_NL_JOIN" in upper:
        raise RuntimeError(f"Unsafe join operator in {name}:\n{plan}")
    return plan


def export_query(
    con: duckdb.DuckDBPyConnection, query: str, path: Path
) -> None:
    frame = con.execute(query).fetchdf()
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    log(f"CHECKPOINT file={path.name} rows={len(frame)}")


def bootstrap_conversion(
    frame: pd.DataFrame, replicates: int = 1000, seed: int = 20260731
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    records: list[dict[str, object]] = []
    scopes = sorted(frame["drug_class"].unique().tolist()) + ["all_classes"]
    for scope in scopes:
        subset = frame if scope == "all_classes" else frame.loc[
            frame["drug_class"].eq(scope)
        ]
        subject = (
            subset.groupby("subject_id", as_index=False)
            .agg(
                eligible_n=("poe_id", "size"),
                strict_n=("converted", "sum"),
                relaxed_n=("relaxed_converted", "sum"),
            )
            .sort_values("subject_id")
        )
        values = subject[["eligible_n", "strict_n", "relaxed_n"]].to_numpy(
            dtype=np.int64
        )
        n_subjects = len(values)
        strict_boot = np.empty(replicates, dtype=float)
        relaxed_boot = np.empty(replicates, dtype=float)
        for index in range(replicates):
            sample = rng.integers(0, n_subjects, size=n_subjects)
            totals = values[sample].sum(axis=0)
            strict_boot[index] = 100 * totals[1] / totals[0]
            relaxed_boot[index] = 100 * totals[2] / totals[0]
        eligible = int(values[:, 0].sum())
        strict = int(values[:, 1].sum())
        relaxed = int(values[:, 2].sum())
        records.append(
            {
                "drug_class": scope,
                "subjects_n": n_subjects,
                "eligible_order_units_n": eligible,
                "strict_identity_converted_n": strict,
                "strict_identity_conversion_pct": 100 * strict / eligible,
                "strict_cluster_boot_ci_low_pct": float(
                    np.quantile(strict_boot, 0.025)
                ),
                "strict_cluster_boot_ci_high_pct": float(
                    np.quantile(strict_boot, 0.975)
                ),
                "class_window_converted_n": relaxed,
                "class_window_conversion_pct": 100 * relaxed / eligible,
                "class_window_cluster_boot_ci_low_pct": float(
                    np.quantile(relaxed_boot, 0.025)
                ),
                "class_window_cluster_boot_ci_high_pct": float(
                    np.quantile(relaxed_boot, 0.975)
                ),
                "absolute_conversion_gain_pct_points": 100
                * (relaxed - strict)
                / eligible,
                "bootstrap_replicates": replicates,
                "bootstrap_seed": seed,
            }
        )
    return pd.DataFrame(records)


def build_participant_flow(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    icu = pd.read_csv(
        MIMIC / "icu" / "icustays.csv.gz",
        usecols=["subject_id", "hadm_id", "stay_id", "intime", "outtime"],
    )
    patients = pd.read_csv(
        MIMIC / "hosp" / "patients.csv.gz",
        usecols=["subject_id", "anchor_age", "anchor_year"],
    )
    admissions = pd.read_csv(
        MIMIC / "hosp" / "admissions.csv.gz",
        usecols=["hadm_id"],
    )
    joined = icu.merge(patients, on="subject_id", how="inner").merge(
        admissions, on="hadm_id", how="inner"
    )
    intime = pd.to_datetime(joined["intime"], errors="coerce")
    outtime = pd.to_datetime(joined["outtime"], errors="coerce")
    age = joined["anchor_age"] + intime.dt.year - joined["anchor_year"]
    adult = age.ge(18)
    valid_time = intime.notna() & outtime.notna() & outtime.gt(intime)
    records = [
        {
            "cohort": "source_observability",
            "step": "raw ICU stays",
            "rows_n": len(icu),
        },
        {
            "cohort": "source_observability",
            "step": "linked to patient and admission records",
            "rows_n": len(joined),
        },
        {
            "cohort": "source_observability",
            "step": "adult age at ICU entry",
            "rows_n": int(adult.sum()),
        },
        {
            "cohort": "source_observability",
            "step": "valid nonmissing ICU interval; final adult stays",
            "rows_n": int((adult & valid_time).sum()),
        },
    ]
    a1_flow = con.execute(
        """
        SELECT 'A1_post_implementation' AS cohort,
               'post-implementation adult stays' AS step,
               count(*)::BIGINT AS rows_n
        FROM base.adult_stays s JOIN stay_calendar c USING (stay_id)
        WHERE c.deployment_era = 'post_implementation'
        UNION ALL
        SELECT 'A1_post_implementation',
               'exactly one ICU stay per subject and valid outcome', count(*)
        FROM a1_post
        UNION ALL
        SELECT 'A2_post_implementation',
               'post-implementation adult first ICU stays', count(*)
        FROM base.adult_stays s JOIN stay_calendar c USING (stay_id)
        WHERE c.deployment_era = 'post_implementation'
          AND s.subject_stay_order = 1
        UNION ALL
        SELECT 'A2_post_implementation',
               'operational ICD-sepsis admissions', count(*)
        FROM base.adult_stays s
        JOIN stay_calendar c USING (stay_id)
        JOIN base.diagnosis_flags d ON s.hadm_id = d.hadm_id
        WHERE c.deployment_era = 'post_implementation'
          AND s.subject_stay_order = 1 AND d.sepsis_icd_flag = 1
        UNION ALL
        SELECT 'A2_post_implementation',
               'after acid-indication exclusions; final cohort', count(*)
        FROM a2_post
        UNION ALL
        SELECT 'A2_post_implementation',
               '48-hour landmark eligible', sum(landmark_48h_eligible)::BIGINT
        FROM a2_post
        """
    ).fetchdf()
    return pd.concat([pd.DataFrame(records), a1_flow], ignore_index=True)


def main() -> None:
    contract_checks = verify_contracts()
    log("PASS pre-submission contract hashes")
    if not BASE_DB.exists():
        raise FileNotFoundError(BASE_DB)
    con = duckdb.connect(str(SCRATCH_DB))
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{sql_path(TMP)}'")
    try:
        con.execute(f"ATTACH '{sql_path(BASE_DB)}' AS base (READ_ONLY)")
        run_step(
            con,
            "materialize corrected stay calendar",
            f"""
            CREATE OR REPLACE TABLE stay_calendar AS
            SELECT * FROM read_csv_auto(
              '{sql_path(CALENDAR_CSV)}', header=true, sample_size=-1,
              ignore_errors=false, strict_mode=true
            )
            """,
            "stay_calendar",
        )
        run_step(
            con,
            "materialize post-implementation order units",
            """
            CREATE OR REPLACE TABLE post_orders AS
            SELECT o.*
            FROM base.order_conversion_complete o
            JOIN stay_calendar c USING (stay_id)
            WHERE c.deployment_era = 'post_implementation'
            """,
            "post_orders",
        )
        post_n = int(con.execute("SELECT count(*) FROM post_orders").fetchone()[0])
        if post_n != 264_171:
            raise RuntimeError(f"Unexpected post order denominator: {post_n}")

        run_step(
            con,
            "preaggregate strict-given eMAR times to stay and class",
            """
            CREATE OR REPLACE TABLE given_times_by_stay_class AS
            SELECT stay_id, drug_class,
                   list(charttime ORDER BY charttime) AS given_times,
                   count(*) AS given_events_n
            FROM base.emar_stay_events
            WHERE event_category = 'given_strict' AND charttime IS NOT NULL
            GROUP BY stay_id, drug_class
            """,
            "given_times_by_stay_class",
        )
        relaxed_select = """
            SELECT o.*,
                   list_min(list_filter(
                     g.given_times,
                     x -> x >= o.conversion_window_start
                       AND x <= o.conversion_window_end
                   )) AS relaxed_first_administration_time
            FROM post_orders o
            LEFT JOIN given_times_by_stay_class g
              ON o.stay_id = g.stay_id AND o.drug_class = g.drug_class
        """
        plan = save_plan(con, "relaxed_class_window_full_explain", relaxed_select)
        if "HASH_JOIN" not in plan.upper():
            raise RuntimeError("Relaxed conversion plan lacks bounded hash join")
        run_step(
            con,
            "limited 10000-order relaxed conversion pilot",
            "CREATE OR REPLACE TEMP TABLE relaxed_pilot AS "
            + relaxed_select.replace("FROM post_orders o", "FROM (SELECT * FROM post_orders LIMIT 10000) o"),
            "relaxed_pilot",
        )
        pilot_n, pilot_unique = con.execute(
            """
            SELECT count(*), count(DISTINCT (stay_id, drug_class, poe_id))
            FROM relaxed_pilot
            """
        ).fetchone()
        if int(pilot_n) != 10_000 or int(pilot_unique) != 10_000:
            raise RuntimeError(
                f"Relaxed pilot multiplicity failure: rows={pilot_n}, unique={pilot_unique}"
            )
        run_step(
            con,
            "full relaxed class-window conversion",
            """
            CREATE OR REPLACE TABLE relaxed_order_conversion AS
            SELECT *,
                   (relaxed_first_administration_time IS NOT NULL)
                     AS relaxed_converted
            FROM (
            """
            + relaxed_select
            + ")",
            "relaxed_order_conversion",
        )
        relaxed_n, relaxed_unique = con.execute(
            """
            SELECT count(*), count(DISTINCT (stay_id, drug_class, poe_id))
            FROM relaxed_order_conversion
            """
        ).fetchone()
        if int(relaxed_n) != post_n or int(relaxed_unique) != post_n:
            raise RuntimeError("Full relaxed conversion changed the frozen order unit")

        conversion_rows = con.execute(
            """
            SELECT subject_id, drug_class, poe_id,
                   converted::INTEGER AS converted,
                   relaxed_converted::INTEGER AS relaxed_converted
            FROM relaxed_order_conversion
            """
        ).fetchdf()
        conversion_boot = bootstrap_conversion(conversion_rows)
        conversion_boot.to_csv(
            TABLES / "conversion_strict_vs_class_window_cluster_bootstrap.csv",
            index=False,
            encoding="utf-8-sig",
        )
        log(
            "CHECKPOINT file=conversion_strict_vs_class_window_cluster_bootstrap.csv "
            f"rows={len(conversion_boot)}"
        )

        run_step(
            con,
            "materialize nonconverted candidate POE keys",
            """
            CREATE OR REPLACE TABLE nonconverted_poe_keys AS
            SELECT DISTINCT subject_id, hadm_id, poe_id
            FROM post_orders
            WHERE NOT converted
            """,
            "nonconverted_poe_keys",
        )
        poe_columns = [
            "poe_id", "poe_seq", "subject_id", "hadm_id", "ordertime",
            "order_type", "order_subtype", "transaction_type",
            "discontinue_of_poe_id", "discontinued_by_poe_id",
            "order_provider_id", "order_status",
        ]
        poe_scan = explicit_csv(MIMIC / "hosp" / "poe.csv.gz", poe_columns)
        poe_query = f"""
            SELECT p.*,
                   coalesce(k_direct.subject_id, k_reference.subject_id)
                     AS candidate_subject_id,
                   coalesce(k_direct.hadm_id, k_reference.hadm_id)
                     AS candidate_hadm_id,
                   coalesce(k_direct.poe_id, k_reference.poe_id)
                     AS candidate_poe_id,
                   (k_reference.poe_id IS NOT NULL
                     AND k_direct.poe_id IS NULL) AS discontinues_candidate
            FROM {poe_scan} p
            LEFT JOIN nonconverted_poe_keys k_direct
              ON TRY_CAST(p.subject_id AS BIGINT) = k_direct.subject_id
             AND TRY_CAST(p.hadm_id AS BIGINT) = k_direct.hadm_id
             AND p.poe_id = k_direct.poe_id
            LEFT JOIN nonconverted_poe_keys k_reference
              ON TRY_CAST(p.subject_id AS BIGINT) = k_reference.subject_id
             AND TRY_CAST(p.hadm_id AS BIGINT) = k_reference.hadm_id
             AND p.discontinue_of_poe_id = k_reference.poe_id
            WHERE k_direct.poe_id IS NOT NULL
               OR k_reference.poe_id IS NOT NULL
        """
        save_plan(con, "poe_status_projection_explain", poe_query)
        run_step(
            con,
            "project POE status for nonconverted order units",
            "CREATE OR REPLACE TABLE poe_status_subset AS " + poe_query,
            "poe_status_subset",
        )
        run_step(
            con,
            "aggregate POE status flags",
            r"""
            CREATE OR REPLACE TABLE poe_status_flags AS
            SELECT candidate_subject_id AS subject_id,
                   candidate_hadm_id AS hadm_id,
                   candidate_poe_id AS poe_id,
                   max((
                     regexp_matches(lower(coalesce(order_status, '')), 'cancel|discontinu')
                     OR regexp_matches(lower(coalesce(transaction_type, '')), 'cancel|discontinu|(^|[^a-z])dc([^a-z]|$)')
                     OR regexp_matches(lower(coalesce(order_type, '')), 'cancel|discontinu|(^|[^a-z])dc([^a-z]|$)')
                     OR regexp_matches(lower(coalesce(order_subtype, '')), 'cancel|discontinu|(^|[^a-z])dc([^a-z]|$)')
                     OR nullif(trim(coalesce(discontinue_of_poe_id, '')), '') IS NOT NULL
                     OR nullif(trim(coalesce(discontinued_by_poe_id, '')), '') IS NOT NULL
                   )::INTEGER)::BOOLEAN AS explicit_cancel_discontinue,
                   min(TRY_CAST(ordertime AS TIMESTAMP)) FILTER (
                     WHERE discontinues_candidate
                        OR regexp_matches(
                          lower(concat_ws(' ', transaction_type,
                            order_type, order_subtype)),
                          'cancel|discontinu|(^|[^a-z])dc([^a-z]|$)'
                        )
                   ) AS earliest_explicit_dc_time,
                   max(regexp_matches(
                     lower(concat_ws(' ', order_status, transaction_type)),
                     'inactive|stopp?ed|complete'
                   )::INTEGER)::BOOLEAN AS ambiguous_closed_status,
                   max(regexp_matches(
                     lower(concat_ws(' ', order_type, order_subtype)),
                     'prn|as needed|once|one time|stat|sliding|conditional|protocol'
                   )::INTEGER)::BOOLEAN AS conditional_protocol,
                   string_agg(DISTINCT coalesce(order_status, '<null>'), '|')
                     AS order_status_values,
                   string_agg(DISTINCT coalesce(transaction_type, '<null>'), '|')
                     AS transaction_type_values,
                   string_agg(DISTINCT coalesce(order_type, '<null>'), '|')
                     AS order_type_values,
                   string_agg(DISTINCT coalesce(order_subtype, '<null>'), '|')
                     AS order_subtype_values
            FROM poe_status_subset
            GROUP BY candidate_subject_id, candidate_hadm_id,
                     candidate_poe_id
            """,
            "poe_status_flags",
        )

        pharmacy_columns = [
            "subject_id", "hadm_id", "pharmacy_id", "poe_id", "starttime",
            "stoptime", "medication", "proc_type", "status", "entertime",
            "verifiedtime", "route", "frequency", "disp_sched",
            "infusion_type", "sliding_scale", "lockout_interval", "basal_rate",
            "one_hr_max", "doses_per_24_hrs", "duration",
            "duration_interval", "expiration_value", "expiration_unit",
            "expirationdate", "dispensation", "fill_quantity",
        ]
        pharmacy_scan = explicit_csv(
            MIMIC / "hosp" / "pharmacy.csv.gz", pharmacy_columns
        )
        pharmacy_query = f"""
            SELECT p.*
            FROM {pharmacy_scan} p
            JOIN nonconverted_poe_keys k
              ON TRY_CAST(p.subject_id AS BIGINT) = k.subject_id
             AND TRY_CAST(p.hadm_id AS BIGINT) = k.hadm_id
             AND p.poe_id = k.poe_id
        """
        save_plan(con, "pharmacy_status_projection_explain", pharmacy_query)
        run_step(
            con,
            "project pharmacy status for nonconverted order units",
            "CREATE OR REPLACE TABLE pharmacy_status_subset AS "
            + pharmacy_query,
            "pharmacy_status_subset",
        )
        run_step(
            con,
            "aggregate pharmacy status and conditional flags",
            r"""
            CREATE OR REPLACE TABLE pharmacy_status_flags AS
            SELECT TRY_CAST(subject_id AS BIGINT) AS subject_id,
                   TRY_CAST(hadm_id AS BIGINT) AS hadm_id, poe_id,
                   max(regexp_matches(
                     lower(coalesce(status, '')),
                     'cancel|discontinu|(^|[^a-z])dc([^a-z]|$)'
                   )::INTEGER)::BOOLEAN AS explicit_cancel_discontinue,
                   max(regexp_matches(
                     lower(coalesce(status, '')),
                     'inactive|stopp?ed|complete'
                   )::INTEGER)::BOOLEAN AS ambiguous_closed_status,
                   max((
                     lower(trim(coalesce(sliding_scale, ''))) IN
                       ('y', 'yes', '1', 'true', 't')
                     OR regexp_matches(
                       lower(concat_ws(' ', frequency, proc_type, disp_sched)),
                       'prn|as needed|once|one time|stat|sliding|conditional|protocol'
                     )
                     OR regexp_matches(
                       lower(coalesce(doses_per_24_hrs, '')),
                       'prn|as needed'
                     )
                   )::INTEGER)::BOOLEAN AS conditional_protocol,
                   string_agg(DISTINCT coalesce(status, '<null>'), '|')
                     AS pharmacy_status_values,
                   string_agg(DISTINCT coalesce(frequency, '<null>'), '|')
                     AS frequency_values,
                   string_agg(DISTINCT coalesce(sliding_scale, '<null>'), '|')
                     AS sliding_scale_values
            FROM pharmacy_status_subset
            GROUP BY subject_id, hadm_id, poe_id
            """,
            "pharmacy_status_flags",
        )
        run_step(
            con,
            "classify mutually exclusive nonconversion mechanisms",
            """
            CREATE OR REPLACE TABLE nonconversion_order_diagnostics AS
            SELECT r.subject_id, r.hadm_id, r.stay_id, r.drug_class,
                   r.poe_id, r.ordertime, r.conversion_window_start,
                   r.conversion_window_end,
                   coalesce(p.explicit_cancel_discontinue, false)
                     OR coalesce(f.explicit_cancel_discontinue, false)
                     AS any_explicit_cancel_discontinue_status,
                   p.earliest_explicit_dc_time,
                   coalesce(
                     p.earliest_explicit_dc_time BETWEEN
                       r.ordertime - INTERVAL 2 HOUR
                       AND r.ordertime + INTERVAL 6 HOUR,
                     false
                   ) AS early_explicit_cancel_discontinue,
                   coalesce(p.ambiguous_closed_status, false)
                     OR coalesce(f.ambiguous_closed_status, false)
                     AS ambiguous_closed_status,
                   coalesce(p.conditional_protocol, false)
                     OR coalesce(f.conditional_protocol, false)
                     OR regexp_matches(
                       lower(coalesce(r.doses_per_24_hrs, '')),
                       'prn|as needed'
                     ) AS conditional_protocol,
                   r.relaxed_converted AS same_class_given_in_window,
                   CASE
                     WHEN coalesce(
                       p.earliest_explicit_dc_time BETWEEN
                         r.ordertime - INTERVAL 2 HOUR
                         AND r.ordertime + INTERVAL 6 HOUR,
                       false
                     ) THEN 'early_explicit_cancel_or_discontinue'
                     WHEN coalesce(p.conditional_protocol, false)
                       OR coalesce(f.conditional_protocol, false)
                       OR regexp_matches(
                         lower(coalesce(r.doses_per_24_hrs, '')),
                         'prn|as needed'
                       ) THEN 'conditional_prn_or_one_time'
                     WHEN r.relaxed_converted
                       THEN 'same_class_event_without_identity_link'
                     ELSE 'no_same_class_event_in_frozen_window'
                   END AS mechanism,
                   p.order_status_values, p.transaction_type_values,
                   p.order_type_values, p.order_subtype_values,
                   f.pharmacy_status_values, f.frequency_values,
                   f.sliding_scale_values
            FROM relaxed_order_conversion r
            LEFT JOIN poe_status_flags p
              ON r.subject_id = p.subject_id AND r.hadm_id = p.hadm_id
             AND r.poe_id = p.poe_id
            LEFT JOIN pharmacy_status_flags f
              ON r.subject_id = f.subject_id AND r.hadm_id = f.hadm_id
             AND r.poe_id = f.poe_id
            WHERE NOT r.converted
            """,
            "nonconversion_order_diagnostics",
        )
        nonconverted_n = int(
            con.execute(
                "SELECT count(*) FROM nonconversion_order_diagnostics"
            ).fetchone()[0]
        )
        if nonconverted_n != 93_281:
            raise RuntimeError(
                f"Unexpected post nonconversion denominator: {nonconverted_n}"
            )
        export_query(
            con,
            """
            SELECT drug_class, mechanism, count(*) AS order_units_n,
                   100.0 * count(*) / sum(count(*)) OVER (
                     PARTITION BY drug_class
                   ) AS within_class_pct,
                   sum(ambiguous_closed_status::INTEGER) AS ambiguous_status_n
            FROM nonconversion_order_diagnostics
            GROUP BY drug_class, mechanism
            UNION ALL
            SELECT 'all_classes', mechanism, count(*),
                   100.0 * count(*) / sum(count(*)) OVER (),
                   sum(ambiguous_closed_status::INTEGER)
            FROM nonconversion_order_diagnostics
            GROUP BY mechanism
            ORDER BY drug_class, mechanism
            """,
            TABLES / "nonconversion_mechanisms_by_class.csv",
        )
        export_query(
            con,
            """
            SELECT drug_class,
                   count(*) AS nonconverted_order_units_n,
                   sum(early_explicit_cancel_discontinue::INTEGER)
                     AS early_explicit_cancel_discontinue_n,
                   sum(any_explicit_cancel_discontinue_status::INTEGER)
                     AS any_explicit_cancel_discontinue_status_n,
                   sum(conditional_protocol::INTEGER)
                     AS conditional_protocol_n,
                   sum(same_class_given_in_window::INTEGER)
                     AS same_class_given_in_window_n,
                   sum(ambiguous_closed_status::INTEGER)
                     AS ambiguous_closed_status_n
            FROM nonconversion_order_diagnostics
            GROUP BY drug_class
            ORDER BY drug_class
            """,
            TABLES / "nonconversion_status_flags_by_class.csv",
        )

        run_step(
            con,
            "load post-implementation anchor inputs",
            f"""
            CREATE OR REPLACE TABLE a1_post AS
              SELECT * FROM read_csv_auto('{sql_path(A1_POST_CSV)}',
                header=true, sample_size=-1, strict_mode=true,
                ignore_errors=false);
            CREATE OR REPLACE TABLE a2_post AS
              SELECT * FROM read_csv_auto('{sql_path(A2_POST_CSV)}',
                header=true, sample_size=-1, strict_mode=true,
                ignore_errors=false)
            """,
        )
        run_step(
            con,
            "build broad A1 administration operator",
            """
            CREATE OR REPLACE TABLE a1_broad_admin AS
            SELECT e.stay_id, min(e.charttime) AS broad_admin_onset
            FROM base.emar_stay_events e
            JOIN a1_post a USING (stay_id)
            WHERE e.drug_class = 'vte_prophylaxis'
              AND e.ingredient IN ('heparin', 'enoxaparin')
              AND e.event_category = 'given_strict'
              AND e.charttime BETWEEN e.intime AND e.outtime
            GROUP BY e.stay_id
            """,
            "a1_broad_admin",
        )
        run_step(
            con,
            "build A2 order and strict/broad administration onsets",
            """
            CREATE OR REPLACE TABLE a2_order_onset AS
            SELECT o.stay_id,
                   min(CASE
                     WHEN coalesce(o.ordertime, o.prescription_starttime)
                          <= o.intime THEN o.intime
                     ELSE coalesce(o.ordertime, o.prescription_starttime)
                   END) AS order_onset
            FROM base.eligible_order_clusters o
            JOIN a2_post a USING (stay_id)
            WHERE o.drug_class = 'stress_ulcer_prophylaxis'
              AND o.subclass = 'PPI'
              AND o.ordertime <= o.intime + INTERVAL 48 HOUR
              AND coalesce(o.prescription_stoptime, o.outtime) >= o.intime
            GROUP BY o.stay_id;

            CREATE OR REPLACE TABLE a2_strict_admin AS
            SELECT o.stay_id,
                   min(o.first_administration_time) AS strict_admin_onset
            FROM base.order_conversion_complete o
            JOIN a2_post a USING (stay_id)
            WHERE o.drug_class = 'stress_ulcer_prophylaxis'
              AND o.subclass = 'PPI'
              AND o.ordertime <= o.intime + INTERVAL 48 HOUR
              AND coalesce(o.prescription_stoptime, o.outtime) >= o.intime
              AND o.converted
              AND o.first_administration_time <= o.intime + INTERVAL 48 HOUR
            GROUP BY o.stay_id;

            CREATE OR REPLACE TABLE a2_broad_admin AS
            SELECT e.stay_id, min(e.charttime) AS broad_admin_onset
            FROM base.emar_stay_events e
            JOIN a2_post a USING (stay_id)
            WHERE e.drug_class = 'stress_ulcer_prophylaxis'
              AND e.subclass = 'PPI'
              AND e.event_category = 'given_strict'
              AND e.charttime BETWEEN e.intime AND e.intime + INTERVAL 48 HOUR
            GROUP BY e.stay_id
            """,
        )
        run_step(
            con,
            "assemble anchor operator model inputs",
            """
            CREATE OR REPLACE TABLE a1_operator_post AS
            SELECT a.*,
                   a.administration_exposure::INTEGER AS admin_strict,
                   (b.stay_id IS NOT NULL)::INTEGER AS admin_broad
            FROM a1_post a LEFT JOIN a1_broad_admin b USING (stay_id);

            CREATE OR REPLACE TABLE a2_operator_post AS
            SELECT a.*,
                   (s.stay_id IS NOT NULL)::INTEGER AS admin_strict,
                   (b.stay_id IS NOT NULL)::INTEGER AS admin_broad,
                   CASE WHEN o.order_onset IS NULL THEN NULL ELSE
                     greatest(0.0, date_diff('second', a.intime,
                       o.order_onset) / 3600.0) END AS order_onset_hours,
                   CASE WHEN s.strict_admin_onset IS NULL THEN NULL ELSE
                     greatest(0.0, date_diff('second', a.intime,
                       s.strict_admin_onset) / 3600.0) END
                     AS strict_admin_onset_hours,
                   CASE WHEN b.broad_admin_onset IS NULL THEN NULL ELSE
                     greatest(0.0, date_diff('second', a.intime,
                       b.broad_admin_onset) / 3600.0) END
                     AS broad_admin_onset_hours,
                   CASE
                     WHEN a.stay_year_high <= 2019 THEN 'pre_2020_certain'
                     WHEN a.stay_year_low >= 2020 THEN 'year_2020_plus_certain'
                     ELSE 'crosses_2020_boundary'
                   END AS calendar_sensitivity_group
            FROM a2_post a
            LEFT JOIN a2_order_onset o USING (stay_id)
            LEFT JOIN a2_strict_admin s USING (stay_id)
            LEFT JOIN a2_broad_admin b USING (stay_id)
            """,
        )
        export_query(
            con,
            "SELECT * FROM a1_operator_post ORDER BY stay_id",
            MODEL_INPUTS / "anchor_a1_operator_post.csv",
        )
        export_query(
            con,
            "SELECT * FROM a2_operator_post ORDER BY stay_id",
            MODEL_INPUTS / "anchor_a2_operator_post.csv",
        )
        export_query(
            con,
            """
            WITH long AS (
              SELECT 'A1' AS anchor_id, 'strict_poe_identity' AS operator,
                     order_exposure, admin_strict AS administration_exposure,
                     outcome FROM a1_operator_post
              UNION ALL
              SELECT 'A1', 'broad_class_window', order_exposure, admin_broad,
                     outcome FROM a1_operator_post
              UNION ALL
              SELECT 'A2', 'strict_poe_identity', order_exposure, admin_strict,
                     outcome FROM a2_operator_post
              UNION ALL
              SELECT 'A2', 'broad_class_window', order_exposure, admin_broad,
                     outcome FROM a2_operator_post
            )
            SELECT anchor_id, operator, order_exposure,
                   administration_exposure, count(*) AS patients_n,
                   sum(outcome) AS outcomes_n,
                   100.0 * avg(outcome) AS outcome_pct
            FROM long
            GROUP BY anchor_id, operator, order_exposure,
                     administration_exposure
            ORDER BY anchor_id, operator, order_exposure,
                     administration_exposure
            """,
            TABLES / "anchor_operator_outcome_cells.csv",
        )
        operator_definitions = pd.DataFrame(
            [
                ["A1", "order", "Frozen route/dose-eligible heparin or enoxaparin order assigned to ICU stay"],
                ["A1", "strict_poe_identity", "Strict-given VTE event linked to a qualifying order by POE, class, stay, and frozen window"],
                ["A1", "broad_class_window", "Any strict-given heparin or enoxaparin event during ICU stay; no POE requirement"],
                ["A2", "order", "Frozen PPI order by 48 hours and active at or after ICU entry"],
                ["A2", "strict_poe_identity", "Strict-given PPI event by 48 hours linked to a qualifying order by POE, class, stay, and frozen window"],
                ["A2", "broad_class_window", "Any strict-given PPI event from ICU entry through 48 hours; no POE requirement"],
            ],
            columns=["anchor_id", "operator", "definition"],
        )
        operator_definitions.to_csv(
            TABLES / "anchor_exposure_operator_definitions.csv",
            index=False,
            encoding="utf-8-sig",
        )

        run_step(
            con,
            "trace broad A2 administration-only provenance",
            """
            CREATE OR REPLACE TABLE a2_first_broad_event AS
            SELECT * EXCLUDE (rn) FROM (
              SELECT e.*, row_number() OVER (
                PARTITION BY e.stay_id ORDER BY e.charttime, e.emar_id, e.emar_seq
              ) AS rn
              FROM base.emar_stay_events e JOIN a2_operator_post a USING (stay_id)
              WHERE a.order_exposure = 0 AND a.admin_broad = 1
                AND e.drug_class = 'stress_ulcer_prophylaxis'
                AND e.subclass = 'PPI'
                AND e.event_category = 'given_strict'
                AND e.charttime BETWEEN e.intime AND e.intime + INTERVAL 48 HOUR
            ) WHERE rn = 1;

            CREATE OR REPLACE TABLE a2_admin_only_provenance AS
            WITH same_poe_ppi AS (
              SELECT stay_id, poe_id, min(ordertime) AS earliest_ppi_ordertime,
                     count(*) AS ppi_order_units_n
              FROM base.eligible_order_clusters
              WHERE drug_class = 'stress_ulcer_prophylaxis' AND subclass = 'PPI'
              GROUP BY stay_id, poe_id
            ), any_stay_ppi AS (
              SELECT stay_id, count(*) AS any_stay_ppi_order_units_n
              FROM base.eligible_order_clusters
              WHERE drug_class = 'stress_ulcer_prophylaxis' AND subclass = 'PPI'
              GROUP BY stay_id
            )
            SELECT a.subject_id, a.hadm_id, a.stay_id, a.outcome,
                   e.emar_id, e.poe_id, e.charttime,
                   e.poe_id_identity_link, p.ppi_order_units_n,
                   p.earliest_ppi_ordertime, q.any_stay_ppi_order_units_n,
                   CASE
                     WHEN e.poe_id IS NULL OR trim(e.poe_id) = ''
                       THEN 'missing_poe_id'
                     WHEN NOT coalesce(e.poe_id_identity_link, false)
                       THEN 'poe_not_identity_linked'
                     WHEN p.ppi_order_units_n IS NOT NULL
                       THEN 'same_poe_ppi_order_outside_a2_operator'
                     WHEN q.any_stay_ppi_order_units_n IS NOT NULL
                       THEN 'different_poe_ppi_order_in_stay'
                     ELSE 'no_mapped_ppi_order_in_icu_stay'
                   END AS provenance_category
            FROM a2_operator_post a
            JOIN a2_first_broad_event e USING (stay_id)
            LEFT JOIN same_poe_ppi p
              ON e.stay_id = p.stay_id AND e.poe_id = p.poe_id
            LEFT JOIN any_stay_ppi q USING (stay_id)
            WHERE a.order_exposure = 0 AND a.admin_broad = 1
            """,
            "a2_admin_only_provenance",
        )
        export_query(
            con,
            """
            SELECT provenance_category, count(*) AS patients_n,
                   sum(outcome) AS deaths_90d_n,
                   100.0 * avg(outcome) AS death_90d_pct
            FROM a2_admin_only_provenance
            GROUP BY provenance_category
            ORDER BY patients_n DESC
            """,
            TABLES / "a2_broad_admin_only_provenance_summary.csv",
        )

        run_step(
            con,
            "build insulin three-state semantic audit",
            """
            CREATE OR REPLACE TABLE insulin_semantic_states AS
            SELECT CASE
                     WHEN starts_with(coalesce(e.event_txt, ''),
                          'Not Given per Sliding Scale')
                       THEN 'protocol_not_indicated_sliding_scale'
                     WHEN e.event_category = 'given_strict'
                       THEN 'strict_documented_administration'
                     WHEN e.event_category = 'not_given'
                       THEN 'other_primary_not_given'
                     WHEN e.event_txt = 'Hold Dose' THEN 'hold_dose_audit_state'
                     WHEN e.event_category = 'flushed' THEN 'flushed_excluded'
                     WHEN e.event_category = 'confirmed' THEN 'confirmed_excluded'
                     WHEN e.event_txt IS NULL OR trim(e.event_txt) = ''
                       THEN 'blank_excluded'
                     ELSE 'other_excluded'
                   END AS semantic_state,
                   count(*) AS events_n
            FROM base.emar_stay_events e JOIN stay_calendar c USING (stay_id)
            WHERE c.deployment_era = 'post_implementation'
              AND e.drug_class = 'insulin'
            GROUP BY semantic_state
            """,
            "insulin_semantic_states",
        )
        export_query(
            con,
            """
            SELECT semantic_state, events_n,
                   100.0 * events_n / sum(events_n) OVER () AS all_events_pct,
                   CASE WHEN semantic_state IN (
                     'strict_documented_administration',
                     'protocol_not_indicated_sliding_scale',
                     'other_primary_not_given'
                   ) THEN 100.0 * events_n / sum(CASE WHEN semantic_state IN (
                     'strict_documented_administration',
                     'protocol_not_indicated_sliding_scale',
                     'other_primary_not_given'
                   ) THEN events_n ELSE 0 END) OVER () END AS three_state_pct
            FROM insulin_semantic_states
            ORDER BY events_n DESC
            """,
            TABLES / "insulin_three_state_semantics.csv",
        )

        flow = build_participant_flow(con)
        flow.to_csv(
            TABLES / "participant_flow_complete.csv",
            index=False,
            encoding="utf-8-sig",
        )
        log(f"CHECKPOINT file=participant_flow_complete.csv rows={len(flow)}")

        qc = {
            "contract_checks": contract_checks,
            "post_order_units_n": post_n,
            "post_nonconverted_order_units_n": nonconverted_n,
            "relaxed_output_rows_n": int(relaxed_n),
            "relaxed_unique_units_n": int(relaxed_unique),
            "a1_operator_rows_n": int(
                con.execute("SELECT count(*) FROM a1_operator_post").fetchone()[0]
            ),
            "a2_operator_rows_n": int(
                con.execute("SELECT count(*) FROM a2_operator_post").fetchone()[0]
            ),
            "a2_broad_admin_only_n": int(
                con.execute(
                    "SELECT count(*) FROM a2_admin_only_provenance"
                ).fetchone()[0]
            ),
            "raw_sources_modified": False,
            "base_database_modified": False,
        }
        if qc["a1_operator_rows_n"] != 20_248:
            raise RuntimeError(f"A1 operator cohort mismatch: {qc}")
        if qc["a2_operator_rows_n"] != 2_813:
            raise RuntimeError(f"A2 operator cohort mismatch: {qc}")
        if qc["a2_broad_admin_only_n"] != 296:
            raise RuntimeError(f"A2 admin-only mismatch: {qc}")
        (MANIFESTS / "26_pre_submission_diagnostics_manifest.json").write_text(
            json.dumps(
                {
                    **qc,
                    "script": str(Path(__file__).resolve()),
                    "script_sha256": sha256(Path(__file__).resolve()),
                    "base_db_sha256": sha256(BASE_DB),
                    "started_epoch": START,
                    "finished_epoch": time.time(),
                    "elapsed_seconds": round(time.time() - START, 3),
                    "python": sys.version,
                    "duckdb": duckdb.__version__,
                    "pandas": pd.__version__,
                    "numpy": np.__version__,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        con.execute("CHECKPOINT")
        log(
            "PASS pre-submission diagnostic build "
            f"elapsed_seconds={time.time() - START:.3f}"
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
