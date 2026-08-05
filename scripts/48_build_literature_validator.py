#!/usr/bin/env python3
"""Transform the frozen 40-study coding table and run the structured validator."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from medprov.reporting import render_html, render_markdown
from medprov.schema import validate_reporting
from medprov.validator import validate_reporting_records

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "literature_validator_v0_1_0"
RECORDS = OUT / "structured_records"
TABLES = OUT / "tables"
REPORTS = OUT / "reports"
MANIFESTS = OUT / "manifests"

SOURCE_ROOT = ROOT / "outputs" / "jamia_residual_provenance_v1_0" / "tables"
CODING = SOURCE_ROOT / "published_operator_landscape_expanded_evidence_sample.csv"
SCOPE = SOURCE_ROOT / "published_operator_evidence_scope.csv"
DIFF = SOURCE_ROOT / "published_operator_landscape_evidence_scope_coding_diff.csv"
CONTRACT = ROOT / "contracts" / "LITERATURE_VALIDATOR_CONTRACT_v1.0_2026-08-05.md"
CONTRACT_SHA = ROOT / "contracts" / "LITERATURE_VALIDATOR_CONTRACT_v1.0_2026-08-05.sha256"

DIMENSIONS = {
    "source_layer": ("named_native_table_reported", "source_evidence"),
    "identity_rule": ("database_identity_rule_reported", "identity_evidence"),
    "time_origin_window": ("time_origin_and_window_reported", "time_evidence"),
    "event_semantics_map": ("event_semantics_reported", None),
    "required_metadata": ("dose_or_route_reported", "dose_route_evidence"),
}
EXPECTED = {
    "source_layer": 7,
    "identity_rule": 2,
    "time_origin_window": 35,
    "event_semantics_map": 0,
    "required_metadata": 30,
    "complete_executable_operator": 0,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_code(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"true", "yes", "1", "reported"}:
        return "reported"
    if normalized in {"false", "no", "0", "missing"}:
        return "missing"
    if normalized in {"unclear", "ambiguous"}:
        return "ambiguous"
    if normalized in {"not_applicable", "n/a", "na"}:
        return "not_applicable"
    raise ValueError(f"Unsupported frozen coding value: {value!r}")


def parse_bool(value: str) -> bool:
    return parse_code(value) == "reported"


def split_urls(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[|;]", value or "") if item.strip()]


def evidence_scope_status(value: str, kind: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "retrieved_and_reviewed":
        return "reviewed"
    if normalized == "none_linked":
        return "none_linked"
    if normalized == "generic_repository_only" and kind == "repository":
        return "generic_only"
    if normalized in {"partly_retrieved", "linked_unavailable"}:
        return "not_available"
    return "not_reviewed"


def short_note(value: str | None, fallback: str) -> str:
    rendered = (value or fallback).strip().replace("\n", " ")
    return rendered[:240]


def assert_contract() -> None:
    required = [CODING, SCOPE, DIFF, CONTRACT, CONTRACT_SHA]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing frozen literature-validator inputs:\n" + "\n".join(missing)
        )
    expected = CONTRACT_SHA.read_text(encoding="utf-8").split()[0].lower()
    actual = sha256_file(CONTRACT)
    if actual != expected:
        raise RuntimeError(f"Literature validator contract hash mismatch: {actual} != {expected}")


def build_records() -> list[dict[str, Any]]:
    coded = read_csv(CODING)
    if len(coded) != 40:
        raise RuntimeError(f"Frozen study count gate failed: {len(coded)} != 40")
    scope_by_pmid = {row["pmid"]: row for row in read_csv(SCOPE)}
    diff_by_key = {(row["pmcid"], row["field"]): row for row in read_csv(DIFF)}
    records: list[dict[str, Any]] = []
    for row in coded:
        scope = scope_by_pmid.get(row["pmid"])
        if scope is None:
            raise RuntimeError(f"No evidence-scope row for PMID {row['pmid']}")
        dimensions: dict[str, Any] = {}
        for dimension, (source_field, note_field) in DIMENSIONS.items():
            status = parse_code(row[source_field])
            evidence: list[dict[str, str]] = []
            if status == "reported":
                changed = diff_by_key.get((row["pmcid"], source_field))
                source = "supplement" if changed else "main_text"
                location = (
                    changed["evidence_source"] if changed else "Expanded main-text coding packet"
                )
                fallback = {
                    "source_layer": "Native medication source reported",
                    "identity_rule": "Database-executable medication identity reported",
                    "time_origin_window": "Time origin and exposure window reported",
                    "event_semantics_map": "Native event-state semantics reported",
                    "required_metadata": "Dose or route constraint reported",
                }[dimension]
                note = changed["evidence_summary"] if changed else row.get(note_field or "", "")
                evidence = [
                    {
                        "source": source,
                        "location": location,
                        "short_note": short_note(note, fallback),
                    }
                ]
            dimensions[dimension] = {"status": status, "evidence": evidence}

        urls = split_urls(scope.get("article_specific_repository_urls", ""))
        record = {
            "schema_version": "1.0.0",
            "study_id": f"mimic-medication-{int(row['sample_order']):02d}",
            "citation": {
                "title": row["title"],
                "pmid": row["pmid"] or None,
                "pmcid": row["pmcid"] or None,
                "doi": row["doi"] or None,
            },
            "database": "MIMIC-IV",
            "evidence_scope": {
                "main_text": "reviewed"
                if parse_bool(row["main_text_reviewed"])
                else "not_reviewed",
                "supplement": evidence_scope_status(row["supplement_status"], "supplement"),
                "article_repository": evidence_scope_status(
                    row["article_specific_repo_status"], "repository"
                ),
            },
            "dimensions": dimensions,
            "repository": {
                "url_reported": bool(urls),
                "version_reported": False,
                "hash_reported": False,
                "urls": urls,
            },
            "operational_indicators": {
                "named_native_source": parse_bool(row["named_native_table_reported"]),
                "executable_identity": parse_bool(row["database_identity_rule_reported"]),
                "complete_executable_operator": parse_bool(
                    row["fully_executable_exposure_operator"]
                ),
            },
            "coder": {
                "coder_id": "primary_coder_1",
                "review_date": "2026-08-01",
                "notes": "Single-primary-coder structured transformation; no independent recode available.",
            },
        }
        errors = validate_reporting(record)
        if errors:
            raise RuntimeError(f"Reporting schema failure for {record['study_id']}: {errors}")
        records.append(record)
    return records


def write_records(records: list[dict[str, Any]]) -> None:
    RECORDS.mkdir(parents=True, exist_ok=True)
    jsonl_lines: list[str] = []
    for record in records:
        payload = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        (RECORDS / f"{record['study_id']}.json").write_text(payload, encoding="utf-8", newline="\n")
        jsonl_lines.append(json.dumps(record, sort_keys=True, ensure_ascii=False))
    (OUT / "published_operator_reporting_records.jsonl").write_text(
        "\n".join(jsonl_lines) + "\n", encoding="utf-8", newline="\n"
    )


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validate_gates(result: dict[str, Any]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    counts = result["dimension_counts"]
    for dimension in DIMENSIONS:
        expected = EXPECTED[dimension]
        actual = int(counts[dimension]["reported"])
        gates.append(
            {
                "gate": dimension,
                "expected_n": expected,
                "actual_n": actual,
                "status": "PASS" if expected == actual else "FAIL",
            }
        )
    actual_complete = int(result["operational_indicator_counts"]["complete_executable_operator"])
    gates.append(
        {
            "gate": "complete_executable_operator",
            "expected_n": EXPECTED["complete_executable_operator"],
            "actual_n": actual_complete,
            "status": "PASS" if actual_complete == 0 else "FAIL",
        }
    )
    gates.append(
        {
            "gate": "schema_valid_records",
            "expected_n": 40,
            "actual_n": int(result["valid_records_n"]),
            "status": "PASS" if int(result["valid_records_n"]) == 40 else "FAIL",
        }
    )
    return gates


def report(result: dict[str, Any], gates: list[dict[str, Any]]) -> str:
    complete = result["operational_indicator_counts"]["complete_executable_operator"]
    lines = [
        "# Literature/reporting validator report",
        "",
        "## Decision: PASS"
        if all(row["status"] == "PASS" for row in gates)
        else "## Decision: FAIL",
        "",
        "The primary validator executed on 40 human-coded structured records. It did not infer fields from article prose, and no text-assist or LLM classification was used for the primary result.",
        "",
        "## Reproduced reporting gaps",
        "",
        f"- Named native medication source: {result['operational_indicator_counts']['named_native_source']}/40.",
        f"- Database-executable identity: {result['operational_indicator_counts']['executable_identity']}/40.",
        f"- Time origin and exposure window: {result['dimension_counts']['time_origin_window']['reported']}/40.",
        f"- Native event-state semantics: {result['dimension_counts']['event_semantics_map']['reported']}/40.",
        f"- Dose or route rule: {result['dimension_counts']['required_metadata']['reported']}/40.",
        f"- Complete executable five-dimensional operator: {complete}/40.",
        "",
        "The result is not that the reviewed studies necessarily used incorrect exposure definitions; the reproducibility problem is that their published evidence did not specify a complete database-executable operator.",
        "",
        "## Evidence scope",
        "",
        "All 40 main texts, 55/56 linked supplementary files, and three article-specific repositories had already been reviewed. Generic MIT-LCP repositories were not treated as article-specific executable code. The 86 studies removed by the open-access filter could have higher or lower reporting completeness, so direction of selection bias is unknown. This sample remains a structured landscape audit, not a systematic review.",
        "",
        "## Independent recoding",
        "",
        "Status: `AUTHOR_ACTION_REQUIRED_SECOND_CODER`. The public package includes blinded instructions, import validation, and agreement analysis, but no second coder result or kappa is claimed because the existing worksheet is blank.",
    ]
    return "\n".join(lines) + "\n"


def build_manifest() -> dict[str, Any]:
    files = sorted(
        path
        for path in OUT.rglob("*")
        if path.is_file() and path.name != "literature_validator_manifest.json"
    )
    return {
        "artifact": "literature_validator_v0_1_0",
        "contract_sha256": sha256_file(CONTRACT),
        "primary_validator_mode": "structured_human_coded_input",
        "text_assist_used_for_primary_results": False,
        "independent_second_coder_status": "AUTHOR_ACTION_REQUIRED_SECOND_CODER",
        "files": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }


def main() -> int:
    assert_contract()
    for directory in (RECORDS, TABLES, REPORTS, MANIFESTS):
        directory.mkdir(parents=True, exist_ok=True)
    records = build_records()
    write_records(records)
    result = validate_reporting_records(records)
    gates = validate_gates(result)
    summary_rows = [
        {
            "dimension": dimension,
            "reported_n": result["dimension_counts"][dimension]["reported"],
            "missing_n": result["dimension_counts"][dimension]["missing"],
            "ambiguous_n": result["dimension_counts"][dimension]["ambiguous"],
            "not_applicable_n": result["dimension_counts"][dimension]["not_applicable"],
            "sample_n": 40,
        }
        for dimension in DIMENSIONS
    ]
    study_rows = [
        {
            "study_id": row["study_id"],
            "valid": row["valid"],
            "reported_dimensions_n": row.get("reported_dimensions_n", ""),
            "missing_or_ambiguous_dimensions": "|".join(
                row.get("missing_or_ambiguous_dimensions", [])
            ),
            "database_executable_operator": row.get("database_executable_operator", False),
        }
        for row in result["records"]
    ]
    write_tsv(
        TABLES / "reporting_dimension_summary.tsv",
        summary_rows,
        [
            "dimension",
            "reported_n",
            "missing_n",
            "ambiguous_n",
            "not_applicable_n",
            "sample_n",
        ],
    )
    write_tsv(
        TABLES / "study_missing_dimensions.tsv",
        study_rows,
        [
            "study_id",
            "valid",
            "reported_dimensions_n",
            "missing_or_ambiguous_dimensions",
            "database_executable_operator",
        ],
    )
    write_tsv(
        TABLES / "validator_parity_gates.tsv", gates, ["gate", "expected_n", "actual_n", "status"]
    )
    machine_path = OUT / "literature_validator_result.json"
    machine_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    narrative = report(result, gates)
    (REPORTS / "LITERATURE_VALIDATOR_REPORT.md").write_text(
        narrative, encoding="utf-8", newline="\n"
    )
    (REPORTS / "LITERATURE_VALIDATOR_RESULT.md").write_text(
        render_markdown("Structured reporting validator result", result),
        encoding="utf-8",
        newline="\n",
    )
    (REPORTS / "LITERATURE_VALIDATOR_RESULT.html").write_text(
        render_html("Structured reporting validator result", result),
        encoding="utf-8",
        newline="\n",
    )
    manifest = build_manifest()
    (MANIFESTS / "literature_validator_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    passed = all(row["status"] == "PASS" for row in gates)
    if not passed:
        failed = [row for row in gates if row["status"] != "PASS"]
        (REPORTS / "LITERATURE_MAPPING_DIAGNOSTIC.md").write_text(
            "# Literature mapping diagnostic\n\n"
            + "\n".join(
                f"- {row['gate']}: expected {row['expected_n']}, actual {row['actual_n']}"
                for row in failed
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return 2
    print("PASS literature validator: 40/40 valid; 7/40 source, 2/40 identity, 0/40 complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
