from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
CACHE = PROJECT / "cache"
CONTRACTS = PROJECT / "contracts"
EXTENSION_VERSION = (
    "v1_1"
    if "--extension-version=v1_1" in sys.argv[1:]
    else "v1_0"
)
if EXTENSION_VERSION == "v1_1":
    OUTPUT = PROJECT / "outputs" / "jamia_observability_v1_1"
    CONTRACT_MANIFEST = (
        CONTRACTS / "jamia_observability_sha256_v1.1_2026-07-30.txt"
    )
    REPORT_NAME = "16_jamia_observability_v1_1_pre_model_audit.md"
    SESSION_NAME = "Python_sessionInfo_JAMIA_observability_v1_1.txt"
else:
    OUTPUT = PROJECT / "outputs" / "jamia_observability"
    CONTRACT_MANIFEST = (
        CONTRACTS / "jamia_observability_sha256_2026-07-30.txt"
    )
    REPORT_NAME = "12_jamia_observability_pre_model_audit.md"
    SESSION_NAME = "Python_sessionInfo_JAMIA_observability.txt"
TABLES = OUTPUT / "tables"
MODEL_INPUTS = OUTPUT / "model_inputs"
LOGS = OUTPUT / "logs"
MANIFESTS = OUTPUT / "manifests"
REPORTS = PROJECT / "reports"
ENVIRONMENT = PROJECT / "environment"
DB_PATH = CACHE / "n1_validity.duckdb"
EXPECTED_EMAR_ROWS = 42_808_593

for directory in (TABLES, MODEL_INPUTS, LOGS, MANIFESTS, REPORTS, ENVIRONMENT):
    directory.mkdir(parents=True, exist_ok=True)

LOG_PATH = LOGS / "13_build_jamia_observability_extension.log"
STARTED = time.time()


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


def verify_contract_manifest() -> list[dict[str, object]]:
    if not CONTRACT_MANIFEST.exists():
        raise FileNotFoundError(f"Missing contract manifest: {CONTRACT_MANIFEST}")
    checks: list[dict[str, object]] = []
    for line in CONTRACT_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split(maxsplit=1)
        path = (
            PROJECT / name
            if name == "analysis_decision_log.md"
            else CONTRACTS / name
        )
        actual = sha256(path)
        checks.append(
            {
                "file": name,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "match": actual == expected,
            }
        )
    if not checks or not all(bool(row["match"]) for row in checks):
        raise RuntimeError("JAMIA observability contract hash verification failed.")
    return checks


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return (math.nan, math.nan)
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = (
        z
        * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
        / denominator
    )
    return (100 * (center - half), 100 * (center + half))


