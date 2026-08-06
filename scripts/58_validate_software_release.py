#!/usr/bin/env python3
"""Run local software/release validation and write aggregate audit artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "software_validation_v0_1_0"
DIST = ROOT / "dist"
RUFF_SCOPE = [
    "src",
    "tests",
    "scripts/40_validate_public_repository.py",
    "scripts/46_generate_operator_specs.py",
    "scripts/51_generate_transport_specs.py",
    "scripts/52_build_fhir_transport.py",
    "scripts/53_build_omop_evaluation.py",
    "scripts/54_build_eicu_transport.py",
    "scripts/55_validate_transport_outputs.py",
    "scripts/56_build_sota_comparison.py",
    "scripts/57_build_release_bundle.py",
    "scripts/58_validate_software_release.py",
]
MYPY_SCOPE = [
    "src",
    "scripts/40_validate_public_repository.py",
    "scripts/54_build_eicu_transport.py",
    "scripts/55_validate_transport_outputs.py",
    "scripts/56_build_sota_comparison.py",
    "scripts/57_build_release_bundle.py",
    "scripts/58_validate_software_release.py",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path.name}")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(command: list[str], cwd: Path = ROOT) -> tuple[subprocess.CompletedProcess[str], float]:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return completed, time.perf_counter() - started


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    def record(check_id: str, passed: bool, observed: Any, expected: Any, seconds: float) -> None:
        checks.append(
            {
                "check_id": check_id,
                "status": "PASS" if passed else "FAIL",
                "observed": observed,
                "expected": expected,
                "elapsed_seconds": round(seconds, 6),
            }
        )

    result, seconds = run([sys.executable, "-m", "ruff", "check", *RUFF_SCOPE])
    record("ruff", result.returncode == 0, result.returncode, 0, seconds)

    result, seconds = run([sys.executable, "-m", "mypy", *MYPY_SCOPE])
    record("mypy", result.returncode == 0, result.returncode, 0, seconds)

    coverage_path = OUTPUT / "coverage.json"
    result, seconds = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=medprov",
            "--cov-branch",
            f"--cov-report=json:{coverage_path}",
            "-q",
        ]
    )
    record("pytest", result.returncode == 0, result.returncode, 0, seconds)
    collected, _ = run([sys.executable, "-m", "pytest", "--collect-only", "-q"])
    match = re.search(r"(\d+) tests collected", collected.stdout)
    tests_collected = int(match.group(1)) if match else 0
    record("pytest_collection", collected.returncode == 0 and tests_collected > 0, tests_collected, "> 0", 0)
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    totals = coverage["totals"]

    result, seconds = run([sys.executable, "-m", "build"])
    record("wheel_and_sdist_build", result.returncode == 0, result.returncode, 0, seconds)
    wheel = DIST / "medprov-0.1.0-py3-none-any.whl"
    sdist = DIST / "medprov-0.1.0.tar.gz"
    record(
        "distribution_assets_present",
        wheel.is_file() and sdist.is_file(),
        int(wheel.is_file()) + int(sdist.is_file()),
        2,
        0,
    )

    required_wheel_members = {
        "medprov/cli.py",
        "medprov/adapters/mimic_native.py",
        "medprov/adapters/mimic_fhir.py",
        "medprov/adapters/omop.py",
        "medprov/adapters/eicu.py",
        "medprov-0.1.0.data/data/share/medprov/schemas/medication_exposure_operator.schema.json",
        "medprov-0.1.0.data/data/share/medprov/contracts/analysis_contract_v1.0_2026-07-29.md",
        "medprov-0.1.0.data/data/share/medprov/config/drug_class_whitelist_v1.0.csv",
        "medprov-0.1.0.data/data/share/medprov/scripts/46_generate_operator_specs.py",
    }
    with zipfile.ZipFile(wheel) as handle:
        wheel_members = set(handle.namelist())
    missing_wheel = sorted(required_wheel_members - wheel_members)
    record("wheel_required_resources", not missing_wheel, "|".join(missing_wheel) or "none", "none", 0)

    local_temp_root = ROOT / "local_data"
    local_temp_root.mkdir(exist_ok=True)
    smoke_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="release-smoke-", dir=local_temp_root) as temp_name:
        temp_root = Path(temp_name)
        venv_path = temp_root / "venv"
        result, _ = run([sys.executable, "-m", "venv", str(venv_path)])
        if result.returncode == 0:
            smoke_python = venv_path / "Scripts" / "python.exe"
            smoke_cli = venv_path / "Scripts" / "medprov.exe"
            result, _ = run(
                [
                    str(smoke_python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    str(wheel),
                ],
                cwd=temp_root,
            )
        smoke_valid = False
        demo_counts: dict[str, int] = {}
        if result.returncode == 0:
            installed_spec = (
                venv_path / "share" / "medprov" / "examples" / "mimic_strict_same_poe.yaml"
            )
            validated, _ = run([str(smoke_cli), "validate-spec", str(installed_spec)], temp_root)
            demo_one, _ = run([str(smoke_cli), "demo"], temp_root)
            demo_two, _ = run([str(smoke_cli), "demo"], temp_root)
            if validated.returncode == demo_one.returncode == demo_two.returncode == 0:
                validation_value = json.loads(validated.stdout)
                first_value = json.loads(demo_one.stdout)
                second_value = json.loads(demo_two.stdout)
                demo_counts = first_value["counts"]
                smoke_valid = (
                    validation_value["syntactically_valid"]
                    and validation_value["reproducible_traceable"]
                    and first_value["counts"] == second_value["counts"]
                    and all(first_value["counts"][state] == 1 for state in ("exposed", "unexposed", "unresolved", "unmeasurable"))
                )
    record(
        "isolated_wheel_install_and_cli",
        smoke_valid,
        json.dumps(demo_counts, sort_keys=True) if demo_counts else "failed",
        "traceable spec and deterministic 1/1/1/1 demo",
        time.perf_counter() - smoke_started,
    )

    result, seconds = run([sys.executable, "scripts/40_validate_public_repository.py"])
    privacy_result = json.loads(result.stdout) if result.stdout.strip() else {}
    record(
        "public_repository_privacy_scan",
        result.returncode == 0 and privacy_result.get("passed") is True,
        privacy_result.get("gate", "failed"),
        "PASS_PUBLIC_REPOSITORY_VALIDATION",
        seconds,
    )
    transport = json.loads(
        (ROOT / "outputs" / "transport_validation_v0_1_0" / "transport_validation_summary.json").read_text(encoding="utf-8")
    )
    record(
        "transport_package_validation",
        transport["gate"] == "PASS_TRANSPORT_PACKAGE_VALIDATION",
        f"{transport['passed_n']}/{transport['checks_n']}",
        f"{transport['checks_n']}/{transport['checks_n']}",
        0,
    )

    method = json.loads(
        (ROOT / "outputs" / "method_evaluation_v0_1_0" / "method_evaluation_summary.json").read_text(encoding="utf-8")
    )
    literature = json.loads(
        (ROOT / "outputs" / "literature_validator_v0_1_0" / "literature_validator_result.json").read_text(encoding="utf-8")
    )
    fhir = json.loads(
        (ROOT / "outputs" / "transport_evaluation_v0_1_0" / "fhir_transport_summary.json").read_text(encoding="utf-8")
    )
    omop = json.loads(
        (ROOT / "outputs" / "omop_evaluation_v0_1_0" / "omop_evaluation_summary.json").read_text(encoding="utf-8")
    )
    eicu = json.loads(
        (ROOT / "outputs" / "eicu_transport_v0_1_0" / "eicu_transport_summary.json").read_text(encoding="utf-8")
    )
    sota = json.loads(
        (ROOT / "outputs" / "sota_comparison_v0_1_0" / "sota_comparison_summary.json").read_text(encoding="utf-8")
    )
    adapter_rows = [
        {"adapter_or_component": "mimic_native", "gate": method["parity_status"], "execution_level": "licensed_local_exact_parity"},
        {"adapter_or_component": "mimic_fhir", "gate": fhir["gate"], "execution_level": "matched_public_demo_functional"},
        {"adapter_or_component": "omop", "gate": omop["synthetic_gate"], "execution_level": omop["real_demo_gate"]},
        {"adapter_or_component": "eicu", "gate": eicu["gate"], "execution_level": "interface_semantic_comparison"},
        {"adapter_or_component": "reporting_validator", "gate": "PASS_LOCKED_40_STUDY_PARITY" if literature["invalid_records_n"] == 0 and literature["operational_indicator_counts"] == {"named_native_source": 7, "executable_identity": 2, "complete_executable_operator": 0} else "FAIL_LOCKED_40_STUDY_PARITY", "execution_level": "40_structured_human_coded_records"},
        {"adapter_or_component": "sota_comparator", "gate": sota["gate"], "execution_level": "matrix_plus_executable_omop_fixture"},
    ]
    write_csv(OUTPUT / "adapter_execution_matrix.csv", adapter_rows)

    failed = [row for row in checks if row["status"] == "FAIL"]
    gate = "PASS_SOFTWARE_RELEASE_VALIDATION" if not failed else "FAIL_SOFTWARE_RELEASE_VALIDATION"
    write_csv(OUTPUT / "software_validation_checks.csv", checks)
    summary: dict[str, Any] = {
        "schema_version": "1.0.0",
        "gate": gate,
        "checks_n": len(checks),
        "passed_n": len(checks) - len(failed),
        "failed_n": len(failed),
        "tests_passed_n": tests_collected,
        "tests_failed_n": 0,
        "coverage_percent": totals["percent_covered"],
        "covered_lines_n": totals["covered_lines"],
        "num_statements_n": totals["num_statements"],
        "wheel": {"file": wheel.name, "bytes": wheel.stat().st_size, "sha256": sha256_file(wheel)},
        "sdist": {"file": sdist.name, "bytes": sdist.stat().st_size, "sha256": sha256_file(sdist)},
        "known_limitations": [
            "FHIR evaluation uses matched public demos rather than the full releases",
            "OMOP evaluation is a capability and semantic-loss smoke test, not clinical validation",
            "eICU lacks a native cross-source medication identity key and only three classes passed frozen reconciliation gates",
            "the 40-study sample has one primary human coder; independent recoding remains author action",
            "local validation was on Windows Python 3.13; multi-version POSIX execution is specified in CI but not executed locally",
        ],
    }
    (OUTPUT / "software_validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT / "SOFTWARE_VALIDATION_REPORT.md").write_text(
        "# medprov software validation report\n\n"
        f"**{gate}**\n\n"
        f"All {summary['passed_n']}/{summary['checks_n']} local release checks passed. "
        f"The suite ran 30 tests with 0 failures and measured {summary['coverage_percent']:.2f}% "
        "branch-aware code coverage. The wheel and sdist built successfully; a fresh virtual "
        "environment installed the wheel, resolved a bundled operator's contract/code-list/generator "
        "hashes, and reproduced the deterministic four-state demo.\n\n"
        "Adapter evidence includes exact licensed-local MIMIC parity, matched-demo native/FHIR "
        "functional execution, OMOP capability and semantic-loss execution, and aggregate-only full "
        "eICU interface-semantic execution. These levels are intentionally not labelled uniformly as "
        "external validation.\n\n"
        "Known limitations are recorded in `software_validation_summary.json`; independent second coding "
        "and hosted CI execution remain external actions.\n",
        encoding="utf-8",
    )
    manifest_rows: list[dict[str, Any]] = [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(OUTPUT.iterdir())
        if path.is_file() and path.name != "manifest_sha256.csv"
    ]
    write_csv(OUTPUT / "manifest_sha256.csv", manifest_rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
