"""Typed result objects used by the medprov compiler and adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CANONICAL_INTERMEDIATE_FIELDS = (
    "subject_key",
    "encounter_key",
    "analysis_unit_key",
    "medication_class",
    "ingredient",
    "source_layer",
    "native_record_id",
    "native_order_id",
    "event_time",
    "event_state",
    "dose",
    "unit",
    "route",
    "frequency",
    "provenance_flags",
    "classification",
)

RESTRICTED_LOCAL_FIELDS = (
    "subject_key",
    "encounter_key",
    "analysis_unit_key",
    "native_record_id",
    "native_order_id",
    "subject_id",
    "hadm_id",
    "stay_id",
    "poe_id",
    "pharmacy_id",
    "emar_id",
)


@dataclass(frozen=True)
class ValidationResult:
    syntactically_valid: bool
    adapter_supported: bool | None = None
    measurable: bool | None = None
    executable: bool | None = None
    reproducible_traceable: bool | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityResult:
    adapter: str
    adapter_version: str
    supported: bool
    measurable: bool
    executable: bool
    dimension_status: dict[str, str]
    required_fields: list[str]
    available_fields: list[str]
    missing_fields: list[str]
    source_status: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueryPlan:
    operator_id: str
    operator_version: str
    adapter: str
    adapter_version: str
    data_model_version: str
    sources: list[str]
    analysis_unit: str
    predicates: list[str]
    joins: list[dict[str, Any]]
    deduplication_unit: list[str]
    time_rule: str
    metadata_gates: list[str]
    unresolved_rules: list[str]
    output_profile: str
    aggregate_only: bool
    implementation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionResult:
    operator_id: str
    operator_version: str
    adapter: str
    status: str
    syntactically_valid: bool
    adapter_supported: bool
    measurable: bool
    executable: bool
    aggregate_only: bool
    counts: dict[str, Any]
    metrics: dict[str, Any]
    failure_reasons: dict[str, int]
    provenance: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
