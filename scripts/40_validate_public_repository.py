#!/usr/bin/env python3
"""Validate a source checkout or assembled patient-free medprov release."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_COLUMNS = {
    "subject_id",
    "hadm_id",
    "stay_id",
    "emar_id",
    "emar_seq",
    "pharmacy_id",
    "poe_id",
    "patientunitstayid",
    "uniquepid",
}
FORBIDDEN_SUFFIXES = {".duckdb", ".db", ".parquet", ".7z", ".feather"}
TEXT_SUFFIXES = {
    ".cff",
    ".csv",
    ".html",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".r",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}
DRIVE_PATH = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:\\[A-Za-z0-9_.-]")
SECRET_PATTERNS = {
    "github_token": re.compile(r"(?:ghp|gho|github_pat)_[A-Za-z0-9_]{12,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "local_user": re.compile(r"(?i)\\Users\\ljjws(?:\\|\b)"),
}
REQUIRED = {
    "pyproject.toml",
    "CITATION.cff",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY_PRIVACY.md",
    "METHOD_SPECIFICATION.md",
    "schemas/medication_exposure_operator.schema.json",
    "schemas/medication_exposure_reporting.schema.json",
    "src/medprov/cli.py",
    "tests/test_synthetic_end_to_end.py",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_files(root: Path) -> list[Path]:
    if (root / ".git").exists():
        output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
        return [root / value.decode("utf-8") for value in output.split(b"\0") if value]
    return [path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--require-manifest", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    failures: list[str] = []
    files = source_files(root)
    relative_files = {path.relative_to(root).as_posix() for path in files}

    missing_required = sorted(REQUIRED - relative_files)
    failures.extend(f"missing required file: {path}" for path in missing_required)
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden file type: {relative}")
        if path.suffix.lower() == ".gz" and not relative.startswith("dist/"):
            failures.append(f"forbidden gzip outside dist: {relative}")
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), [])
            found = FORBIDDEN_COLUMNS.intersection(value.strip().lower() for value in header)
            if found:
                failures.append(f"patient/stay key columns in {relative}: {sorted(found)}")
        if path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8-sig")
            if DRIVE_PATH.search(text):
                failures.append(f"local absolute path: {relative}")
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    failures.append(f"{label}: {relative}")

    manifest_path = root / "PUBLIC_RELEASE_MANIFEST.csv"
    manifest_checked = args.require_manifest and manifest_path.exists()
    if args.require_manifest and not manifest_path.exists():
        failures.append("PUBLIC_RELEASE_MANIFEST.csv is missing")
    if manifest_checked:
        with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
            manifest_rows = list(csv.DictReader(handle))
        expected = {
            path.relative_to(root).as_posix(): path
            for path in files
            if path.name != manifest_path.name
        }
        recorded = {row["relative_path"]: row for row in manifest_rows}
        if expected.keys() != recorded.keys():
            failures.append(
                "manifest membership mismatch: "
                f"missing={sorted(expected.keys() - recorded.keys())}; "
                f"extra={sorted(recorded.keys() - expected.keys())}"
            )
        for relative, path in expected.items():
            row = recorded.get(relative)
            if row is None:
                continue
            if int(row["bytes"]) != path.stat().st_size or row["sha256"] != sha256_file(path):
                failures.append(f"manifest hash/size mismatch: {relative}")

    result = {
        "schema_version": "1.0.0",
        "gate": "PASS_PUBLIC_REPOSITORY_VALIDATION" if not failures else "FAIL_PUBLIC_REPOSITORY_VALIDATION",
        "root": str(root),
        "files_n": len(files),
        "manifest_checked": manifest_checked,
        "failures": failures,
        "passed": not failures,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
