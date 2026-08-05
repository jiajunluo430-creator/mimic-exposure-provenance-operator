"""Aggregate-only operator execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters import get_adapter
from .models import ExecutionResult
from .reporting import write_report_bundle
from .schema import load_document, validate_operator
from .utils import assert_public_aggregate


def execute_operator(
    spec: dict[str, Any], adapter_name: str | None = None, data_root: str | Path | None = None
) -> ExecutionResult:
    errors = validate_operator(spec)
    if errors:
        raise ValueError("Invalid operator specification:\n" + "\n".join(errors))
    requested = adapter_name or spec["data_model"]["adapter"]
    result = get_adapter(requested).execute(spec, data_root)
    payload = result.to_dict()
    if not result.aggregate_only:
        raise ValueError("Adapter attempted non-aggregate output; execution stopped.")
    assert_public_aggregate(payload)
    return result


def execute_operator_file(
    path: str | Path,
    adapter_name: str | None = None,
    data_root: str | Path | None = None,
    aggregate_out: str | Path | None = None,
) -> ExecutionResult:
    spec = load_document(path)
    result = execute_operator(spec, adapter_name=adapter_name, data_root=data_root)
    if aggregate_out:
        write_report_bundle(
            aggregate_out,
            spec["operator_id"],
            f"medprov execution: {spec['operator_id']}",
            result.to_dict(),
        )
    return result
