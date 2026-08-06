"""OMOP CDM DRUG_EXPOSURE adapter and semantic-loss smoke test."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from medprov.identity import classify_strings, load_name_rules
from medprov.models import ExecutionResult, QueryPlan
from medprov.utils import canonical_json_sha256, utc_now

from .base import BaseAdapter


class OmopAdapter(BaseAdapter):
    name = "omop"
    version = "0.1.0"
    supported_models = ("OMOP CDM", "OMOP")
    field_aliases = {
        **BaseAdapter.field_aliases,
        "status": ("medprov_event_state", "event_state", "status"),
    }

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

    @staticmethod
    def _concept_names(source: Path) -> dict[str, str]:
        names: dict[str, str] = {}
        for filename in ("2b_concept.csv", "concept.csv", "CONCEPT.csv"):
            candidate = source.parent / filename
            if not candidate.is_file():
                continue
            with candidate.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    concept_id = str(row.get("concept_id", "")).strip()
                    concept_name = str(row.get("concept_name", "")).strip()
                    if concept_id and concept_name:
                        names[concept_id] = concept_name
            break
        return names

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
        source = self._drug_exposure(data_root)
        semantic_ablation = bool(
            source is not None
            and capability.supported
            and set(capability.missing_fields) == {"status"}
            and str(spec["target_event"])
            in {"administration", "documented_administration"}
        )
        if not capability.executable and not semantic_ablation:
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
        assert source is not None
        classes = set(spec["identity_rule"]["class_filter"])
        ingredients = {
            str(item).lower() for item in spec["identity_rule"].get("ingredient_filter", [])
        }
        rules = load_name_rules(spec)
        if ingredients:
            rules = [rule for rule in rules if rule.ingredient.lower() in ingredients]
        concept_names = self._concept_names(source)
        required = self.required_metadata_fields(spec)
        positive = {
            str(item).strip().lower() for item in spec["event_semantics_map"]["positive"]
        }
        negative = {
            str(item).strip().lower() for item in spec["event_semantics_map"]["negative"]
        }
        event_state_required = (
            "status" in required
            or str(spec["target_event"]) in {"administration", "documented_administration"}
        )
        state_rank = {"unmeasurable": 0, "unresolved": 1, "unexposed": 2, "exposed": 3}
        units: dict[tuple[str, str, str], str] = {}
        matched_source_rows = 0
        event_state_available_rows = 0
        identity_unmapped_rows = 0
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                med_class = row.get("medprov_class", "")
                if med_class not in classes or ingredients:
                    med_class, identity_state = classify_strings(
                        [
                            row.get("drug_source_value", ""),
                            concept_names.get(str(row.get("drug_concept_id", "")), ""),
                            concept_names.get(
                                str(row.get("drug_source_concept_id", "")), ""
                            ),
                        ],
                        rules,
                    )
                    if med_class is None or identity_state != "resolved":
                        identity_unmapped_rows += 1
                        continue
                if med_class not in classes:
                    continue
                matched_source_rows += 1
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
                literal = str(row.get("medprov_event_state", "")).strip().lower()
                if literal:
                    event_state_available_rows += 1
                if missing or (event_state_required and not literal):
                    state = "unmeasurable"
                elif event_state_required:
                    if literal in positive:
                        state = "exposed"
                    elif literal in negative:
                        state = "unexposed"
                    else:
                        state = "unresolved"
                else:
                    state = "exposed"
                unit_key = (
                    str(row.get("person_id", "")).strip(),
                    str(row.get("visit_occurrence_id", "")).strip(),
                    str(med_class),
                )
                if not unit_key[0] or not unit_key[1]:
                    unit_key = (
                        str(row.get("drug_exposure_id", "")).strip(),
                        "missing_visit",
                        str(med_class),
                    )
                previous = units.get(unit_key)
                if previous is None or state_rank[state] > state_rank[previous]:
                    units[unit_key] = state
        for state in units.values():
            counts[state] += 1
        counts["analysis_units"] = sum(
            counts[key] for key in ("exposed", "unexposed", "unresolved", "unmeasurable")
        )
        result_status = "unmeasurable" if semantic_ablation else "executed"
        return ExecutionResult(
            spec["operator_id"],
            spec["operator_version"],
            self.name,
            result_status,
            True,
            capability.supported,
            capability.measurable,
            not semantic_ablation,
            True,
            counts,
            {
                "interpretation": "OMOP capability/smoke test; not clinical external validation",
                "matched_source_rows": matched_source_rows,
                "analysis_unit": "person_id x visit_occurrence_id x medication_class",
                "event_state_available_rows": event_state_available_rows,
                "identity_unmapped_rows": identity_unmapped_rows,
                "concept_dictionary_available": bool(concept_names),
            },
            ({reason: 1 for reason in capability.reasons} if semantic_ablation else {}),
            provenance,
            capability.reasons if semantic_ablation else [],
        )
