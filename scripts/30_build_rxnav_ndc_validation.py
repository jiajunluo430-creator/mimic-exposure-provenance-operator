from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "outputs" / "jamia_prereview_upgrade_v1_0"
TABLES = OUTPUT / "tables"
LOGS = OUTPUT / "logs"
MANIFESTS = OUTPUT / "manifests"
RAW = OUTPUT / "rxnav_raw"
ENVIRONMENT = PROJECT / "environment"
INPUT = TABLES / "prescription_ndc_code_counts_for_rxnav.csv"
WHITELIST = PROJECT / "config" / "drug_class_whitelist_v1.0.csv"
CONTRACT = (
    PROJECT
    / "contracts"
    / "jamia_prereview_upgrade_addendum_v1.0_2026-07-31.md"
)
EXPECTED_CONTRACT_SHA256 = (
    "0a851a99c9176c16deda2cde9e30fded7f2b5131a5a3f64ac7f050ebd8f81d9d"
)
BASE_ENDPOINT = "https://rxnav.nlm.nih.gov/REST/ndcstatus.json"
VERSION_ENDPOINT = "https://rxnav.nlm.nih.gov/REST/version.json"
USER_AGENT = "N1-MIMIC-medication-provenance-audit/1.0"
QUERY_DATE = "2026-07-31"
TARGET_ROW_COVERAGE = 0.95
MAX_UNIQUE_CODES = 2000
MIN_SECONDS_BETWEEN_CALLS = 0.34
STARTED = time.time()


for directory in (TABLES, LOGS, MANIFESTS, RAW, ENVIRONMENT):
    directory.mkdir(parents=True, exist_ok=True)

LOG_PATH = LOGS / "30_build_rxnav_ndc_validation.log"


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


def get_json(url: str, attempts: int = 5) -> tuple[int, dict[str, object]]:
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = int(response.status)
                payload = json.loads(response.read().decode("utf-8"))
                return status, payload
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt < attempts:
                time.sleep(min(60, 2**attempt))
                continue
            return int(error.code), {"error": str(error)}
        except Exception as error:  # network errors remain auditable
            if attempt < attempts:
                time.sleep(min(30, 2**attempt))
                continue
            return 0, {"error": repr(error)}
    raise AssertionError("unreachable")


def compile_dictionary() -> list[dict[str, object]]:
    whitelist = pd.read_csv(WHITELIST, dtype=str).fillna("")
    rules: list[dict[str, object]] = []
    for row in whitelist.itertuples(index=False):
        rules.append(
            {
                "drug_class": row.drug_class,
                "ingredient": row.ingredient,
                "name": re.compile(row.name_regex, flags=re.IGNORECASE),
                "negative": re.compile(row.negative_regex, flags=re.IGNORECASE)
                if row.negative_regex
                else None,
            }
        )
    return rules


def map_concept_name(
    concept_name: str, rules: list[dict[str, object]]
) -> tuple[str, str]:
    ingredients: set[str] = set()
    classes: set[str] = set()
    for rule in rules:
        negative = rule["negative"]
        if negative is not None and negative.search(concept_name):
            continue
        if rule["name"].search(concept_name):
            ingredients.add(str(rule["ingredient"]))
            classes.add(str(rule["drug_class"]))
    return "|".join(sorted(ingredients)), "|".join(sorted(classes))


