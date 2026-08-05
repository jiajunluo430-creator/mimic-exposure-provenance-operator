"""Specification-to-adapter plan compilation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters import get_adapter
from .models import QueryPlan
from .schema import load_document, validate_operator


def compile_operator(
    spec: dict[str, Any], adapter_name: str | None = None, data_root: str | Path | None = None
) -> QueryPlan:
    errors = validate_operator(spec)
    if errors:
        raise ValueError("Invalid operator specification:\n" + "\n".join(errors))
    requested = adapter_name or spec["data_model"]["adapter"]
    adapter = get_adapter(requested)
    return adapter.compile(spec, data_root)


def compile_operator_file(
    path: str | Path, adapter_name: str | None = None, data_root: str | Path | None = None
) -> QueryPlan:
    return compile_operator(load_document(path), adapter_name=adapter_name, data_root=data_root)
