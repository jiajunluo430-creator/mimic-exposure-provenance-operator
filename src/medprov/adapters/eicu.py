"""eICU adapter with explicit non-equivalence and native-key boundaries."""

from __future__ import annotations

import zipfile
from pathlib import Path

from medprov.models import CapabilityResult, ExecutionResult, QueryPlan
from medprov.utils import canonical_json_sha256, utc_now

from .base import BaseAdapter


class EicuAdapter(BaseAdapter):
    name = "eicu"
    version = "0.1.0"
    supported_models = ("eICU-CRD", "eICU")

    @staticmethod
    def _members(data_root: str | Path | None) -> list[str]:
        if not data_root:
            return []
        path = Path(data_root)
        if path.is_file() and path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                return archive.namelist()
        if path.is_dir():
            return [str(item.relative_to(path)).replace("\\", "/") for item in path.rglob("*.csv*")]
        return []

    def inspect_source(self, spec, data_root):
        members = self._members(data_root)
        basenames = {Path(item).name.lower() for item in members}
        source_type = spec["source_layer"]["source_type"]
        required_names = (
            {"medication.csv.gz"} if source_type == "order" else {"infusiondrug.csv.gz"}
        )
        if source_type in {"reconciliation", "mixed"}:
            required_names = {"medication.csv.gz", "infusiondrug.csv.gz"}
        present = {
            name
            for name in required_names
            if name in basenames or name.replace(".gz", "") in basenames
        }
        available = bool(members) and present == required_names
        fields = set()
        if "medication.csv.gz" in present:
            fields.update(
                {
                    "patientunitstayid",
                    "drugname",
                    "dosage",
                    "routeadmin",
                    "frequency",
                    "drugstartoffset",
                    "drugstopoffset",
                }
            )
        if "infusiondrug.csv.gz" in present:
            fields.update(
                {
                    "patientunitstayid",
                    "drugname",
                    "infusionrate",
                    "drugamount",
                    "volumeoffluid",
                    "infusionoffset",
                }
            )
        reasons = []
        if not members:
            reasons.append("eICU ZIP or extracted source directory is unavailable.")
        if present != required_names:
            reasons.append(
                "Required eICU source files are missing: "
                + ", ".join(sorted(required_names - present))
            )
        exact_key_requested = spec["identity_rule"][
            "match_mode"
        ] == "exact_native_key" and source_type in {"reconciliation", "mixed"}
        if exact_key_requested:
            reasons.append(
                "eICU has no native medication-to-infusion cross-source identifier for exact reconciliation."
            )
        return (
            fields,
            {
                "data_available": available,
                "execution_path_available": available and not exact_key_requested,
                "zip_members_n": len(members),
                "source_files_present": sorted(present),
                "native_cross_source_key": False,
                "evaluation_level": "same_class_window_capability"
                if available
                else "not_evaluated",
            },
            reasons,
        )

    def capability(self, spec, data_root):
        result = super().capability(spec, data_root)
        exact = spec["identity_rule"]["match_mode"] == "exact_native_key" and spec["source_layer"][
            "source_type"
        ] in {"reconciliation", "mixed"}
        if not exact:
            return result
        dimensions = dict(result.dimension_status)
        dimensions["identity_rule"] = "unsupported_exact_cross_source_identity"
        return CapabilityResult(
            adapter=result.adapter,
            adapter_version=result.adapter_version,
            supported=False,
            measurable=False,
            executable=False,
            dimension_status=dimensions,
            required_fields=result.required_fields,
            available_fields=result.available_fields,
            missing_fields=result.missing_fields,
            source_status=result.source_status,
            reasons=result.reasons,
        )

    def compile(self, spec, data_root):
        role = spec["source_layer"]["source_type"]
        predicates = ["frozen six-class label mapping", "valid offset"]
        if role in {"administration", "reconciliation", "mixed"}:
            predicates.extend(["drug-specific infusion label", "positive numeric rate/value"])
        return QueryPlan(
            operator_id=spec["operator_id"],
            operator_version=spec["operator_version"],
            adapter=self.name,
            adapter_version=self.version,
            data_model_version=spec["data_model"]["model_version"],
            sources=spec["source_layer"]["tables_or_resources"],
            analysis_unit=spec["analysis_unit"],
            predicates=predicates,
            joins=[{"left": "source rows", "right": "patient", "keys": ["patientunitstayid"]}],
            deduplication_unit=spec["identity_rule"]["deduplication_unit"],
            time_rule=spec["time_origin_window"]["window_rule"],
            metadata_gates=self.required_metadata_fields(spec),
            unresolved_rules=[
                "no cross-source key -> same-class/window only",
                "treatment rows -> documentation only",
            ],
            output_profile=spec["output_specification"]["profile"],
            aggregate_only=True,
            implementation={"streaming_zip": True, "native_cross_source_key": False},
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
        empty = {
            "analysis_units": 0,
            "exposed": 0,
            "unexposed": 0,
            "unresolved": 0,
            "unmeasurable": 0,
        }
        if not capability.executable:
            status = (
                "unmeasurable"
                if capability.source_status.get("data_available")
                else "not_executed_data_unavailable"
            )
            return ExecutionResult(
                spec["operator_id"],
                spec["operator_version"],
                self.name,
                status,
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
        return ExecutionResult(
            spec["operator_id"],
            spec["operator_version"],
            self.name,
            "capability_confirmed_execution_pending_phase6",
            True,
            True,
            True,
            False,
            True,
            empty,
            {"interpretation": "Source-capability result only; not external clinical validation."},
            {"real_streaming_reconciliation_not_yet_run": 1},
            provenance,
            [
                "Real eICU aggregate execution is deferred to the prespecified Phase 6 adapter evaluation."
            ],
        )
