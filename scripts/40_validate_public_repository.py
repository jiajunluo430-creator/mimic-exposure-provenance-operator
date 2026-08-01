#!/usr/bin/env python3
"""Independently validate the assembled public repository without modifying it."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PUBLIC_RELEASE_MANIFEST.csv"
FORBIDDEN_COLUMNS = {
    "subject_id", "hadm_id", "stay_id", "emar_id", "emar_seq",
    "pharmacy_id", "poe_id", "patientunitstayid", "uniquepid",
}
FORBIDDEN_SUFFIXES = {
    ".duckdb", ".db", ".parquet", ".gz", ".zip", ".7z", ".feather",
}
TEXT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".py", ".r", ".ps1", ".cff"}
DRIVE_PATH = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:\\")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    failures: list[str] = []
    files = [
        item for item in ROOT.rglob("*")
        if item.is_file() and ".git" not in item.parts
    ]
    for item in files:
        relative = item.relative_to(ROOT).as_posix()
        if item.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden file type: {relative}")
        if item.suffix.lower() == ".csv":
            with item.open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), [])
            found = FORBIDDEN_COLUMNS.intersection(
                value.strip().lower() for value in header
            )
            if found:
                failures.append(f"patient/stay key columns in {relative}: {sorted(found)}")
        if item.suffix.lower() in TEXT_SUFFIXES and item.name != Path(__file__).name:
            text = item.read_text(encoding="utf-8-sig")
            if DRIVE_PATH.search(text):
                failures.append(f"local absolute path: {relative}")
            lowered = text.lower()
            for token in (
                "ghp_", "gho_", "github_pat_", "\\users\\ljjws",
                "cqmu." + "edu.cn",
            ):
                if token in lowered:
                    failures.append(f"credential/personal token in {relative}: {token}")

    if not MANIFEST.exists():
        failures.append("PUBLIC_RELEASE_MANIFEST.csv is missing")
        manifest_rows: list[dict[str, str]] = []
    else:
        with MANIFEST.open("r", encoding="utf-8-sig", newline="") as handle:
            manifest_rows = list(csv.DictReader(handle))

    expected = {
        item.relative_to(ROOT).as_posix(): item
        for item in files
        if item.name != MANIFEST.name
    }
    recorded = {row["relative_path"]: row for row in manifest_rows}
    if expected.keys() != recorded.keys():
        failures.append(
            "manifest membership mismatch: "
            f"missing={sorted(expected.keys() - recorded.keys())}; "
            f"extra={sorted(recorded.keys() - expected.keys())}"
        )
    for relative, item in expected.items():
        row = recorded.get(relative)
        if row is None:
            continue
        if int(row["bytes"]) != item.stat().st_size or row["sha256"] != sha256(item):
            failures.append(f"manifest hash/size mismatch: {relative}")

    result = {
        "files_n": len(files),
        "manifest_entries_n": len(manifest_rows),
        "failures": failures,
        "passed": not failures,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