def main() -> None:
    observed_contract_hash = sha256(CONTRACT)
    if observed_contract_hash != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError("Prereview-upgrade contract hash mismatch")
    if not INPUT.exists():
        raise FileNotFoundError(INPUT)
    rules = compile_dictionary()
    codes = pd.read_csv(INPUT, dtype={"normalized_ndc": str})
    codes["normalized_ndc"] = codes["normalized_ndc"].str.zfill(11)
    codes = codes.sort_values(
        ["prescription_rows_n", "normalized_ndc"],
        ascending=[False, True],
    ).reset_index(drop=True)
    total_rows = float(codes["prescription_rows_n"].sum())
    codes["cumulative_rows_n"] = codes["prescription_rows_n"].cumsum()
    codes["cumulative_row_coverage"] = codes["cumulative_rows_n"] / total_rows
    crossing = codes.index[codes["cumulative_row_coverage"] >= TARGET_ROW_COVERAGE]
    selected_n = (int(crossing[0]) + 1) if len(crossing) else len(codes)
    selected_n = min(selected_n, MAX_UNIQUE_CODES, len(codes))
    selected = codes.iloc[:selected_n].copy()
    log(
        f"SELECT codes={selected_n} total_unique={len(codes)} "
        f"row_coverage={selected['prescription_rows_n'].sum() / total_rows:.6f}"
    )

    version_status, version_payload = get_json(VERSION_ENDPOINT)
    (RAW / "rxnav_version.json").write_text(
        json.dumps(
            {
                "query_date": QUERY_DATE,
                "endpoint": VERSION_ENDPOINT,
                "http_status": version_status,
                "response": version_payload,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    records: list[dict[str, object]] = []
    raw_jsonl = RAW / "ndcstatus_responses.jsonl"
    with raw_jsonl.open("w", encoding="utf-8") as raw_handle:
        last_call = 0.0
        for index, row in enumerate(selected.itertuples(index=False), start=1):
            wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - last_call)
            if wait > 0:
                time.sleep(wait)
            endpoint = BASE_ENDPOINT + "?" + urllib.parse.urlencode(
                {"ndc": row.normalized_ndc}
            )
            status_code, payload = get_json(endpoint)
            last_call = time.monotonic()
            raw_handle.write(
                json.dumps(
                    {
                        "query_date": QUERY_DATE,
                        "endpoint": endpoint,
                        "http_status": status_code,
                        "response": payload,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            ndc_status = payload.get("ndcStatus", {})
            if not isinstance(ndc_status, dict):
                ndc_status = {}
            concept_name = str(ndc_status.get("conceptName", "") or "")
            inferred_ingredients, inferred_classes = map_concept_name(
                concept_name, rules
            )
            expected_ingredients = set(str(row.expected_ingredients).split("|"))
            expected_classes = set(str(row.expected_classes).split("|"))
            inferred_ingredient_set = set(inferred_ingredients.split("|")) - {""}
            inferred_class_set = set(inferred_classes.split("|")) - {""}
            mapped = bool(ndc_status.get("rxcui")) and bool(concept_name)
            records.append(
                {
                    "normalized_ndc": row.normalized_ndc,
                    "prescription_rows_n": row.prescription_rows_n,
                    "expected_ingredients": row.expected_ingredients,
                    "expected_classes": row.expected_classes,
                    "query_date": QUERY_DATE,
                    "endpoint": endpoint,
                    "http_status": status_code,
                    "rxnav_status": ndc_status.get("status"),
                    "rxnav_active": ndc_status.get("active"),
                    "rxnorm_ndc": ndc_status.get("rxnormNdc"),
                    "rxcui": ndc_status.get("rxcui"),
                    "concept_name": concept_name,
                    "concept_status": ndc_status.get("conceptStatus"),
                    "inferred_ingredients_from_concept_name": inferred_ingredients,
                    "inferred_classes_from_concept_name": inferred_classes,
                    "api_mapped": mapped,
                    "ingredient_agreement": mapped
                    and bool(expected_ingredients & inferred_ingredient_set),
                    "class_agreement": mapped
                    and bool(expected_classes & inferred_class_set),
                }
            )
            if index % 25 == 0 or index == selected_n:
                log(f"CHECKPOINT queried={index}/{selected_n}")

    result = pd.DataFrame(records)
    result.to_csv(
        TABLES / "rxnav_ndc_validation_code_level.csv",
        index=False,
        encoding="utf-8-sig",
    )
    expanded = result.assign(
        expected_class=result["expected_classes"].str.split("|")
    ).explode("expected_class")
    by_class = (
        expanded.groupby("expected_class", dropna=False)
        .apply(
            lambda frame: pd.Series(
                {
                    "queried_codes_n": frame["normalized_ndc"].nunique(),
                    "represented_prescription_rows_n": frame[
                        "prescription_rows_n"
                    ].sum(),
                    "api_mapped_rows_n": frame.loc[
                        frame["api_mapped"], "prescription_rows_n"
                    ].sum(),
                    "api_mapped_rows_pct": 100
                    * frame.loc[frame["api_mapped"], "prescription_rows_n"].sum()
                    / frame["prescription_rows_n"].sum(),
                    "class_agreement_rows_n": frame.loc[
                        frame["class_agreement"], "prescription_rows_n"
                    ].sum(),
                    "class_agreement_among_mapped_rows_pct": 100
                    * frame.loc[
                        frame["class_agreement"], "prescription_rows_n"
                    ].sum()
                    / max(
                        1,
                        frame.loc[frame["api_mapped"], "prescription_rows_n"].sum(),
                    ),
                    "ingredient_agreement_rows_n": frame.loc[
                        frame["ingredient_agreement"], "prescription_rows_n"
                    ].sum(),
                    "ingredient_agreement_among_mapped_rows_pct": 100
                    * frame.loc[
                        frame["ingredient_agreement"], "prescription_rows_n"
                    ].sum()
                    / max(
                        1,
                        frame.loc[frame["api_mapped"], "prescription_rows_n"].sum(),
                    ),
                }
            ),
            include_groups=False,
        )
        .reset_index()
        .rename(columns={"expected_class": "drug_class"})
    )
    by_class.to_csv(
        TABLES / "rxnav_ndc_validation_by_class.csv",
        index=False,
        encoding="utf-8-sig",
    )
    represented_rows = float(result["prescription_rows_n"].sum())
    mapped_rows = float(
        result.loc[result["api_mapped"], "prescription_rows_n"].sum()
    )
    class_agree_rows = float(
        result.loc[result["class_agreement"], "prescription_rows_n"].sum()
    )
    ingredient_agree_rows = float(
        result.loc[result["ingredient_agreement"], "prescription_rows_n"].sum()
    )
    summary = pd.DataFrame(
        [
            {
                "query_date": QUERY_DATE,
                "total_unique_ndcs_n": len(codes),
                "queried_unique_ndcs_n": selected_n,
                "target_row_coverage_pct": 100 * TARGET_ROW_COVERAGE,
                "actual_row_coverage_pct": 100 * represented_rows / total_rows,
                "represented_prescription_rows_n": represented_rows,
                "api_mapped_codes_n": int(result["api_mapped"].sum()),
                "api_mapped_rows_n": mapped_rows,
                "api_mapped_rows_pct": 100 * mapped_rows / represented_rows,
                "class_agreement_among_mapped_rows_pct": 100
                * class_agree_rows
                / max(1, mapped_rows),
                "ingredient_agreement_among_mapped_rows_pct": 100
                * ingredient_agree_rows
                / max(1, mapped_rows),
                "rxnav_version_http_status": version_status,
                "rxnav_version_response": json.dumps(
                    version_payload, ensure_ascii=False, sort_keys=True
                ),
            }
        ]
    )
    summary.to_csv(
        TABLES / "rxnav_ndc_validation_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    manifest = {
        "script_sha256": sha256(Path(__file__)),
        "contract_sha256": observed_contract_hash,
        "query_date": QUERY_DATE,
        "endpoint": BASE_ENDPOINT,
        "version_endpoint": VERSION_ENDPOINT,
        "unique_ndcs_available": len(codes),
        "unique_ndcs_queried": selected_n,
        "represented_row_coverage_pct": 100 * represented_rows / total_rows,
        "http_success_codes_n": int((result["http_status"] == 200).sum()),
        "elapsed_seconds": time.time() - STARTED,
    }
    (MANIFESTS / "30_rxnav_ndc_validation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (ENVIRONMENT / "Python_sessionInfo_RxNav_validation.txt").write_text(
        "\n".join(
            [
                f"timestamp={datetime.now().astimezone().isoformat()}",
                f"python={sys.version}",
                f"pandas={pd.__version__}",
                f"script_sha256={manifest['script_sha256']}",
                f"contract_sha256={observed_contract_hash}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    log(
        "COMPLETE "
        f"mapped_rows_pct={100 * mapped_rows / represented_rows:.3f} "
        f"class_agreement_pct={100 * class_agree_rows / max(1, mapped_rows):.3f} "
        f"elapsed_seconds={time.time() - STARTED:.3f}"
    )


if __name__ == "__main__":
    main()
