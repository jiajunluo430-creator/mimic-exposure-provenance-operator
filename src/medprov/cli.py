"""Command-line interface for medprov."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .adapters import get_adapter
from .comparison import compare_result_files
from .compiler import compile_operator_file
from .executor import execute_operator, execute_operator_file
from .reporting import write_report_bundle
from .schema import load_document
from .utils import write_json
from .validator import (
    load_reporting_records,
    validate_reporting_records,
    validate_specification_file,
)

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_NOT_EXECUTABLE = 3
EXIT_RUNTIME = 4


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="medprov", description="Machine-executable medication-exposure provenance operators"
    )
    parser.add_argument("--version", action="version", version=f"medprov {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-spec", help="Validate an operator specification")
    validate.add_argument("spec")
    validate.add_argument("--adapter")
    validate.add_argument("--data-root")

    capability = sub.add_parser("capability", help="Assess adapter support and measurability")
    capability.add_argument("--spec", required=True)
    capability.add_argument("--adapter", required=True)
    capability.add_argument("--data-root")

    compile_parser = sub.add_parser("compile", help="Compile an operator to an adapter query plan")
    compile_parser.add_argument("--spec", required=True)
    compile_parser.add_argument("--adapter")
    compile_parser.add_argument("--data-root")
    compile_parser.add_argument("--out")

    execute = sub.add_parser("execute", help="Execute an operator with aggregate-only output")
    execute.add_argument("--spec", required=True)
    execute.add_argument("--adapter")
    execute.add_argument("--data-root", required=True)
    execute.add_argument("--aggregate-out")

    compare = sub.add_parser("compare", help="Compare two aggregate execution results")
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    compare.add_argument("--out")

    reporting = sub.add_parser(
        "validate-reporting", help="Validate structured medication-exposure reporting records"
    )
    reporting.add_argument("structured_input")
    reporting.add_argument("--out")

    demo = sub.add_parser("demo", help="Run a deterministic synthetic end-to-end example")
    demo.add_argument("--out")
    return parser


def _demo_spec() -> dict[str, Any]:
    null_hash = "0" * 64
    return {
        "schema_version": "1.0.0",
        "operator_id": "medprov.synthetic.demo",
        "operator_version": "0.1.0",
        "clinical_construct": "synthetic medication exposure",
        "analysis_unit": "synthetic_event_id",
        "target_event": "documented_administration",
        "data_model": {
            "adapter": "synthetic",
            "model_name": "medprov synthetic",
            "model_version": "1.0",
        },
        "provenance": {
            "author": "medprov",
            "date": "2026-08-05",
            "contract_path": "synthetic",
            "contract_sha256": null_hash,
            "generator": "synthetic",
            "generator_sha256": null_hash,
        },
        "source_layer": {
            "tables_or_resources": ["canonical_events.csv"],
            "source_type": "administration",
            "observability_gate": {
                "enabled": False,
                "rule": "synthetic source is fully observable",
                "deployment_start": None,
                "deployment_end": None,
                "failure_state": "unmeasurable",
            },
        },
        "identity_rule": {
            "vocabulary": "synthetic",
            "vocabulary_version": "1.0",
            "code_list": {"path": "synthetic", "sha256": null_hash, "tier": "strict"},
            "native_keys": ["native_order_id"],
            "match_mode": "source_code",
            "deduplication_unit": ["analysis_unit_key"],
            "revision_handling": "collapse_to_unit",
            "class_filter": ["insulin"],
            "ingredient_filter": ["insulin"],
            "negative_match_rule": None,
        },
        "time_origin_window": {
            "origin": "event_time",
            "assignment_timestamp": "event_time",
            "start_offset_hours": 0,
            "end_offset_hours": 24,
            "lower_inclusive": True,
            "upper_inclusive": True,
            "grace_before_hours": 0,
            "grace_after_hours": 0,
            "censoring_boundary": "none",
            "window_rule": "synthetic 24-hour window",
        },
        "event_semantics_map": {
            "positive": ["administered"],
            "negative": ["not given", "held"],
            "excluded": ["confirmed", "flushed", "<blank>"],
            "unresolved": ["unknown"],
            "precedence": "detail_override",
            "normalization": {"trim": True, "lowercase": True, "null_token": "<blank>"},
        },
        "required_metadata": {
            "route": "optional",
            "dose": "required",
            "unit": "required",
            "frequency": "ignored",
            "status": "required",
            "missing_policy": "unmeasurable",
            "constraints": ["dose must be present"],
        },
        "output_specification": {
            "profile": "synthetic_demo",
            "aggregate_only": True,
            "allow_patient_level": False,
            "trace_level": "aggregate",
            "classifications": ["exposed", "unexposed", "unresolved", "unmeasurable"],
            "formats": ["json", "markdown", "html"],
        },
    }


def _run_demo(output: str | None) -> dict[str, Any]:
    rows = [
        {
            "analysis_unit_key": "SYN-1",
            "medication_class": "insulin",
            "event_state": "administered",
            "dose": "2",
            "unit": "unit",
            "route": "SC",
            "status": "complete",
        },
        {
            "analysis_unit_key": "SYN-2",
            "medication_class": "insulin",
            "event_state": "not given",
            "dose": "2",
            "unit": "unit",
            "route": "SC",
            "status": "complete",
        },
        {
            "analysis_unit_key": "SYN-3",
            "medication_class": "insulin",
            "event_state": "confirmed",
            "dose": "2",
            "unit": "unit",
            "route": "SC",
            "status": "complete",
        },
        {
            "analysis_unit_key": "SYN-4",
            "medication_class": "insulin",
            "event_state": "administered",
            "dose": "",
            "unit": "",
            "route": "SC",
            "status": "complete",
        },
    ]
    with tempfile.TemporaryDirectory(prefix="medprov-demo-") as temp:
        fixture = Path(temp) / "canonical_events.csv"
        with fixture.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        result = execute_operator(
            _demo_spec(), adapter_name="synthetic", data_root=fixture
        ).to_dict()
    if output:
        write_report_bundle(output, "medprov_demo", "medprov synthetic demo", result)
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-spec":
            result = validate_specification_file(args.spec, args.adapter, args.data_root).to_dict()
            _print(result)
            return EXIT_OK if result["syntactically_valid"] else EXIT_INVALID
        if args.command == "capability":
            spec = load_document(args.spec)
            result = get_adapter(args.adapter).capability(spec, args.data_root).to_dict()
            _print(result)
            return EXIT_OK if result["executable"] else EXIT_NOT_EXECUTABLE
        if args.command == "compile":
            result = compile_operator_file(args.spec, args.adapter, args.data_root).to_dict()
            if args.out:
                write_json(args.out, result)
            _print(result)
            return EXIT_OK
        if args.command == "execute":
            result = execute_operator_file(
                args.spec, args.adapter, args.data_root, args.aggregate_out
            ).to_dict()
            _print(result)
            return EXIT_OK if result["executable"] else EXIT_NOT_EXECUTABLE
        if args.command == "compare":
            result = compare_result_files(args.left, args.right)
            if args.out:
                write_json(args.out, result)
            _print(result)
            return EXIT_OK
        if args.command == "validate-reporting":
            result = validate_reporting_records(load_reporting_records(args.structured_input))
            if args.out:
                write_report_bundle(
                    args.out,
                    "reporting_validation",
                    "Medication-exposure reporting validation",
                    result,
                )
            _print(result)
            return EXIT_OK if result["invalid_records_n"] == 0 else EXIT_INVALID
        if args.command == "demo":
            _print(_run_demo(args.out))
            return EXIT_OK
    except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return EXIT_INVALID
    except Exception as exc:  # pragma: no cover - safety net for CLI users
        print(
            json.dumps({"status": "runtime_error", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return EXIT_RUNTIME
    return EXIT_RUNTIME


if __name__ == "__main__":
    raise SystemExit(main())
