"""OMOP CDM DRUG_EXPOSURE adapter and semantic-loss smoke test."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from medprov.models import ExecutionResult, QueryPlan
from medprov.utils import canonical_json_sha256, utc_now

from .base import BaseAdapter


class OmopAdapter(BaseAdapter):
    name = "omop"
    version = "0.1.0"
    supported_models = ("OMOP CDM", "OMOP")

    @staticmethod
    def _drug_exposure(data_root: str | Path | None) -> Path | None:
        if not data_root:
            return None
        root = Path(data_root)
        if root.is_file():
            return root
        for name in ("DRUG_EXPOSURE.csv", "drug_exposure.csv"):
            candidate = root / name
            if candidate.is_file():
                return candidate
        return None

    def inspect_source(self, spec, data_root):
        source = self._drug_exposure(data_root)
        if not source:
            return (
                set(),
                {
                    "data_available": False,
                    "execution_path_available": True,
                    "evaluation_level": "synthetic_capability_only",
                },
                ["OMOP DRUG_EXPOSURE input is not available locally."],
            )
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            fields = set(next(csv.reader(handle)))
        return (
            fields,
            {
                "data_available": True,
                "execution_path_available": True,
                "source_file": source.name,
                "evaluation_level": "demo_or_fixture_smoke_test",
            },
            [],
        )

    def compile(self, spec, data_root):
        return QueryPlan(
            operator_id=spec["operator_id"],
            operator_version=spec["operator_version"],
            adapter=self.name,
            adapter_version=self.version,
            data_model_version=spec["data_model"]["model_version"],
            sources=["DRUG_EXPOSURE"],
            analysis_unit=spec["analysis_unit"],
            predicates=[
                "drug_concept_id/source value mapping",
                "start/end datetime window",
                "drug_type provenance",
            ],
            joins=[
                {
                    "left": "DRUG_EXPOSURE",
                    "right": "VISIT_OCCURRENCE",
                    "keys": ["visit_occurrence_id"],
                }
            ],
            deduplication_unit=spec["identity_rule"]["deduplication_unit"],
            time_rule=spec["time_origin_window"]["window_rule"],
            metadata_gates=self.required_metadata_fields(spec),
            unresolved_rules=[
                "source-specific event state absent -> extension_required/unresolved"
            ],
            output_profile=spec["output_specification"]["profile"],
            aggregate_only=True,
            implementation={
                "table": "DRUG_EXPOSURE",
                "source_fields": [
                    "drug_source_value",
                    "route_source_value",
                    "dose_unit_source_value",
                    "drug_type_concept_id",
                ],
                "provenance_extension": "medprov_source_provenance",
            },
        )

    def execute(self, spec, data_root):
        capability = self.capability(spec, data_root)
        provenance = {
            "spec_sha256": canonical_json_sha256(spec),
            "adapter_version": self.version,
            "executed_at_utc": utc_now(),
            "aggregate_only": True,
            "evaluation_level": capability.source_status.get("evaluation_level"),
        }
        counts: dict[str, Any] = {
            "analysis_units": 0,
            "exposed": 0,
            "unexposed": 0,
            "unresolved": 0,
            "unmeasurable": 0,
        }
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
                provenance,
                capability.reasons,
            )
        source = self._drug_exposure(data_root)
        assert source is not None
        classes = set(spec["identity_rule"]["class_filter"])
        ingredients = {
            str(item).lower() for item in spec["identity_rule"].get("ingredient_filter", [])
        }
        required = self.required_metadata_fields(spec)
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                med_class = row.get("medprov_class", "")
                source_value = str(row.get("drug_source_value", "")).lower()
                if med_class not in classes and not any(
                    item in source_value for item in ingredients
                ):
                    continue
                missing = []
                alias = {
                    "route": ("route_source_value", "route_concept_id"),
                    "dose": ("quantity",),
                    "unit": ("dose_unit_source_value",),
                    "frequency": ("sig",),
                    "status": ("medprov_event_state",),
                }
                for logical in required:
                    if not any(str(row.get(field, "")).strip() for field in alias[logical]):
                        missing.append(logical)
                state = "unmeasurable" if missing else "exposed"
                counts[state] += 1
        counts["analysis_units"] = sum(
            counts[key] for key in ("exposed", "unexposed", "unresolved", "unmeasurable")
        )
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
            {"interpretation": "OMOP capability/smoke test; not clinical external validation"},
            {},
            provenance,
            [],
        )
