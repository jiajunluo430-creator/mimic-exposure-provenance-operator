"""MIMIC-IV native reference adapter.

The first public implementation executes against the materialized, read-only
DuckDB reference cache produced by the frozen pipeline. Raw CSV sources remain
the authoritative inputs; using the cache avoids repeating the previously
audited multi-hour scans and lets parity failures be localized deterministically.
"""

from __future__ import annotations

import csv
import gzip
import os
from pathlib import Path
from typing import Any, TextIO

import duckdb

from medprov.identity import classify_strings, load_name_rules
from medprov.models import ExecutionResult, QueryPlan
from medprov.utils import canonical_json_sha256, utc_now

from .base import BaseAdapter


class MimicNativeAdapter(BaseAdapter):
    name = "mimic_native"
    version = "0.1.0"
    supported_models = ("MIMIC-IV native", "MIMIC-IV")

    _PRE_DB = "jamia_pre_submission_v1_0.duckdb"
    _UPGRADE_DB = "jamia_prereview_upgrade_v1_0.duckdb"
    _BASE_DB = "n1_validity.duckdb"

    @staticmethod
    def _is_raw_demo(spec: dict[str, Any]) -> bool:
        version = str(spec["data_model"]["model_version"]).lower()
        return "demo" in version and "2.2" in version

    @staticmethod
    def _find_raw_file(data_root: str | Path | None, basename: str) -> Path | None:
        if not data_root:
            return None
        root = Path(data_root)
        if root.is_file() and root.name.lower() == basename.lower():
            return root.resolve()
        if not root.is_dir():
            return None
        matches = sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.name.lower() == basename.lower()
        )
        return matches[0].resolve() if matches else None

    @staticmethod
    def _open_csv_text(path: Path) -> TextIO:
        if path.name.lower().endswith(".gz"):
            return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
        return path.open("r", encoding="utf-8-sig", newline="")

    @classmethod
    def _raw_demo_sources(
        cls, spec: dict[str, Any], data_root: str | Path | None
    ) -> dict[str, Path]:
        sources: dict[str, Path] = {}
        for item in spec["source_layer"]["tables_or_resources"]:
            name = item.split("/")[-1]
            if not name.lower().endswith((".csv", ".csv.gz")):
                name += ".csv.gz"
            path = cls._find_raw_file(data_root, name)
            if path is not None:
                sources[item] = path
        return sources

    @classmethod
    def _reference_for_spec(cls, spec: dict[str, Any]) -> tuple[str, str]:
        construct = str(spec["clinical_construct"])
        if construct == "a2_ppi_hospital_overlap_order_exposure":
            return cls._UPGRADE_DB, "a2_upgrade_input"
        if spec["output_specification"]["profile"] == "six_class_conversion":
            table = (
                "post_orders"
                if spec["identity_rule"]["match_mode"] == "exact_native_key"
                else "relaxed_order_conversion"
            )
            return cls._PRE_DB, table
        return cls._PRE_DB, "a1_operator_post" if construct.startswith(
            "a1_"
        ) else "a2_operator_post"

    @staticmethod
    def _candidate_roots(data_root: str | Path | None) -> list[Path]:
        roots: list[Path] = []
        if data_root:
            roots.append(Path(data_root))
        if os.environ.get("MEDPROV_MIMIC_CACHE"):
            roots.append(Path(os.environ["MEDPROV_MIMIC_CACHE"]))
        return roots

    @classmethod
    def _find_database(cls, data_root: str | Path | None, filename: str) -> Path | None:
        for root in cls._candidate_roots(data_root):
            candidates = [
                root if root.is_file() and root.name == filename else root / filename,
                root / "cache" / filename,
                root.parent / "cache" / filename,
            ]
            for candidate in candidates:
                if candidate.is_file():
                    return candidate.resolve()
        return None

    @staticmethod
    def _table_columns(connection: duckdb.DuckDBPyConnection, table: str) -> set[str]:
        return {str(row[0]) for row in connection.execute(f"DESCRIBE {table}").fetchall()}

    @staticmethod
    def _tables(connection: duckdb.DuckDBPyConnection) -> set[str]:
        return {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}

    def inspect_source(
        self, spec: dict[str, Any], data_root: str | Path | None
    ) -> tuple[set[str], dict[str, Any], list[str]]:
        if self._is_raw_demo(spec):
            sources = self._raw_demo_sources(spec, data_root)
            requested = list(spec["source_layer"]["tables_or_resources"])
            raw_fields: set[str] = set()
            for path in sources.values():
                with self._open_csv_text(path) as handle:
                    raw_fields.update(next(csv.reader(handle)))
            complete = len(sources) == len(requested)
            raw_reasons = []
            if not complete:
                missing = sorted(set(requested) - set(sources))
                raw_reasons.append(
                    "Matched native demo source files are missing: " + ", ".join(missing)
                )
            return (
                raw_fields,
                {
                    "data_available": complete,
                    "execution_path_available": complete,
                    "evaluation_level": "matched_demo_execution",
                    "raw_csv_execution": "streaming",
                    "source_files": {key: value.name for key, value in sorted(sources.items())},
                },
                raw_reasons,
            )
        pre_db = self._find_database(data_root, self._PRE_DB)
        upgrade_db = self._find_database(data_root, self._UPGRADE_DB)
        base_db = self._find_database(data_root, self._BASE_DB)
        reference_filename, selected_table = self._reference_for_spec(spec)
        selected_db = pre_db if reference_filename == self._PRE_DB else upgrade_db
        reasons: list[str] = []
        status: dict[str, Any] = {
            "data_available": bool(selected_db or base_db),
            "execution_path_available": bool(selected_db),
            "materialized_reference_database": selected_db.name if selected_db else None,
            "materialized_reference_table": selected_table,
            "base_reference_database": base_db.name if base_db else None,
            "raw_csv_execution": "compile_only",
        }
        fields: set[str] = set()
        if selected_db:
            with duckdb.connect(str(selected_db), read_only=True) as connection:
                tables = self._tables(connection)
                status["materialized_tables"] = sorted(tables)
                if selected_table in tables:
                    fields.update(self._table_columns(connection, selected_table))
                else:
                    reasons.append(
                        f"Required materialized reference table is absent: {selected_table}"
                    )
                    status["execution_path_available"] = False
        # These logical metadata gates were applied upstream before the frozen
        # aggregate anchor table was materialized.  Preserve that distinction
        # rather than requiring raw columns to remain in the anchor table.
        if spec["output_specification"]["profile"] == "anchor_exposure":
            fields.add("status")
            if spec["target_event"] == "order" and str(spec["clinical_construct"]).startswith(
                "a1_"
            ):
                fields.update({"route", "dose", "unit"})
                status["materialized_metadata_contract"] = [
                    "subcutaneous-compatible route",
                    "frozen prophylactic-dose rule",
                ]
        target = spec["target_event"]
        if base_db and target in {"documented_administration", "reconciliation"}:
            with duckdb.connect(str(base_db), read_only=True) as connection:
                tables = self._tables(connection)
                if "decision_events_scoped" in tables:
                    event_fields = self._table_columns(connection, "decision_events_scoped")
                    fields.update(event_fields)
        required = self.required_metadata_fields(spec)
        if "route" in required and target in {"documented_administration", "reconciliation"}:
            route_row: tuple[Any, ...] | None = None
            if (
                str(spec["clinical_construct"])
                == "a1_vte_prophylaxis_administration_exposure_route_required"
                and upgrade_db
            ):
                with duckdb.connect(str(upgrade_db), read_only=True) as connection:
                    fields.update(self._table_columns(connection, "a1_given_events"))
                    route_row = connection.execute(
                        "SELECT count(*), count(route) FROM a1_given_events"
                    ).fetchone()
                status["required_route_reference"] = "a1_given_events"
            elif base_db:
                class_filter = spec["identity_rule"]["class_filter"]
                with duckdb.connect(str(base_db), read_only=True) as connection:
                    if "decision_events_scoped" in self._tables(connection):
                        placeholders = ",".join("?" for _ in class_filter)
                        query = (
                            "SELECT count(*) AS n, "
                            "sum(CASE WHEN route IS NOT NULL AND trim(route) <> '' THEN 1 ELSE 0 END) AS route_n "
                            "FROM decision_events_scoped WHERE drug_class IN ("
                            + placeholders
                            + ") "
                            "AND event_category = 'given_strict'"
                        )
                        route_row = connection.execute(query, class_filter).fetchone()
                    status["required_route_reference"] = "decision_events_scoped"
            if route_row is None:
                raise RuntimeError("Route capability query returned no aggregate row")
            n, route_n = route_row
            status["required_route_population_n"] = int(n or 0)
            status["required_route_nonmissing_n"] = int(route_n or 0)
            if int(n or 0) > 0 and int(route_n or 0) == 0:
                fields.discard("route")
                reasons.append(
                    "Route column exists but is 0% populated among qualifying documented administrations."
                )
        if not selected_db:
            reasons.append(
                "Materialized MIMIC reference database not found; native CSV compilation is available but execution is not enabled."
            )
        return fields, status, reasons

    def _conversion_sql(self, spec: dict[str, Any]) -> tuple[str, str]:
        match_mode = spec["identity_rule"]["match_mode"]
        class_filter = spec["identity_rule"]["class_filter"]
        quoted = ", ".join("'" + item.replace("'", "''") + "'" for item in class_filter)
        if match_mode == "exact_native_key":
            table, flag = "post_orders", "converted"
        elif match_mode == "same_class_window":
            table, flag = "relaxed_order_conversion", "relaxed_converted"
        else:
            raise ValueError(f"Unsupported six-class MIMIC match mode: {match_mode}")
        sql = f"""
            SELECT drug_class,
                   count(*)::BIGINT AS eligible_n,
                   sum(CASE WHEN {flag} THEN 1 ELSE 0 END)::BIGINT AS exposed_n,
                   sum(CASE WHEN NOT {flag} THEN 1 ELSE 0 END)::BIGINT AS unexposed_n
            FROM {table}
            WHERE drug_class IN ({quoted})
            GROUP BY drug_class
            ORDER BY drug_class
        """.strip()
        return table, sql

    def _anchor_sql(self, spec: dict[str, Any]) -> tuple[str, str, str]:
        construct = spec["clinical_construct"]
        database, table = self._reference_for_spec(spec)
        target = spec["target_event"]
        match_mode = spec["identity_rule"]["match_mode"]
        if target == "order":
            exposure = (
                "hospital_order_exposure"
                if construct == "a2_ppi_hospital_overlap_order_exposure"
                else "order_exposure"
            )
        elif target == "documented_administration":
            exposure = "admin_strict" if match_mode == "exact_native_key" else "admin_broad"
        else:
            raise ValueError(f"Unsupported anchor target event: {target}")
        sql = f"""
            SELECT count(*)::BIGINT AS analysis_units_n,
                   sum(CASE WHEN {exposure}=1 THEN 1 ELSE 0 END)::BIGINT AS exposed_n,
                   sum(CASE WHEN {exposure}=0 THEN 1 ELSE 0 END)::BIGINT AS unexposed_n,
                   sum(CASE WHEN {exposure} IS NULL THEN 1 ELSE 0 END)::BIGINT AS unresolved_n
            FROM {table}
        """.strip()
        return database, table, sql

    def compile(self, spec: dict[str, Any], data_root: str | Path | None) -> QueryPlan:
        if self._is_raw_demo(spec):
            return QueryPlan(
                operator_id=spec["operator_id"],
                operator_version=spec["operator_version"],
                adapter=self.name,
                adapter_version=self.version,
                data_model_version=spec["data_model"]["model_version"],
                sources=list(spec["source_layer"]["tables_or_resources"]),
                analysis_unit=spec["analysis_unit"],
                predicates=[
                    "frozen strict medication-name mapping",
                    "literal source event semantics",
                    "matched MIMIC-IV demo v2.2",
                ],
                joins=[],
                deduplication_unit=list(spec["identity_rule"]["deduplication_unit"]),
                time_rule=spec["time_origin_window"]["window_rule"],
                metadata_gates=self.required_metadata_fields(spec),
                unresolved_rules=[
                    "ambiguous medication class -> unresolved",
                    "required missing source field -> unmeasurable",
                ],
                output_profile=spec["output_specification"]["profile"],
                aggregate_only=True,
                implementation={"raw_csv_execution": "streaming", "version_matched": True},
            )
        profile = spec["output_specification"]["profile"]
        if profile == "six_class_conversion":
            table, sql = self._conversion_sql(spec)
            database = self._PRE_DB
        elif profile == "anchor_exposure":
            database, table, sql = self._anchor_sql(spec)
        else:
            database, table, sql = (
                self._PRE_DB,
                "canonical_event_stream",
                "adapter-defined canonical classification",
            )
        metadata_gates = [
            f"{field}={value}"
            for field, value in spec["required_metadata"].items()
            if field in {"route", "dose", "unit", "frequency", "status"} and value == "required"
        ]
        return QueryPlan(
            operator_id=spec["operator_id"],
            operator_version=spec["operator_version"],
            adapter=self.name,
            adapter_version=self.version,
            data_model_version=spec["data_model"]["model_version"],
            sources=list(spec["source_layer"]["tables_or_resources"]),
            analysis_unit=spec["analysis_unit"],
            predicates=[
                f"match_mode={spec['identity_rule']['match_mode']}",
                f"observability_gate={spec['source_layer']['observability_gate']['rule']}",
                "literal event states evaluated before collapse",
            ],
            joins=[
                {
                    "left": "order unit",
                    "right": "administration event",
                    "keys": spec["identity_rule"]["native_keys"],
                }
            ],
            deduplication_unit=list(spec["identity_rule"]["deduplication_unit"]),
            time_rule=spec["time_origin_window"]["window_rule"],
            metadata_gates=metadata_gates,
            unresolved_rules=[
                f"observability failure -> {spec['source_layer']['observability_gate']['failure_state']}",
                f"missing required metadata -> {spec['required_metadata']['missing_policy']}",
            ],
            output_profile=profile,
            aggregate_only=True,
            implementation={"database": database, "materialized_table": table, "sql": sql},
        )

    def _execute_raw_demo(
        self,
        spec: dict[str, Any],
        data_root: str | Path | None,
        capability: Any,
        provenance: dict[str, Any],
    ) -> ExecutionResult:
        empty: dict[str, Any] = {
            "analysis_units": 0,
            "exposed": 0,
            "unexposed": 0,
            "unresolved": 0,
            "unmeasurable": 0,
        }
        if not capability.executable:
            return ExecutionResult(
                operator_id=spec["operator_id"],
                operator_version=spec["operator_version"],
                adapter=self.name,
                status="not_executed_data_unavailable",
                syntactically_valid=True,
                adapter_supported=capability.supported,
                measurable=capability.measurable,
                executable=False,
                aggregate_only=True,
                counts=empty,
                metrics={},
                failure_reasons={reason: 1 for reason in capability.reasons},
                provenance=provenance,
                warnings=capability.reasons,
            )
        rules = load_name_rules(spec)
        positive = {
            str(item).strip().lower() for item in spec["event_semantics_map"]["positive"]
        }
        negative = {
            str(item).strip().lower() for item in spec["event_semantics_map"]["negative"]
        }
        excluded = {
            str(item).strip().lower() for item in spec["event_semantics_map"]["excluded"]
        }
        required = self.required_metadata_fields(spec)
        target = str(spec["target_event"])
        sources = self._raw_demo_sources(spec, data_root)
        name_fields = {
            "prescriptions.csv.gz": "drug",
            "pharmacy.csv.gz": "medication",
            "emar.csv.gz": "medication",
        }
        key_fields = {
            "prescriptions.csv.gz": "pharmacy_id",
            "pharmacy.csv.gz": "pharmacy_id",
            "emar.csv.gz": "emar_id",
        }
        aliases = {
            "route": ("route",),
            "dose": ("dose_val_rx", "dose_given"),
            "unit": ("dose_unit_rx", "dose_given_unit"),
            "frequency": ("frequency", "doses_per_24_hrs"),
            "status": ("event_txt", "status"),
        }
        by_source: dict[str, dict[str, int]] = {}
        by_class: dict[str, dict[str, int]] = {}
        seen: set[tuple[str, str, str]] = set()
        identity_unmapped = 0
        identity_ambiguous = 0
        excluded_semantics = 0
        counts = dict(empty)
        for source_name, path in sorted(sources.items()):
            basename = path.name.lower()
            name_field = name_fields.get(basename)
            key_field = key_fields.get(basename)
            if name_field is None or key_field is None:
                continue
            with self._open_csv_text(path) as handle:
                for row_number, row in enumerate(csv.DictReader(handle), start=1):
                    medication_class, identity_state = classify_strings(
                        [row.get(name_field, "")], rules
                    )
                    if medication_class is None:
                        if identity_state == "ambiguous":
                            identity_ambiguous += 1
                        else:
                            identity_unmapped += 1
                        continue
                    native_key = str(row.get(key_field, "")).strip() or str(row_number)
                    dedup_key = (source_name, native_key, medication_class)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    missing = []
                    for logical in required:
                        if logical == "status":
                            # Blank eMAR event_txt is an observed native semantic state,
                            # not structural absence of the status field.  The frozen
                            # contract keeps it separate and excludes it from strict
                            # administration denominators.
                            if not any(field in row for field in aliases[logical]):
                                missing.append(logical)
                        elif not any(
                            str(row.get(field, "")).strip() for field in aliases[logical]
                        ):
                            missing.append(logical)
                    literal = str(row.get("event_txt", "")).strip().lower() or "<blank>"
                    if missing:
                        state = "unmeasurable"
                    elif target in {"order", "dispense"}:
                        state = "exposed"
                    elif literal in positive:
                        state = "exposed"
                    elif literal in negative:
                        state = "unexposed"
                    else:
                        state = "unresolved"
                        if literal in excluded:
                            excluded_semantics += 1
                    counts[state] += 1
                    source_bucket = by_source.setdefault(
                        source_name,
                        {
                            key: 0
                            for key in ("exposed", "unexposed", "unresolved", "unmeasurable")
                        },
                    )
                    source_bucket[state] += 1
                    class_bucket = by_class.setdefault(
                        medication_class,
                        {
                            key: 0
                            for key in ("exposed", "unexposed", "unresolved", "unmeasurable")
                        },
                    )
                    class_bucket[state] += 1
        counts["analysis_units"] = sum(
            int(counts[key])
            for key in ("exposed", "unexposed", "unresolved", "unmeasurable")
        )
        counts["by_source"] = [
            {"source": key, **value} for key, value in sorted(by_source.items())
        ]
        counts["by_class"] = [
            {"medication_class": key, **value} for key, value in sorted(by_class.items())
        ]
        return ExecutionResult(
            operator_id=spec["operator_id"],
            operator_version=spec["operator_version"],
            adapter=self.name,
            status="executed",
            syntactically_valid=True,
            adapter_supported=True,
            measurable=True,
            executable=True,
            aggregate_only=True,
            counts=counts,
            metrics={
                "identity_unmapped_records": identity_unmapped,
                "identity_ambiguous_records": identity_ambiguous,
                "excluded_semantics_records": excluded_semantics,
            },
            failure_reasons={},
            provenance=provenance,
            warnings=[],
        )

    def execute(self, spec: dict[str, Any], data_root: str | Path | None) -> ExecutionResult:
        capability = self.capability(spec, data_root)
        base_provenance = {
            "spec_sha256": canonical_json_sha256(spec),
            "adapter_version": self.version,
            "data_model_version": spec["data_model"]["model_version"],
            "executed_at_utc": utc_now(),
            "aggregate_only": True,
            "source_database": capability.source_status.get("materialized_reference_database"),
        }
        if self._is_raw_demo(spec):
            return self._execute_raw_demo(spec, data_root, capability, base_provenance)
        if not capability.executable:
            state = (
                "unmeasurable"
                if capability.supported and capability.source_status.get("data_available")
                else "not_executed_data_unavailable"
            )
            analysis_units = 0
            if (
                state == "unmeasurable"
                and spec["output_specification"]["profile"] == "anchor_exposure"
            ):
                reference_name, reference_table = self._reference_for_spec(spec)
                reference_db = self._find_database(data_root, reference_name)
                if reference_db is not None:
                    with duckdb.connect(str(reference_db), read_only=True) as connection:
                        count_row = connection.execute(
                            f"SELECT count(*) FROM {reference_table}"
                        ).fetchone()
                    if count_row is not None:
                        analysis_units = int(count_row[0])
            return ExecutionResult(
                operator_id=spec["operator_id"],
                operator_version=spec["operator_version"],
                adapter=self.name,
                status=state,
                syntactically_valid=True,
                adapter_supported=capability.supported,
                measurable=capability.measurable,
                executable=False,
                aggregate_only=True,
                counts={
                    "analysis_units": analysis_units,
                    "exposed": 0,
                    "unexposed": 0,
                    "unresolved": 0,
                    "unmeasurable": analysis_units,
                },
                metrics={},
                failure_reasons={reason: 1 for reason in capability.reasons},
                provenance=base_provenance,
                warnings=capability.reasons,
            )
        plan = self.compile(spec, data_root)
        database = self._find_database(data_root, str(plan.implementation["database"]))
        assert database is not None
        sql = str(plan.implementation["sql"])
        profile = spec["output_specification"]["profile"]
        with duckdb.connect(str(database), read_only=True) as connection:
            rows = connection.execute(sql).fetchall()
            columns = [item[0] for item in connection.description]
        records = [dict(zip(columns, row, strict=True)) for row in rows]
        if profile == "six_class_conversion":
            by_class = []
            for record in records:
                eligible = int(record["eligible_n"])
                exposed = int(record["exposed_n"])
                by_class.append(
                    {
                        "medication_class": record["drug_class"],
                        "analysis_units": eligible,
                        "exposed": exposed,
                        "unexposed": int(record["unexposed_n"]),
                        "unresolved": 0,
                        "unmeasurable": 0,
                        "exposed_proportion": exposed / eligible if eligible else None,
                    }
                )
            counts = {
                "analysis_units": sum(row["analysis_units"] for row in by_class),
                "exposed": sum(row["exposed"] for row in by_class),
                "unexposed": sum(row["unexposed"] for row in by_class),
                "unresolved": 0,
                "unmeasurable": 0,
                "by_class": by_class,
            }
        else:
            record = records[0]
            counts = {
                "analysis_units": int(record["analysis_units_n"]),
                "exposed": int(record["exposed_n"]),
                "unexposed": int(record["unexposed_n"]),
                "unresolved": int(record["unresolved_n"]),
                "unmeasurable": 0,
            }
        return ExecutionResult(
            operator_id=spec["operator_id"],
            operator_version=spec["operator_version"],
            adapter=self.name,
            status="executed",
            syntactically_valid=True,
            adapter_supported=True,
            measurable=True,
            executable=True,
            aggregate_only=True,
            counts=counts,
            metrics={"query_profile": profile},
            failure_reasons={},
            provenance=base_provenance,
            warnings=[],
        )