def make_calendar(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    columns = [
        "subject_id",
        "hadm_id",
        "stay_id",
        "intime",
        "anchor_year",
        "anchor_year_group",
    ]
    calendar = con.execute(
        f"SELECT {', '.join(columns)} FROM adult_stays"
    ).fetchdf()
    calendar["intime"] = pd.to_datetime(calendar["intime"])
    group_text = calendar["anchor_year_group"].astype("string")
    calendar["anchor_group_start"] = (
        group_text.str.slice(0, 4).astype("int64")
    )
    calendar["anchor_group_end"] = (
        group_text.str.slice(-4).astype("int64")
    )
    calendar["shifted_stay_year"] = calendar["intime"].dt.year.astype("int64")
    calendar["stay_year_delta"] = (
        calendar["shifted_stay_year"] - calendar["anchor_year"].astype("int64")
    )
    calendar["stay_year_low"] = (
        calendar["anchor_group_start"] + calendar["stay_year_delta"]
    )
    calendar["stay_year_high"] = (
        calendar["anchor_group_end"] + calendar["stay_year_delta"]
    )
    calendar["stay_year_midpoint"] = (
        calendar["anchor_group_start"] + 1 + calendar["stay_year_delta"]
    )
    calendar["corrected_anchor_era"] = np.select(
        [
            calendar["stay_year_midpoint"] <= 2013,
            calendar["stay_year_midpoint"].between(2014, 2019),
        ],
        ["2008-2013", "2014-2019"],
        default="2020-2022",
    )
    if EXTENSION_VERSION == "v1_1":
        calendar["deployment_era"] = np.select(
            [
                calendar["stay_year_high"] <= 2013,
                calendar["stay_year_low"] >= 2017,
            ],
            ["pre_implementation", "post_implementation"],
            default="implementation_overlap",
        )
    else:
        calendar["deployment_era"] = np.select(
            [
                calendar["stay_year_high"] <= 2010,
                calendar["stay_year_low"] >= 2014,
            ],
            ["pre_implementation", "post_implementation"],
            default="implementation_overlap",
        )

    emar_admissions = con.execute(
        """
        SELECT DISTINCT subject_id, hadm_id
        FROM s02v2_raw_emar_keys
        """
    ).fetchdf()
    emar_admissions["any_emar_in_admission"] = True
    calendar = calendar.merge(
        emar_admissions,
        on=["subject_id", "hadm_id"],
        how="left",
        validate="many_to_one",
    )
    calendar["any_emar_in_admission"] = (
        calendar["any_emar_in_admission"].fillna(False).astype(bool)
    )
    return calendar


def coverage_summary(calendar: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for era, data in calendar.groupby("deployment_era", observed=True):
        admission = data[
            ["subject_id", "hadm_id", "any_emar_in_admission"]
        ].drop_duplicates()
        rows.append(
            {
                "deployment_era": era,
                "adult_stays_n": len(data),
                "adult_stays_with_any_emar_n": int(
                    data["any_emar_in_admission"].sum()
                ),
                "adult_stays_with_any_emar_pct": float(
                    100 * data["any_emar_in_admission"].mean()
                ),
                "adult_admissions_n": len(admission),
                "adult_admissions_with_any_emar_n": int(
                    admission["any_emar_in_admission"].sum()
                ),
                "adult_admissions_with_any_emar_pct": float(
                    100 * admission["any_emar_in_admission"].mean()
                ),
            }
        )
    order = {
        "pre_implementation": 0,
        "implementation_overlap": 1,
        "post_implementation": 2,
    }
    result = pd.DataFrame(rows)
    result["_order"] = result["deployment_era"].map(order)
    return result.sort_values("_order").drop(columns="_order")


def analysis_scopes(data: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    return [
        ("all_periods", data),
        (
            "pre_implementation",
            data.loc[data["deployment_era"] == "pre_implementation"],
        ),
        (
            "implementation_overlap",
            data.loc[data["deployment_era"] == "implementation_overlap"],
        ),
        (
            "post_implementation",
            data.loc[data["deployment_era"] == "post_implementation"],
        ),
        (
            "post_implementation_any_emar_sensitivity",
            data.loc[
                (data["deployment_era"] == "post_implementation")
                & data["any_emar_in_admission"]
            ],
        ),
    ]


def conversion_summary(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scope, scoped in analysis_scopes(data):
        for drug_class, group in scoped.groupby("drug_class", observed=True):
            eligible = len(group)
            converted = int(group["converted"].sum())
            low, high = wilson_interval(converted, eligible)
            rows.append(
                {
                    "analysis_scope": scope,
                    "drug_class": drug_class,
                    "eligible_orders_n": eligible,
                    "converted_orders_n": converted,
                    "not_converted_orders_n": eligible - converted,
                    "conversion_pct": 100 * converted / eligible
                    if eligible
                    else math.nan,
                    "conversion_ci_low_pct": low,
                    "conversion_ci_high_pct": high,
                }
            )
    return pd.DataFrame(rows)


def lag_summary(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scope, scoped in analysis_scopes(data):
        for drug_class, group in scoped.groupby("drug_class", observed=True):
            converted = group.loc[group["converted"]].copy()
            lag = converted["first_dose_lag_hours"]
            inference = lag.loc[(lag >= 0) & (lag <= 24 * 7)].dropna()
            rows.append(
                {
                    "analysis_scope": scope,
                    "drug_class": drug_class,
                    "converted_orders_n": len(converted),
                    "negative_lag_n": int((lag < 0).sum()),
                    "lag_over_7d_n": int((lag > 24 * 7).sum()),
                    "inferential_lag_n": len(inference),
                    "median_hours": inference.quantile(0.50)
                    if len(inference)
                    else math.nan,
                    "p10_hours": inference.quantile(0.10)
                    if len(inference)
                    else math.nan,
                    "p25_hours": inference.quantile(0.25)
                    if len(inference)
                    else math.nan,
                    "p75_hours": inference.quantile(0.75)
                    if len(inference)
                    else math.nan,
                    "p90_hours": inference.quantile(0.90)
                    if len(inference)
                    else math.nan,
                    "p95_hours": inference.quantile(0.95)
                    if len(inference)
                    else math.nan,
                    "over_24h_n": int((inference > 24).sum()),
                    "over_24h_pct": 100 * float((inference > 24).mean())
                    if len(inference)
                    else math.nan,
                }
            )
    return pd.DataFrame(rows)


def add_calendar_to_csv(
    source: Path,
    calendar: pd.DataFrame,
    destination_all: Path,
    destination_post: Path,
    *,
    identity_columns: list[str],
) -> pd.DataFrame:
    data = pd.read_csv(source, low_memory=False)
    original_rows = len(data)
    calendar_columns = [
        "subject_id",
        "hadm_id",
        "stay_id",
        "stay_year_low",
        "stay_year_high",
        "stay_year_midpoint",
        "corrected_anchor_era",
        "deployment_era",
        "any_emar_in_admission",
    ]
    if identity_columns == ["stay_id"]:
        calendar_join = calendar[
            [
                "stay_id",
                "stay_year_low",
                "stay_year_high",
                "stay_year_midpoint",
                "corrected_anchor_era",
                "deployment_era",
                "any_emar_in_admission",
            ]
        ]
    else:
        calendar_join = calendar[calendar_columns]
    data = data.merge(
        calendar_join,
        on=identity_columns,
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if len(data) != original_rows or not (data["_merge"] == "both").all():
        raise RuntimeError(f"Calendar merge failed for {source.name}")
    data = data.drop(columns="_merge")
    if "anchor_era" in data:
        data = data.rename(columns={"anchor_era": "original_anchor_era"})
    data["anchor_era"] = data["corrected_anchor_era"]
    data.to_csv(destination_all, index=False)
    data.loc[data["deployment_era"] == "post_implementation"].to_csv(
        destination_post, index=False
    )
    return data


def not_given_summary(
    primary: pd.DataFrame, sensitivity: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for mapping, data in (
        ("frozen_primary", primary),
        ("audit_semantic_sensitivity", sensitivity),
    ):
        for scope, scoped in analysis_scopes(data):
            for drug_class, group in scoped.groupby(
                "drug_class", observed=True
            ):
                not_given_n = float(group["not_given_n"].sum())
                given_n = float(group["given_n"].sum())
                denominator = not_given_n + given_n
                rows.append(
                    {
                        "event_mapping": mapping,
                        "analysis_scope": scope,
                        "drug_class": drug_class,
                        "not_given_n": int(not_given_n),
                        "given_n": int(given_n),
                        "decision_events_n": int(denominator),
                        "not_given_pct": 100 * not_given_n / denominator
                        if denominator
                        else math.nan,
                    }
                )
    return pd.DataFrame(rows)


def crossclassification(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scope, scoped in analysis_scopes(data):
        for anchor_id, group in scoped.groupby("anchor_id", observed=True):
            order = group["order_exposure"].astype(int)
            administration = group["administration_exposure"].astype(int)
            both = int(((order == 1) & (administration == 1)).sum())
            order_only = int(((order == 1) & (administration == 0)).sum())
            administration_only = int(
                ((order == 0) & (administration == 1)).sum()
            )
            neither = int(((order == 0) & (administration == 0)).sum())
            n = len(group)
            observed_agreement = (both + neither) / n if n else math.nan
            order_p = float(order.mean()) if n else math.nan
            admin_p = float(administration.mean()) if n else math.nan
            expected = (
                order_p * admin_p + (1 - order_p) * (1 - admin_p)
                if n
                else math.nan
            )
            kappa = (
                (observed_agreement - expected) / (1 - expected)
                if n and expected < 1
                else math.nan
            )
            union = both + order_only + administration_only
            rows.append(
                {
                    "analysis_scope": scope,
                    "anchor_id": anchor_id,
                    "cohort_n": n,
                    "outcomes_n": int(group["outcome"].sum()),
                    "order_positive_n": int(order.sum()),
                    "administration_positive_n": int(administration.sum()),
                    "both_positive_n": both,
                    "order_only_n": order_only,
                    "administration_only_n": administration_only,
                    "neither_positive_n": neither,
                    "discordant_n": order_only + administration_only,
                    "discordant_pct": 100 * (order_only + administration_only) / n
                    if n
                    else math.nan,
                    "order_only_among_order_positive_pct": (
                        100 * order_only / int(order.sum())
                        if int(order.sum())
                        else math.nan
                    ),
                    "observed_agreement": observed_agreement,
                    "cohen_kappa": kappa,
                    "jaccard_agreement": both / union if union else math.nan,
                }
            )
    return pd.DataFrame(rows)


def write_manifest(paths: list[Path], metadata: dict[str, object]) -> None:
    file_rows = []
    for path in paths:
        row_count: int | None = None
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
                row_count = max(sum(1 for _ in handle) - 1, 0)
        file_rows.append(
            {
                "path": str(path.relative_to(PROJECT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "data_rows": row_count,
            }
        )
    pd.DataFrame(file_rows).to_csv(
        MANIFESTS / "13_jamia_observability_files.csv", index=False
    )
    (MANIFESTS / "13_jamia_observability_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    log("START contract verification")
    contract_checks = verify_contract_manifest()
    pd.DataFrame(contract_checks).to_csv(
        MANIFESTS / "contract_verification.csv", index=False
    )
    log("PASS contract verification")

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        table_names = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        required_tables = {
            "adult_stays",
            "s02v2_raw_emar_keys",
            "order_conversion_complete",
        }
        missing = required_tables - table_names
        if missing:
            raise RuntimeError(f"Missing required DuckDB tables: {sorted(missing)}")
        emar_rows = int(
            con.execute("SELECT count(*) FROM s02v2_raw_emar_keys").fetchone()[0]
        )
        if emar_rows != EXPECTED_EMAR_ROWS:
            raise RuntimeError(
                f"eMAR row reconciliation failed: {emar_rows} != "
                f"{EXPECTED_EMAR_ROWS}"
            )

        log("START stay-level calendar alignment")
        calendar = make_calendar(con)
        if calendar["stay_id"].duplicated().any():
            raise RuntimeError("Calendar contains duplicate stay_id values.")
        if calendar[
            [
                "stay_year_low",
                "stay_year_high",
                "stay_year_midpoint",
                "corrected_anchor_era",
                "deployment_era",
            ]
        ].isna().any().any():
            raise RuntimeError("Calendar alignment contains missing values.")
        if not (
            (calendar["stay_year_low"] <= calendar["stay_year_midpoint"])
            & (calendar["stay_year_midpoint"] <= calendar["stay_year_high"])
        ).all():
            raise RuntimeError("Calendar interval ordering failed.")
        calendar_path = TABLES / "stay_calendar_alignment_audit.csv"
        calendar.to_csv(calendar_path, index=False)
        coverage = coverage_summary(calendar)
        coverage_path = TABLES / "emar_observability_by_deployment_era.csv"
        coverage.to_csv(coverage_path, index=False)
        log(f"DONE calendar alignment stays={len(calendar)}")

        log("START order conversion and lag by observability scope")
        order = con.execute(
            """
            SELECT
              subject_id, hadm_id, stay_id, drug_class, poe_id,
              CAST(converted AS BOOLEAN) AS converted,
              first_dose_lag_hours
            FROM order_conversion_complete
            """
        ).fetchdf()
        order = order.merge(
            calendar[
                [
                    "subject_id",
                    "hadm_id",
                    "stay_id",
                    "corrected_anchor_era",
                    "deployment_era",
                    "any_emar_in_admission",
                ]
            ],
            on=["subject_id", "hadm_id", "stay_id"],
            how="left",
            validate="many_to_one",
        )
        if order["deployment_era"].isna().any():
            raise RuntimeError("Order conversion calendar merge is incomplete.")
        conversion = conversion_summary(order)
        conversion_path = TABLES / "order_conversion_by_observability_scope.csv"
        conversion.to_csv(conversion_path, index=False)
        lag = lag_summary(order)
        lag_path = TABLES / "first_dose_lag_by_observability_scope.csv"
        lag.to_csv(lag_path, index=False)
        log(f"DONE conversion units={len(order)}")
    finally:
        con.close()

    log("START corrected not-given model inputs")
    primary_not_given = add_calendar_to_csv(
        CACHE / "not_given_model_aggregated.csv",
        calendar,
        MODEL_INPUTS / "not_given_primary_corrected_all.csv",
        MODEL_INPUTS / "not_given_primary_corrected_post.csv",
        identity_columns=["stay_id"],
    )
    sensitivity_not_given = add_calendar_to_csv(
        CACHE / "not_given_audit_semantic_sensitivity_aggregated.csv",
        calendar,
        MODEL_INPUTS / "not_given_semantic_corrected_all.csv",
        MODEL_INPUTS / "not_given_semantic_corrected_post.csv",
        identity_columns=["stay_id"],
    )
    not_given = not_given_summary(primary_not_given, sensitivity_not_given)
    not_given_path = TABLES / "not_given_by_observability_scope.csv"
    not_given.to_csv(not_given_path, index=False)
    log("DONE corrected not-given inputs")

    log("START corrected anchor model inputs and cross-classification")
    a1 = add_calendar_to_csv(
        CACHE / "anchor_a1_cohort.csv",
        calendar,
        MODEL_INPUTS / "anchor_a1_corrected_all.csv",
        MODEL_INPUTS / "anchor_a1_corrected_post.csv",
        identity_columns=["subject_id", "hadm_id", "stay_id"],
    )
    a2 = add_calendar_to_csv(
        CACHE / "anchor_a2_cohort.csv",
        calendar,
        MODEL_INPUTS / "anchor_a2_corrected_all.csv",
        MODEL_INPUTS / "anchor_a2_corrected_post.csv",
        identity_columns=["subject_id", "hadm_id", "stay_id"],
    )
    anchors = pd.concat([a1, a2], ignore_index=True, sort=False)
    anchor_cross = crossclassification(anchors)
    anchor_cross_path = TABLES / "anchor_reclassification_by_scope.csv"
    anchor_cross.to_csv(anchor_cross_path, index=False)
    log("DONE corrected anchor inputs")

    expected_classes = {
        "stress_ulcer_prophylaxis",
        "vte_prophylaxis",
        "intra_abdominal_antibiotics",
        "electrolyte_replacement",
        "prokinetic",
        "insulin",
    }
    post_conversion = conversion.loc[
        conversion["analysis_scope"] == "post_implementation"
    ]
    post_cross = anchor_cross.loc[
        anchor_cross["analysis_scope"] == "post_implementation"
    ]
    gates = [
        {
            "gate_id": "J01",
            "status": "PASS",
            "evidence": (
                f"{len(calendar)} unique adult stays; interval ordering and "
                "missingness checks passed"
            ),
        },
        {
            "gate_id": "J02",
            "status": "PASS",
            "evidence": (
                f"{emar_rows} full eMAR keys reconcile; coverage denominators "
                f"sum to {int(coverage['adult_stays_n'].sum())} stays"
            ),
        },
        {
            "gate_id": "J03",
            "status": "PASS"
            if set(post_conversion["drug_class"]) == expected_classes
            else "FAIL",
            "evidence": (
                f"{post_conversion['drug_class'].nunique()} post-implementation "
                "classes retained"
            ),
        },
        {
            "gate_id": "J04",
            "status": "PENDING_MODEL",
            "evidence": "Corrected all-period and post-implementation inputs written",
        },
        {
            "gate_id": "J05",
            "status": "PASS"
            if (
                len(post_cross) == 2
                and (post_cross["cohort_n"] >= 500).all()
                and (post_cross["order_positive_n"] > 0).all()
                and (post_cross["administration_positive_n"] > 0).all()
            )
            else "FAIL",
            "evidence": " | ".join(
                f"{row.anchor_id}: n={row.cohort_n}, "
                f"order={row.order_positive_n}, "
                f"admin={row.administration_positive_n}"
                for row in post_cross.itertuples(index=False)
            ),
        },
        {
            "gate_id": "J06",
            "status": "PENDING_MODEL",
            "evidence": "Paired-model same-cohort verification awaits R fits",
        },
        {
            "gate_id": "J07",
            "status": "PENDING_MODEL",
            "evidence": "Post-implementation material effect change not inspected",
        },
        {
            "gate_id": "J08",
            "status": "PASS",
            "evidence": (
                "Outcome-model inputs select deployment_era only; "
                "any_emar_in_admission retained as descriptive column"
            ),
        },
        {
            "gate_id": "J09",
            "status": "PENDING_TEXT_QA",
            "evidence": "Claim-boundary scan follows results and manuscript revision",
        },
        {
            "gate_id": "J10",
            "status": "PENDING_FINAL_VALIDATION",
            "evidence": "Pre-model reproducibility assets are present",
        },
    ]
    gates_path = TABLES / "pilot_gates_pre_model.csv"
    pd.DataFrame(gates).to_csv(gates_path, index=False)
    if any(row["status"] == "FAIL" for row in gates):
        raise RuntimeError("One or more pre-model JAMIA gates failed.")

    post_class = post_conversion[
        [
            "drug_class",
            "eligible_orders_n",
            "converted_orders_n",
            "conversion_pct",
        ]
    ].sort_values("conversion_pct")
    report_lines = [
        (
            "# 16 — JAMIA observability v1.1 pre-model audit"
            if EXTENSION_VERSION == "v1_1"
            else "# 12 — JAMIA observability pre-model audit"
        ),
        "",
        "The original frozen analyses remain preserved. This report implements the",
        "versioned stay-level calendar repair and observability extension before",
        "any corrected-era or post-implementation outcome model.",
        *(
            [
                "",
                "Version 1.1 uses the source-corrected MIMIC-IV eMAR deployment",
                "interval (2014–2016): pre-implementation intervals end by 2013,",
                "implementation-overlap intervals intersect 2014–2016, and",
                "post-implementation intervals begin in 2017 or later.",
            ]
            if EXTENSION_VERSION == "v1_1"
            else []
        ),
        "",
        "## Calendar and eMAR observability",
        "",
        "```text",
        coverage.to_string(index=False),
        "```",
        "",
        "## Post-implementation class conversion",
        "",
        "```text",
        post_class.to_string(index=False),
        "```",
        "",
        "## Post-implementation anchor reclassification",
        "",
        "```text",
        post_cross.to_string(index=False),
        "```",
        "",
        "## Model boundary",
        "",
        "`any_emar_in_admission` is descriptive only and does not select either",
        "outcome-model cohort. Corrected all-period and post-implementation model",
        "inputs were written only after the contract hash passed.",
        "",
        "## Pre-model gates",
        "",
        "```text",
        pd.DataFrame(gates).to_string(index=False),
        "```",
        "",
    ]
    report_path = REPORTS / REPORT_NAME
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    session_path = ENVIRONMENT / SESSION_NAME
    session_path.write_text(
        "\n".join(
            [
                f"Python: {sys.version}",
                f"Executable: {sys.executable}",
                f"Platform: {platform.platform()}",
                f"duckdb: {duckdb.__version__}",
                f"pandas: {pd.__version__}",
                f"numpy: {np.__version__}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_paths = [
        calendar_path,
        coverage_path,
        conversion_path,
        lag_path,
        not_given_path,
        anchor_cross_path,
        gates_path,
        MODEL_INPUTS / "not_given_primary_corrected_all.csv",
        MODEL_INPUTS / "not_given_primary_corrected_post.csv",
        MODEL_INPUTS / "not_given_semantic_corrected_all.csv",
        MODEL_INPUTS / "not_given_semantic_corrected_post.csv",
        MODEL_INPUTS / "anchor_a1_corrected_all.csv",
        MODEL_INPUTS / "anchor_a1_corrected_post.csv",
        MODEL_INPUTS / "anchor_a2_corrected_all.csv",
        MODEL_INPUTS / "anchor_a2_corrected_post.csv",
        report_path,
        session_path,
        MANIFESTS / "contract_verification.csv",
    ]
    metadata = {
        "started_at": datetime.fromtimestamp(STARTED).astimezone().isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
        "elapsed_seconds": time.time() - STARTED,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "extension_version": EXTENSION_VERSION,
        "deployment_interval": (
            "2014-2016_source_corrected"
            if EXTENSION_VERSION == "v1_1"
            else "2011-2013_v1_0_superseded"
        ),
        "database": str(DB_PATH),
        "database_read_only": True,
        "contract_manifest": str(CONTRACT_MANIFEST),
        "contract_verified": True,
        "full_emar_rows": emar_rows,
        "adult_stays_n": len(calendar),
        "eligible_order_units_n": len(order),
        "post_implementation_anchor_models_run": False,
        "any_emar_used_for_outcome_cohort_selection": False,
    }
    write_manifest(output_paths, metadata)
    log(
        "DONE pre-model observability extension "
        f"elapsed_seconds={metadata['elapsed_seconds']:.3f}"
    )


if __name__ == "__main__":
    main()
