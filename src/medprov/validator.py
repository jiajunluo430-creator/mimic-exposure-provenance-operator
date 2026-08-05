"""Operator and structured-reporting validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from . import CORE_DIMENSIONS
from .adapters import get_adapter
from .models import ValidationResult
from .schema import load_document, validate_operator, validate_reporting
from .utils import sha256_file


def _resolve_reference(spec_path: Path, reference: str) -> Path | None:
    candidate = Path(reference)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    for parent in [spec_path.parent, *spec_path.parents]:
        possible = parent / reference
        if possible.is_file():
            return possible
    return None


def _traceability(spec: dict[str, Any], spec_path: Path) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    checks = [
        (spec["provenance"]["contract_path"], spec["provenance"]["contract_sha256"], "contract"),
        (
            spec["identity_rule"]["code_list"]["path"],
            spec["identity_rule"]["code_list"]["sha256"],
            "code list",
        ),
        (spec["provenance"]["generator"], spec["provenance"]["generator_sha256"], "generator"),
    ]
    passed = True
    for reference, expected, label in checks:
        resolved = _resolve_reference(spec_path, reference)
        if resolved is None:
            passed = False
            warnings.append(f"Could not resolve {label} path: {reference}")
        elif sha256_file(resolved).lower() != str(expected).lower():
            passed = False
            warnings.append(f"{label.capitalize()} SHA-256 mismatch: {reference}")
    return passed, warnings


def validate_specification(
    spec: dict[str, Any],
    spec_path: str | Path | None = None,
    adapter_name: str | None = None,
    data_root: str | Path | None = None,
) -> ValidationResult:
    errors = validate_operator(spec)
    syntactic = not errors
    if not syntactic:
        return ValidationResult(syntactically_valid=False, errors=errors)
    resolved_path = Path(spec_path) if spec_path else Path.cwd() / "operator.yaml"
    traceable, warnings = _traceability(spec, resolved_path)
    if adapter_name is None:
        return ValidationResult(
            syntactically_valid=True,
            reproducible_traceable=traceable,
            warnings=warnings,
            details={"core_dimensions": list(CORE_DIMENSIONS)},
        )
    adapter = get_adapter(adapter_name)
    capability = adapter.capability(spec, data_root)
    return ValidationResult(
        syntactically_valid=True,
        adapter_supported=capability.supported,
        measurable=capability.measurable,
        executable=capability.executable,
        reproducible_traceable=traceable,
        warnings=warnings + capability.reasons,
        details={"capability": capability.to_dict(), "core_dimensions": list(CORE_DIMENSIONS)},
    )


def validate_specification_file(
    path: str | Path, adapter_name: str | None = None, data_root: str | Path | None = None
) -> ValidationResult:
    return validate_specification(
        load_document(path), spec_path=path, adapter_name=adapter_name, data_root=data_root
    )


def load_reporting_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.is_dir():
        records: list[dict[str, Any]] = []
        for child in sorted(
            [*source.glob("*.json"), *source.glob("*.yaml"), *source.glob("*.yml")]
        ):
            records.append(load_document(child))
        return records
    if source.suffix.lower() in {".jsonl", ".ndjson"}:
        return [
            json.loads(line)
            for line in source.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    value = load_document(source)
    if isinstance(value.get("records"), list):
        return list(value["records"])
    return [value]


def validate_reporting_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    validated: list[dict[str, Any]] = []
    dimension_counts = {
        dimension: {status: 0 for status in ("reported", "missing", "ambiguous", "not_applicable")}
        for dimension in CORE_DIMENSIONS
    }
    indicators = {
        "named_native_source": 0,
        "executable_identity": 0,
        "complete_executable_operator": 0,
    }
    total = 0
    invalid = 0
    for record in records:
        total += 1
        errors = validate_reporting(record)
        if errors:
            invalid += 1
            validated.append({"study_id": record.get("study_id"), "valid": False, "errors": errors})
            continue
        for dimension in CORE_DIMENSIONS:
            status = record["dimensions"][dimension]["status"]
            dimension_counts[dimension][status] += 1
        operational = record["operational_indicators"]
        for key in indicators:
            indicators[key] += int(bool(operational[key]))
        missing = [
            dimension
            for dimension in CORE_DIMENSIONS
            if record["dimensions"][dimension]["status"] != "reported"
        ]
        validated.append(
            {
                "study_id": record["study_id"],
                "valid": True,
                "reported_dimensions_n": len(CORE_DIMENSIONS) - len(missing),
                "missing_or_ambiguous_dimensions": missing,
                "database_executable_operator": bool(operational["complete_executable_operator"]),
            }
        )
    return {
        "records_n": total,
        "valid_records_n": total - invalid,
        "invalid_records_n": invalid,
        "dimension_counts": dimension_counts,
        "operational_indicator_counts": indicators,
        "records": validated,
        "primary_validator_mode": "structured_human_coded_input",
        "text_assist_used_for_primary_results": False,
    }
