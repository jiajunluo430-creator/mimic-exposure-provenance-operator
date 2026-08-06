"""MIMIC-IV-on-FHIR adapter with strict version-gated execution."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Iterable, TextIO

from medprov.identity import NameRule, classify_strings, load_name_rules
from medprov.models import ExecutionResult, QueryPlan
from medprov.utils import canonical_json_sha256, utc_now

from .base import BaseAdapter

FHIR_EVENT_RESOURCES = (
    "MedicationRequest",
    "MedicationAdministration",
    "MedicationDispense",
)
FHIR_SUPPORT_RESOURCES = ("Medication", "Encounter", "Patient")
FHIR_RESOURCES = FHIR_EVENT_RESOURCES + FHIR_SUPPORT_RESOURCES


class MimicFHIRAdapter(BaseAdapter):
    name = "mimic_fhir"
    version = "0.1.0"
    supported_models = ("MIMIC-IV-on-FHIR", "FHIR R4")

    @staticmethod
    def _files(data_root: str | Path | None) -> list[Path]:
        if not data_root:
            return []
        root = Path(data_root)

        def usable(path: Path) -> bool:
            lower = path.name.lower()
            return lower.endswith((".ndjson", ".jsonl", ".ndjson.gz", ".jsonl.gz"))

        if root.is_file() and usable(root):
            return [root]
        if root.is_dir():
            return sorted(path for path in root.rglob("*") if path.is_file() and usable(path))
        return []

    @staticmethod
    def _open_text(path: Path) -> TextIO:
        if path.name.lower().endswith(".gz"):
            return gzip.open(path, "rt", encoding="utf-8-sig")
        return path.open("r", encoding="utf-8-sig")

    @staticmethod
    def _resource_types(files: Iterable[Path]) -> set[str]:
        found: set[str] = set()
        for path in files:
            lower = path.name.lower()
            for resource in FHIR_RESOURCES:
                if resource.lower() in lower:
                    found.add(resource)
        return found

    @staticmethod
    def _event_profile_from_filename(path: Path) -> str | None:
        lower = path.name.lower()
        if "medicationadministrationicu" in lower:
            return "MedicationAdministrationICU"
        if "medicationadministration" in lower:
            return "MedicationAdministration"
        if "medicationrequest" in lower:
            return "MedicationRequest"
        if "medicationdispense" in lower and "dispenseed" not in lower:
            return "MedicationDispense"
        return None

    @classmethod
    def _selected_event_files(cls, files: list[Path], selected: set[str]) -> list[Path]:
        chosen: list[Path] = []
        for path in files:
            profile = cls._event_profile_from_filename(path)
            if profile is None or profile in selected:
                chosen.append(path)
        return chosen

    @staticmethod
    def _event_resources(spec: dict[str, Any]) -> set[str]:
        requested = {
            item.split("/")[-1]
            for item in spec["source_layer"]["tables_or_resources"]
            if item.split("/")[-1] in FHIR_EVENT_RESOURCES
        }
        if requested:
            return requested
        source_type = spec["source_layer"]["source_type"]
        inferred = {
            "order": {"MedicationRequest"},
            "administration": {"MedicationAdministration"},
            "dispense": {"MedicationDispense"},
            "reconciliation": {"MedicationRequest", "MedicationAdministration"},
            "mixed": set(FHIR_EVENT_RESOURCES),
        }
        return inferred.get(source_type, set())

    @classmethod
    def _iter_resources(cls, files: Iterable[Path]) -> Iterable[dict[str, Any]]:
        for path in files:
            with cls._open_text(path) as handle:
                for line in handle:
                    if line.strip():
                        value = json.loads(line)
                        if isinstance(value, dict):
                            yield value

    @staticmethod
    def _dosage_blocks(resource: dict[str, Any]) -> list[dict[str, Any]]:
        dosage = resource.get("dosage")
        if isinstance(dosage, dict):
            return [dosage]
        instructions = resource.get("dosageInstruction")
        if isinstance(instructions, list):
            return [item for item in instructions if isinstance(item, dict)]
        return []

    @classmethod
    def _discover_fields(cls, files: list[Path], selected: set[str]) -> set[str]:
        found: set[str] = set()
        for resource in cls._iter_resources(cls._selected_event_files(files, selected)):
            if str(resource.get("resourceType", "")) not in selected:
                continue
            if str(resource.get("status", "")).strip():
                found.add("status")
            if any(
                resource.get(field)
                for field in (
                    "authoredOn",
                    "effectiveDateTime",
                    "effectivePeriod",
                    "whenPrepared",
                    "whenHandedOver",
                )
            ):
                found.add("event_time")
            if resource.get("subject"):
                found.add("subject")
            if resource.get("encounter") or resource.get("context"):
                found.add("encounter")
            for dosage in cls._dosage_blocks(resource):
                if dosage.get("route"):
                    found.add("route")
                dose = dosage.get("dose")
                if dose or dosage.get("doseAndRate"):
                    found.add("dose")
                if isinstance(dose, dict) and (dose.get("unit") or dose.get("code")):
                    found.add("unit")
                for dose_rate in dosage.get("doseAndRate", []):
                    quantity = dose_rate.get("doseQuantity", {})
                    if quantity.get("unit") or quantity.get("code"):
                        found.add("unit")
                if dosage.get("timing"):
                    found.add("frequency")
        if files:
            found.update({"medication_class", "ingredient"})
        return found

    def inspect_source(self, spec, data_root):
        files = self._files(data_root)
        resources = self._resource_types(files)
        required_resources = self._event_resources(spec)
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
        matched = model_version in {
            "2.1",
            "2.1.0",
            "2.1.0-demo-matched",
            "demo-matched",
        }
        if not matched:
            reasons.append(
                "FHIR execution is version-gated to MIMIC-IV-on-FHIR 2.1/2.1.0 "
                "or an explicitly matched demo."
            )
        fields = self._discover_fields(files, required_resources) if files else set()
        return (
            fields,
            {
                "data_available": data_available,
                "execution_path_available": data_available and matched,
                "resource_types": sorted(resources),
                "matched_version_gate": matched,
                "evaluation_level": (
                    "matched_demo_execution"
                    if data_available and "demo" in model_version
                    else "matched_execution"
                    if data_available and matched
                    else "adapter_or_synthetic_only"
                ),
            },
            reasons,
        )

    def compile(self, spec, data_root):
        resources = sorted(self._event_resources(spec))
        return QueryPlan(
            operator_id=spec["operator_id"],
            operator_version=spec["operator_version"],
            adapter=self.name,
            adapter_version=self.version,
            data_model_version=spec["data_model"]["model_version"],
            sources=spec["source_layer"]["tables_or_resources"],
            analysis_unit=spec["analysis_unit"],
            predicates=[
                "resourceType-specific literal status",
                "frozen medication CodeableConcept/reference mapping",
                "encounter/time window retained in trace",
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
                "unmapped or ambiguous code -> unresolved",
                "required missing element -> configured missing policy",
            ],
            output_profile=spec["output_specification"]["profile"],
            aggregate_only=True,
            implementation={
                "resources": resources,
                "version_gate": (
                    "MIMIC-IV-on-FHIR 2.1/2.1.0 requires native MIMIC-IV 2.2 "
                    "for exact parity"
                ),
            },
        )

    @staticmethod
    def _synthetic_class(resource: dict[str, Any]) -> str | None:
        meta = resource.get("meta", {})
        for tag in meta.get("tag", []) if isinstance(meta, dict) else []:
            if tag.get("system") == "https://medprov.org/class":
                return tag.get("code")
        value = resource.get("medprovMedicationClass")
        return str(value) if value else None

    @staticmethod
    def _coding_values(codeable: object) -> list[str]:
        if not isinstance(codeable, dict):
            return []
        values: list[str] = []
        text = codeable.get("text")
        if text:
            values.append(str(text))
        for coding in codeable.get("coding", []):
            if not isinstance(coding, dict):
                continue
            values.extend(str(coding[key]) for key in ("code", "display") if coding.get(key))
        return values

    @classmethod
    def _medication_maps(
        cls, files: list[Path], rules: list[NameRule]
    ) -> tuple[dict[str, tuple[str | None, str]], dict[tuple[str, str], set[str]]]:
        by_reference: dict[str, tuple[str | None, str]] = {}
        by_code: dict[tuple[str, str], set[str]] = {}
        for resource in cls._iter_resources(files):
            if resource.get("resourceType") != "Medication":
                continue
            values = cls._coding_values(resource.get("code"))
            identifiers = resource.get("identifier", [])
            for identifier in identifiers if isinstance(identifiers, list) else []:
                if isinstance(identifier, dict) and identifier.get("value"):
                    values.append(str(identifier["value"]))
            medication_class, state = classify_strings(values, rules)
            resource_id = str(resource.get("id", ""))
            if resource_id:
                by_reference[resource_id] = (medication_class, state)
            if medication_class is None:
                continue
            for identifier in identifiers if isinstance(identifiers, list) else []:
                if not isinstance(identifier, dict):
                    continue
                system = str(identifier.get("system", ""))
                value = str(identifier.get("value", ""))
                if value:
                    by_code.setdefault((system, value), set()).add(medication_class)
                    by_code.setdefault(("", value), set()).add(medication_class)
        return by_reference, by_code

    @classmethod
    def _resource_class(
        cls,
        resource: dict[str, Any],
        rules: list[NameRule],
        by_reference: dict[str, tuple[str | None, str]],
        by_code: dict[tuple[str, str], set[str]],
    ) -> tuple[str | None, str]:
        synthetic = cls._synthetic_class(resource)
        if synthetic:
            return synthetic, "resolved"
        medication_reference = resource.get("medicationReference", {})
        if isinstance(medication_reference, dict):
            reference = str(medication_reference.get("reference", ""))
            if reference:
                value = by_reference.get(reference.split("/")[-1])
                if value is not None:
                    return value
        codeable = resource.get("medicationCodeableConcept")
        direct_class, direct_state = classify_strings(cls._coding_values(codeable), rules)
        if direct_class is not None or direct_state == "ambiguous":
            return direct_class, direct_state
        resolved: set[str] = set()
        if isinstance(codeable, dict):
            for coding in codeable.get("coding", []):
                if not isinstance(coding, dict):
                    continue
                system = str(coding.get("system", ""))
                code = str(coding.get("code", ""))
                resolved.update(by_code.get((system, code), set()))
                resolved.update(by_code.get(("", code), set()))
        if len(resolved) == 1:
            return next(iter(resolved)), "resolved"
        if len(resolved) > 1:
            return None, "ambiguous"
        return None, "unmapped"

    @classmethod
    def _has_required(cls, resource: dict[str, Any], logical: str) -> bool:
        if logical == "status":
            return bool(str(resource.get("status", "")).strip())
        dosage_blocks = cls._dosage_blocks(resource)
        if logical == "route":
            return any(block.get("route") for block in dosage_blocks)
        if logical == "dose":
            return any(block.get("dose") or block.get("doseAndRate") for block in dosage_blocks)
        if logical == "unit":
            for block in dosage_blocks:
                dose = block.get("dose", {})
                if isinstance(dose, dict) and (dose.get("unit") or dose.get("code")):
                    return True
                for item in block.get("doseAndRate", []):
                    quantity = item.get("doseQuantity", {})
                    if quantity.get("unit") or quantity.get("code"):
                        return True
            return False
        if logical == "frequency":
            return any(block.get("timing") for block in dosage_blocks)
        return False

    @staticmethod
    def _native_unit_id(resource: dict[str, Any]) -> str:
        """Return a retained native unit ID when the profile carries one."""

        resource_type = str(resource.get("resourceType", ""))
        suffix = {
            "MedicationRequest": "/medication-request-phid",
            "MedicationDispense": "/medication-dispense",
        }.get(resource_type)
        if suffix:
            identifiers = resource.get("identifier", [])
            for identifier in identifiers if isinstance(identifiers, list) else []:
                if not isinstance(identifier, dict):
                    continue
                if str(identifier.get("system", "")).endswith(suffix):
                    value = str(identifier.get("value", "")).strip()
                    if value:
                        return value
        return str(resource.get("id", "")).strip()

    def execute(self, spec, data_root):
        capability = self.capability(spec, data_root)
        provenance = {
            "spec_sha256": canonical_json_sha256(spec),
            "adapter_version": self.version,
            "executed_at_utc": utc_now(),
            "aggregate_only": True,
            "matched_version_gate": capability.source_status.get("matched_version_gate"),
            "evaluation_level": capability.source_status.get("evaluation_level"),
        }
        empty: dict[str, Any] = {
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
                (
                    "not_executed_data_unavailable"
                    if not capability.source_status.get("data_available")
                    else "not_executed_version_mismatch"
                ),
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
        files = self._files(data_root)
        rules = load_name_rules(spec)
        by_reference, by_code = self._medication_maps(files, rules)
        selected = self._event_resources(spec)
        classes = set(spec["identity_rule"]["class_filter"])
        positive = {str(item).strip().lower() for item in spec["event_semantics_map"]["positive"]}
        negative = {str(item).strip().lower() for item in spec["event_semantics_map"]["negative"]}
        excluded = {str(item).strip().lower() for item in spec["event_semantics_map"]["excluded"]}
        required = self.required_metadata_fields(spec)
        counts: dict[str, Any] = dict(empty)
        identity_unmapped = 0
        identity_ambiguous = 0
        excluded_semantics = 0
        units: dict[tuple[str, str, str], str] = {}
        state_rank = {"unmeasurable": 0, "unresolved": 1, "unexposed": 2, "exposed": 3}
        for resource in self._iter_resources(self._selected_event_files(files, selected)):
            resource_type = str(resource.get("resourceType", ""))
            if resource_type not in selected:
                continue
            medication_class, identity_state = self._resource_class(
                resource, rules, by_reference, by_code
            )
            if medication_class is None:
                if identity_state == "ambiguous":
                    identity_ambiguous += 1
                    counts["unresolved"] += 1
                else:
                    identity_unmapped += 1
                continue
            if medication_class not in classes:
                continue
            missing = [logical for logical in required if not self._has_required(resource, logical)]
            status = str(resource.get("status", "")).strip().lower() or "<blank>"
            if missing:
                state = "unmeasurable"
            elif status in positive:
                state = "exposed"
            elif status in negative:
                state = "unexposed"
            else:
                state = "unresolved"
                if status in excluded:
                    excluded_semantics += 1
            unit_key = (resource_type, self._native_unit_id(resource), medication_class)
            previous = units.get(unit_key)
            if previous is None or state_rank[state] > state_rank[previous]:
                units[unit_key] = state
        by_resource: dict[str, dict[str, int]] = {}
        by_class_counts: dict[str, dict[str, int]] = {}
        for (resource_type, _unit_id, medication_class), state in units.items():
            counts[state] += 1
            resource_bucket = by_resource.setdefault(
                resource_type,
                {key: 0 for key in ("exposed", "unexposed", "unresolved", "unmeasurable")},
            )
            resource_bucket[state] += 1
            class_bucket = by_class_counts.setdefault(
                medication_class,
                {key: 0 for key in ("exposed", "unexposed", "unresolved", "unmeasurable")},
            )
            class_bucket[state] += 1
        counts["analysis_units"] = sum(
            int(counts[key]) for key in ("exposed", "unexposed", "unresolved", "unmeasurable")
        )
        counts["by_resource"] = [
            {"resource": key, **value} for key, value in sorted(by_resource.items())
        ]
        counts["by_class"] = [
            {"medication_class": key, **value}
            for key, value in sorted(by_class_counts.items())
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
            {
                "identity_unmapped_records": identity_unmapped,
                "identity_ambiguous_records": identity_ambiguous,
                "excluded_semantics_records": excluded_semantics,
            },
            {},
            provenance,
            [],
        )
