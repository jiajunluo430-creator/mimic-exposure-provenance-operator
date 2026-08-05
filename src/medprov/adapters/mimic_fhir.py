"""MIMIC-IV-on-FHIR adapter with strict version-gated execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from medprov.models import ExecutionResult, QueryPlan
from medprov.utils import canonical_json_sha256, utc_now

from .base import BaseAdapter

FHIR_RESOURCES = ("MedicationRequest", "MedicationAdministration", "MedicationDispense")


class MimicFHIRAdapter(BaseAdapter):
    name = "mimic_fhir"
    version = "0.1.0"
    supported_models = ("MIMIC-IV-on-FHIR", "FHIR R4")

    @staticmethod
    def _files(data_root: str | Path | None) -> list[Path]:
        if not data_root:
            return []
        root = Path(data_root)
        if root.is_file() and root.suffix.lower() in {".ndjson", ".jsonl"}:
            return [root]
        if root.is_dir():
            return sorted([*root.rglob("*.ndjson"), *root.rglob("*.jsonl")])
        return []

    @staticmethod
    def _resource_types(files: Iterable[Path]) -> set[str]:
        found: set[str] = set()
        for path in files:
            for resource in FHIR_RESOURCES:
                if resource.lower() in path.name.lower():
                    found.add(resource)
            if found == set(FHIR_RESOURCES):
                break
        return found

    def inspect_source(self, spec, data_root):
        files = self._files(data_root)
        resources = self._resource_types(files)
        required_resources = {
            item.split("/")[-1]
            for item in spec["source_layer"]["tables_or_resources"]
            if item.split("/")[-1] in FHIR_RESOURCES
        }
        data_available = bool(files) and required_resources.issubset(resources)
        reasons: list[str] = []
        if not files:
            reasons.append("Matched MIMIC-IV-on-FHIR NDJSON is not available locally.")
        elif not required_resources.issubset(resources):
            reasons.append(
                "Required FHIR resources are missing: "
                + ", ".join(sorted(required_resources - resources))
            )
        model_version = str(spec["data_model"]["model_version"])
        matched = model_version in {"2.1", "demo-matched"}
        if not matched:
            reasons.append(
                "FHIR execution is version-gated to MIMIC-IV-on-FHIR 2.1 or an explicitly matched demo."
            )
        fields = (
            {
                "status",
                "event_time",
                "route",
                "dose",
                "unit",
                "frequency",
                "medication_class",
                "ingredient",
                "encounter",
                "subject",
            }
            if files
            else set()
        )
        return (
            fields,
            {
                "data_available": data_available,
                "execution_path_available": data_available and matched,
                "resource_types": sorted(resources),
                "matched_version_gate": matched,
                "evaluation_level": "matched_execution"
                if data_available and matched
                else "adapter_or_synthetic_only",
            },
            reasons,
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
                "resourceType-specific status",
                "medication CodeableConcept/reference mapping",
                "encounter/time window",
            ],
            joins=[
                {
                    "left": "Medication[x]",
                    "right": "Medication or contained coding",
                    "keys": ["reference/coding"],
                }
            ],
            deduplication_unit=spec["identity_rule"]["deduplication_unit"],
            time_rule=spec["time_origin_window"]["window_rule"],
            metadata_gates=self.required_metadata_fields(spec),
            unresolved_rules=[
                "unmapped code -> unresolved",
                "required missing element -> configured missing policy",
            ],
            output_profile=spec["output_specification"]["profile"],
            aggregate_only=True,
            implementation={
                "resources": spec["source_layer"]["tables_or_resources"],
                "version_gate": "MIMIC-IV-on-FHIR 2.1 requires native MIMIC-IV 2.2 for exact parity",
            },
        )

    @staticmethod
    def _iter_resources(files: Iterable[Path]) -> Iterable[dict[str, Any]]:
        for path in files:
            with path.open("r", encoding="utf-8-sig") as handle:
                for line in handle:
                    if line.strip():
                        value = json.loads(line)
                        if isinstance(value, dict):
                            yield value

    @staticmethod
    def _class(resource: dict[str, Any]) -> str | None:
        meta = resource.get("meta", {})
        for tag in meta.get("tag", []) if isinstance(meta, dict) else []:
            if tag.get("system") == "https://medprov.org/class":
                return tag.get("code")
        return resource.get("medprovMedicationClass")

    def execute(self, spec, data_root):
        capability = self.capability(spec, data_root)
        provenance = {
            "spec_sha256": canonical_json_sha256(spec),
            "adapter_version": self.version,
            "executed_at_utc": utc_now(),
            "aggregate_only": True,
            "matched_version_gate": capability.source_status.get("matched_version_gate"),
        }
        empty = {
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
                "not_executed_data_unavailable"
                if not capability.source_status.get("data_available")
                else "not_executed_version_mismatch",
                True,
                capability.supported,
                capability.measurable,
                False,
                True,
                empty,
                {},
                {reason: 1 for reason in capability.reasons},
                provenance,
                capability.reasons,
            )
        classes = set(spec["identity_rule"]["class_filter"])
        positive = {str(item).lower() for item in spec["event_semantics_map"]["positive"]}
        negative = {str(item).lower() for item in spec["event_semantics_map"]["negative"]}
        required = self.required_metadata_fields(spec)
        counts: dict[str, Any] = dict(empty)
        by_resource: dict[str, dict[str, int]] = {}
        for resource in self._iter_resources(self._files(data_root)):
            resource_type = str(resource.get("resourceType", ""))
            if resource_type not in FHIR_RESOURCES or self._class(resource) not in classes:
                continue
            status = str(resource.get("status", "")).lower()
            missing = []
            if "route" in required and not resource.get("dosage", {}).get("route"):
                missing.append("route")
            if "dose" in required and not resource.get("dosage", {}).get("dose"):
                missing.append("dose")
            if missing:
                state = "unmeasurable"
            elif status in positive:
                state = "exposed"
            elif status in negative:
                state = "unexposed"
            else:
                state = "unresolved"
            counts[state] += 1
            bucket = by_resource.setdefault(
                resource_type,
                {key: 0 for key in ("exposed", "unexposed", "unresolved", "unmeasurable")},
            )
            bucket[state] += 1
        counts["analysis_units"] = sum(
            counts[key] for key in ("exposed", "unexposed", "unresolved", "unmeasurable")
        )
        counts["by_resource"] = [
            {"resource": key, **value} for key, value in sorted(by_resource.items())
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
            provenance,
            [],
        )
