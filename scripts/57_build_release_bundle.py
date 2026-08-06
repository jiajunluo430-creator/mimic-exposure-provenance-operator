#!/usr/bin/env python3
"""Assemble a patient-free release bundle from committed repository files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
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
FORBIDDEN_SUFFIXES = {".duckdb", ".db", ".parquet", ".feather", ".7z"}
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
EXCLUDED_TRACKED = {"PUBLIC_RELEASE_MANIFEST.csv", "PUBLIC_RELEASE_VALIDATION.json"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_text(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [ROOT / item.decode("utf-8") for item in output.split(b"\0") if item]


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


def scan_release(root: Path) -> list[str]:
    failures: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
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
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--output-root", type=Path, default=ROOT / "release_artifacts")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()

    dirty = git_text("status", "--porcelain")
    if dirty:
        raise RuntimeError("Release bundle requires a clean committed working tree")
    commit = git_text("rev-parse", "HEAD")
    short_commit = git_text("rev-parse", "--short=8", "HEAD")
    output_root = args.output_root.resolve()
    bundle_name = f"medprov-{args.version}-{short_commit}"
    bundle = output_root / bundle_name
    archive = output_root / f"{bundle_name}.zip"
    if bundle.exists() or archive.exists():
        raise FileExistsError(f"Refusing to overwrite existing release artifact: {bundle_name}")
    bundle.mkdir(parents=True)

    copied = 0
    for source in tracked_files():
        relative = source.relative_to(ROOT)
        if relative.as_posix() in EXCLUDED_TRACKED:
            continue
        destination = bundle / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1

    dist_files = sorted(args.dist_dir.resolve().glob("medprov-0.1.0*"))
    if not dist_files:
        raise FileNotFoundError("Build wheel and sdist before assembling the release")
    for source in dist_files:
        destination = bundle / "dist" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    failures = scan_release(bundle)
    validation: dict[str, Any] = {
        "schema_version": "1.0.0",
        "gate": "PASS_PUBLIC_RELEASE_VALIDATION" if not failures else "FAIL_PUBLIC_RELEASE_VALIDATION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": args.version,
        "git_commit": commit,
        "tracked_files_copied_n": copied,
        "distribution_files_n": len(dist_files),
        "failures": failures,
        "claim_boundary": "patient-free software, synthetic fixtures, contracts, and aggregate evidence only",
    }
    (bundle / "PUBLIC_RELEASE_VALIDATION.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if failures:
        raise RuntimeError("Public release validation failed: " + "; ".join(failures))

    manifest_rows: list[dict[str, Any]] = [
        {
            "relative_path": path.relative_to(bundle).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(bundle.rglob("*"))
        if path.is_file() and path.name != "PUBLIC_RELEASE_MANIFEST.csv"
    ]
    write_csv(bundle / "PUBLIC_RELEASE_MANIFEST.csv", manifest_rows)

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                handle.write(path, (Path(bundle_name) / path.relative_to(bundle)).as_posix())
    archive_hash = sha256_file(archive)
    archive.with_suffix(".zip.sha256").write_text(
        f"{archive_hash}  {archive.name}\n", encoding="ascii"
    )
    print(
        json.dumps(
            {
                "gate": validation["gate"],
                "bundle": str(bundle),
                "archive": str(archive),
                "archive_sha256": archive_hash,
                "manifest_entries_n": len(manifest_rows),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
