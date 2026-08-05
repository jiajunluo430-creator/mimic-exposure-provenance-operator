"""Adapter interface and shared capability logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from medprov import CORE_DIMENSIONS
from medprov.models import CapabilityResult, ExecutionResult, QueryPlan


class AdapterError(RuntimeError):
    """Base adapter error."""


class DataUnavailableError(AdapterError):
    """Raised when an otherwise-supported adapter has no usable local data."""


class UnmeasurableError(AdapterError):
    """Raised when required source fields or semantics are unavailable."""


class BaseAdapter(ABC):
    name = "base"
    version = "0.1.0"
    supported_models: tuple[str, ...] = ()
    supported_dimensions: tuple[str, ...] = CORE_DIMENSIONS
    field_aliases: dict[str, tuple[str, ...]] = {
        "route": ("route", "route_source_value", "route_concept_id"),
        "dose": ("dose", "dose_given", "quantity", "amount"),
        "unit": ("unit", "dose_unit", "dose_unit_source_value"),
        "frequency": ("frequency", "frequency_source_value"),
        "status": ("status", "event_txt", "event_state"),
    }

    def supports_model(self, spec: dict[str, Any]) -> bool:
        requested = str(spec["data_model"]["model_name"]).lower()
        return not self.supported_models or requested in {
            item.lower() for item in self.supported_models
        }

    @staticmethod
    def required_metadata_fields(spec: dict[str, Any]) -> list[str]:
        metadata = spec["required_metadata"]
        return [
            field
            for field in ("route", "dose", "unit", "frequency", "status")
            if metadata[field] == "required"
        ]

    def capability(self, spec: dict[str, Any], data_root: str | Path | None) -> CapabilityResult:
        available_fields, source_status, reasons = self.inspect_source(spec, data_root)
        required = self.required_metadata_fields(spec)
        missing: list[str] = []
        available_lower = {item.lower() for item in available_fields}
        for logical_field in required:
            aliases = self.field_aliases.get(logical_field, (logical_field,))
            if not any(alias.lower() in available_lower for alias in aliases):
                missing.append(logical_field)
        supported = self.supports_model(spec) and set(CORE_DIMENSIONS).issubset(
            self.supported_dimensions
        )
        measurable = supported and not missing and bool(source_status.get("data_available", False))
        executable = measurable and bool(source_status.get("execution_path_available", False))
        dimension_status = {dimension: "supported" for dimension in CORE_DIMENSIONS}
        if not supported:
            for dimension in CORE_DIMENSIONS:
                if dimension not in self.supported_dimensions:
                    dimension_status[dimension] = "unsupported"
        if missing:
            dimension_status["required_metadata"] = "unmeasurable"
            reasons.append("Missing required metadata: " + ", ".join(missing))
        if not source_status.get("data_available", False):
            dimension_status["source_layer"] = "not_evaluated_data_unavailable"
        return CapabilityResult(
            adapter=self.name,
            adapter_version=self.version,
            supported=supported,
            measurable=measurable,
            executable=executable,
            dimension_status=dimension_status,
            required_fields=required,
            available_fields=sorted(available_fields),
            missing_fields=missing,
            source_status=source_status,
            reasons=reasons,
        )

    @abstractmethod
    def inspect_source(
        self, spec: dict[str, Any], data_root: str | Path | None
    ) -> tuple[set[str], dict[str, Any], list[str]]:
        """Return available fields, source status, and reasons."""

    @abstractmethod
    def compile(self, spec: dict[str, Any], data_root: str | Path | None) -> QueryPlan:
        """Compile a specification to an adapter-specific query plan."""

    @abstractmethod
    def execute(self, spec: dict[str, Any], data_root: str | Path | None) -> ExecutionResult:
        """Execute a specification and return aggregate-only output."""
