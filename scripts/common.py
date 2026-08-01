from __future__ import annotations

import hashlib
import os
import json
import platform
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT / "config"
CONTRACTS = PROJECT / "contracts"
CACHE = PROJECT / "cache"
OUTPUTS = PROJECT / "outputs"
TABLES = OUTPUTS / "tables"
FIGURES = OUTPUTS / "figures"
MANIFESTS = OUTPUTS / "manifests"
LOGS = OUTPUTS / "logs"
REPORTS = PROJECT / "reports"
ENVIRONMENT = PROJECT / "environment"
DUCKDB_TMP = CACHE / "duckdb_tmp"

MIMIC_ROOT = Path(os.environ["MIMIC_IV_ROOT"])
EICU_ZIP = Path(os.environ["EICU_ZIP"])
ND03_MIMIC_WHITELIST = CONFIG / "mimic_interface_whitelist.csv"
ND03_EICU_WHITELIST = CONFIG / "eicu_interface_whitelist.csv"
DB_PATH = CACHE / "n1_validity.duckdb"


def ensure_dirs() -> None:
    for path in (
        CONFIG,
        CONTRACTS,
        CACHE,
        TABLES,
        FIGURES,
        MANIFESTS,
        LOGS,
        REPORTS,
        ENVIRONMENT,
        DUCKDB_TMP,
    ):
        path.mkdir(parents=True, exist_ok=True)


def now_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RunLogger:
    def __init__(self, stem: str):
        ensure_dirs()
        self.path = LOGS / f"{stem}.log"

    def __call__(self, message: str) -> None:
        line = f"{now_local()}\t{message}"
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def file_sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def sql_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def csv_scan(path: Path, *, all_varchar: bool = True) -> str:
    options = [
        "header=true",
        f"all_varchar={'true' if all_varchar else 'false'}",
        "sample_size=-1",
        "ignore_errors=false",
        "strict_mode=true",
        "null_padding=false",
    ]
    return f"read_csv_auto('{sql_path(path)}', {', '.join(options)})"


def connect_duckdb():
    import duckdb

    ensure_dirs()
    con = duckdb.connect(str(DB_PATH))
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{sql_path(DUCKDB_TMP)}'")
    return con


def write_csv(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_json(value: object, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def script_metadata(started: float, script: Path) -> dict[str, object]:
    metadata: dict[str, object] = {
        "started_epoch": started,
        "finished_epoch": time.time(),
        "elapsed_seconds": round(time.time() - started, 3),
        "finished_at": now_local(),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "pandas_version": pd.__version__,
        "script": str(script),
        "script_sha256": file_sha256(script),
        "mimic_root": str(MIMIC_ROOT),
        "eicu_zip": str(EICU_ZIP),
        "raw_sources_modified": False,
    }
    try:
        import duckdb

        metadata["duckdb_version"] = duckdb.__version__
    except Exception as exc:  # pragma: no cover
        metadata["duckdb_version"] = None
        metadata["duckdb_import_error"] = repr(exc)
    return metadata


def verify_frozen_contract() -> pd.DataFrame:
    manifest = CONTRACTS / "frozen_contract_sha256_2026-07-29.txt"
    records: list[dict[str, object]] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = re.split(r"\s{2,}", line.strip(), maxsplit=1)
        path = PROJECT / Path(relative)
        observed = file_sha256(path)
        records.append(
            {
                "relative_path": relative,
                "expected_sha256": expected.lower(),
                "observed_sha256": observed.lower(),
                "match": expected.lower() == observed.lower(),
            }
        )
    result = pd.DataFrame(records)
    if result.empty or not result["match"].all():
        raise RuntimeError(
            "Frozen contract verification failed:\n"
            + result.to_string(index=False)
        )
    return result


def verify_semantic_addendum() -> pd.DataFrame:
    manifest = (
        CONTRACTS / "semantic_audit_addendum_sha256_2026-07-29.txt"
    )
    records: list[dict[str, object]] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = re.split(r"\s{2,}", line.strip(), maxsplit=1)
        path = PROJECT / Path(relative)
        observed = file_sha256(path)
        records.append(
            {
                "relative_path": relative,
                "expected_sha256": expected.lower(),
                "observed_sha256": observed.lower(),
                "match": expected.lower() == observed.lower(),
            }
        )
    result = pd.DataFrame(records)
    if len(result) != 2 or not result["match"].all():
        raise RuntimeError(
            "Semantic-audit addendum verification failed:\n"
            + result.to_string(index=False)
        )
    return result


def load_whitelist(tier: str = "strict") -> pd.DataFrame:
    frame = pd.read_csv(
        CONFIG / "drug_class_whitelist_v1.0.csv",
        dtype=str,
        keep_default_na=False,
    )
    return frame.loc[frame["tier"].eq(tier)].copy()


def regex_sql_condition(
    text_sql: str,
    rows: pd.DataFrame,
) -> str:
    terms: list[str] = []
    for row in rows.itertuples(index=False):
        positive = f"regexp_matches({text_sql}, {sql_quote(row.name_regex)})"
        if row.negative_regex:
            positive += (
                f" AND NOT regexp_matches({text_sql}, "
                f"{sql_quote(row.negative_regex)})"
            )
        terms.append(f"({positive})")
    return "(" + " OR ".join(terms) + ")" if terms else "FALSE"


def class_case_sql(
    text_sql: str,
    whitelist: pd.DataFrame,
    output_column: str,
) -> str:
    pieces = ["CASE"]
    for drug_class, rows in whitelist.groupby("drug_class", sort=False):
        condition = regex_sql_condition(text_sql, rows)
        pieces.append(f"WHEN {condition} THEN {sql_quote(drug_class)}")
    pieces.append(f"END AS {output_column}")
    return "\n".join(pieces)


def ingredient_case_sql(
    text_sql: str,
    whitelist: pd.DataFrame,
    output_column: str,
) -> str:
    pieces = ["CASE"]
    for row in whitelist.itertuples(index=False):
        condition = regex_sql_condition(
            text_sql,
            whitelist.loc[whitelist["ingredient"].eq(row.ingredient)].head(1),
        )
        pieces.append(
            f"WHEN {condition} THEN {sql_quote(row.ingredient)}"
        )
    pieces.append(f"END AS {output_column}")
    return "\n".join(pieces)


def subclass_case_sql(
    text_sql: str,
    whitelist: pd.DataFrame,
    output_column: str,
) -> str:
    pieces = ["CASE"]
    keys = whitelist[["subclass"]].drop_duplicates()["subclass"].tolist()
    for subclass in keys:
        rows = whitelist.loc[whitelist["subclass"].eq(subclass)]
        pieces.append(
            f"WHEN {regex_sql_condition(text_sql, rows)} "
            f"THEN {sql_quote(subclass)}"
        )
    pieces.append(f"END AS {output_column}")
    return "\n".join(pieces)


def source_stat(paths: Iterable[Path]) -> pd.DataFrame:
    records = []
    for path in paths:
        stat = path.stat()
        records.append(
            {
                "path": str(path),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return pd.DataFrame(records)
