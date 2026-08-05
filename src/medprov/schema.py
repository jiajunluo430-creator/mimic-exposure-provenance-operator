"""Schema and YAML/JSON document loading."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

OPERATOR_SCHEMA = "medication_exposure_operator.schema.json"
REPORTING_SCHEMA = "medication_exposure_reporting.schema.json"


def load_document(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    text = source.read_text(encoding="utf-8-sig")
    if source.suffix.lower() == ".json":
        value = json.loads(text)
    else:
        value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError(f"Document must be a mapping/object: {source}")
    return value


def _schema_candidates(name: str) -> list[Path]:
    candidates: list[Path] = []
    if os.environ.get("MEDPROV_SCHEMA_DIR"):
        candidates.append(Path(os.environ["MEDPROV_SCHEMA_DIR"]) / name)
    module_path = Path(__file__).resolve()
    candidates.extend(
        [
            module_path.parents[2] / "schemas" / name,
            module_path.parents[3] / "schemas" / name,
            Path(sys.prefix) / "share" / "medprov" / "schemas" / name,
        ]
    )
    return candidates


def schema_path(name: str) -> Path:
    for candidate in _schema_candidates(name):
        if candidate.is_file():
            return candidate
    rendered = "\n".join(str(item) for item in _schema_candidates(name))
    raise FileNotFoundError(f"Could not locate schema {name}; searched:\n{rendered}")


def load_schema(name: str) -> dict[str, Any]:
    return json.loads(schema_path(name).read_text(encoding="utf-8"))


def validation_errors(document: dict[str, Any], schema_name: str) -> list[str]:
    validator = Draft202012Validator(load_schema(schema_name), format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def validate_operator(document: dict[str, Any]) -> list[str]:
    return validation_errors(document, OPERATOR_SCHEMA)


def validate_reporting(document: dict[str, Any]) -> list[str]:
    return validation_errors(document, REPORTING_SCHEMA)
