"""MIMIC-IV native reference adapter.

The first public implementation executes against the materialized, read-only
DuckDB reference cache produced by the frozen pipeline. Raw CSV sources remain
the authoritative inputs; using the cache avoids repeating the previously
audited multi-hour scans and lets parity failures be localized deterministically.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb

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
                    class_filter = spec["identity_rule"]["class_filter"]
                    if "route" in required:
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
        if not capability.executable:
            state = (
                "unmeasurable"
                if capability.supported and capability.source_status.get("data_available")
                else "not_executed_data_unavailable"
            )
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
                counts={"exposed": 0, "unexposed": 0, "unresolved": 0, "unmeasurable": 0},
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
