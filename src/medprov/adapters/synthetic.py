"""Deterministic synthetic adapter used for public end-to-end tests."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from medprov.models import ExecutionResult, QueryPlan
from medprov.utils import canonical_json_sha256, utc_now

from .base import BaseAdapter


class SyntheticAdapter(BaseAdapter):
    name = "synthetic"
    version = "0.1.0"
    supported_models = ("medprov synthetic",)

    def _fixture(self, data_root: str | Path | None) -> Path | None:
        if not data_root:
            return None
        path = Path(data_root)
        if path.is_file():
            return path
        candidate = path / "canonical_events.csv"
        return candidate if candidate.is_file() else None

    def inspect_source(self, spec, data_root):
        fixture = self._fixture(data_root)
        if not fixture:
            return (
                set(),
                {"data_available": False, "execution_path_available": True},
                ["Synthetic fixture not found."],
            )
        with fixture.open("r", encoding="utf-8-sig", newline="") as handle:
            fields = set(next(csv.reader(handle)))
        return (
            fields,
            {"data_available": True, "execution_path_available": True, "fixture": fixture.name},
            [],
        )

    def compile(self, spec, data_root):
        return QueryPlan(
            operator_id=spec["operator_id"],
            operator_version=spec["operator_version"],
            adapter=self.name,
            adapter_version=self.version,
            data_model_version=spec["data_model"]["model_version"],
            sources=spec["source_layer"]["tables_or_resources"],
            analysis_unit=spec["analysis_unit"],
            predicates=[
                "class in class_filter",
                "event_state mapped literally",
                "required metadata checked",
            ],
            joins=[],
            deduplication_unit=spec["identity_rule"]["deduplication_unit"],
            time_rule=spec["time_origin_window"]["window_rule"],
            metadata_gates=self.required_metadata_fields(spec),
            unresolved_rules=[
                "unknown state -> unresolved",
                "missing required field -> configured missing policy",
            ],
            output_profile=spec["output_specification"]["profile"],
            aggregate_only=True,
            implementation={"engine": "csv_dict_reader"},
        )

    def execute(self, spec, data_root):
        capability = self.capability(spec, data_root)
        counts: dict[str, Any] = {
            state: 0 for state in ("exposed", "unexposed", "unresolved", "unmeasurable")
        }
        by_class: dict[str, dict[str, int]] = {}
        if not capability.executable:
            return ExecutionResult(
                spec["operator_id"],
                spec["operator_version"],
                self.name,
                "not_executed_data_unavailable",
                True,
                capability.supported,
                capability.measurable,
                False,
                True,
                counts,
                {},
                {reason: 1 for reason in capability.reasons},
                {
                    "spec_sha256": canonical_json_sha256(spec),
                    "executed_at_utc": utc_now(),
                    "aggregate_only": True,
                },
                capability.reasons,
            )
        fixture = self._fixture(data_root)
        assert fixture is not None
        positive = {str(item).strip().lower() for item in spec["event_semantics_map"]["positive"]}
        negative = {str(item).strip().lower() for item in spec["event_semantics_map"]["negative"]}
        excluded = {str(item).strip().lower() for item in spec["event_semantics_map"]["excluded"]}
        classes = set(spec["identity_rule"]["class_filter"])
        required = self.required_metadata_fields(spec)
        with fixture.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                medication_class = str(row.get("medication_class", ""))
                if medication_class not in classes:
                    continue
                missing = [field for field in required if not str(row.get(field, "")).strip()]
                if missing:
                    state = (
                        "unmeasurable"
                        if spec["required_metadata"]["missing_policy"] == "unmeasurable"
                        else "unresolved"
                    )
                else:
                    event_state = str(row.get("event_state", "")).strip().lower() or "<blank>"
                    if event_state in positive:
                        state = "exposed"
                    elif event_state in negative:
                        state = "unexposed"
                    elif event_state in excluded:
                        state = "unresolved"
                    else:
                        state = "unresolved"
                counts[state] += 1
                by_class.setdefault(medication_class, {name: 0 for name in counts})[state] += 1
        counts["analysis_units"] = sum(
            counts[state] for state in ("exposed", "unexposed", "unresolved", "unmeasurable")
        )
        counts["by_class"] = [
            {"medication_class": name, **states} for name, states in sorted(by_class.items())
        ]
        return ExecutionResult(
            spec["operator_id"],
            spec["operator_version"],
            self.name,
            "executed",
            True,
            True,
            True,
            True,
            True,
            counts,
            {},
            {},
            {
                "spec_sha256": canonical_json_sha256(spec),
                "executed_at_utc": utc_now(),
                "aggregate_only": True,
                "fixture": fixture.name,
            },
            [],
        )
