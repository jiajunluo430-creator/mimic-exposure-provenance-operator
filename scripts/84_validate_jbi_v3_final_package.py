from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JBI = ROOT / "manuscript" / "jbi"
NAME = "JBI_first_submission_package_2026-08-06_v3_method_complete"
PACKAGE = JBI / NAME
ZIP_PATH = JBI / f"{NAME}.zip"
ZIP_QC = JBI / f"{NAME}_ZIP_VERIFICATION.json"
OUT = JBI / f"{NAME}_INDEPENDENT_VALIDATION.json"


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


failures: list[str] = []
with (PACKAGE / "MANIFEST_SHA256.csv").open(encoding="utf-8", newline="") as handle:
    manifest = list(csv.DictReader(handle))

manifest_names = {row["relative_path"] for row in manifest}
actual_names = {
    path.relative_to(PACKAGE).as_posix()
    for path in PACKAGE.rglob("*")
    if path.is_file() and path.name != "MANIFEST_SHA256.csv"
}
if manifest_names != actual_names:
    failures.append(
        f"Manifest membership mismatch: missing={sorted(actual_names - manifest_names)}, "
        f"extra={sorted(manifest_names - actual_names)}"
    )
for row in manifest:
    path = PACKAGE / row["relative_path"]
    if int(row["bytes"]) != path.stat().st_size:
        failures.append(f"Byte mismatch: {row['relative_path']}")
    if row["sha256"] != digest_file(path):
        failures.append(f"SHA-256 mismatch: {row['relative_path']}")

with zipfile.ZipFile(ZIP_PATH) as archive:
    bad_member = archive.testzip()
    if bad_member:
        failures.append(f"ZIP CRC failure: {bad_member}")
    expected_zip_names = {
        f"{NAME}/{path.relative_to(PACKAGE).as_posix()}"
        for path in PACKAGE.rglob("*")
        if path.is_file()
    }
    actual_zip_names = set(archive.namelist())
    if expected_zip_names != actual_zip_names:
        failures.append("ZIP member set differs from package directory")
    for path in PACKAGE.rglob("*"):
        if not path.is_file():
            continue
        member = f"{NAME}/{path.relative_to(PACKAGE).as_posix()}"
        if digest_bytes(archive.read(member)) != digest_file(path):
            failures.append(f"ZIP content differs: {member}")

zip_qc = json.loads(ZIP_QC.read_text(encoding="utf-8"))
zip_sha = digest_file(ZIP_PATH)
if zip_qc.get("sha256") != zip_sha:
    failures.append("ZIP sidecar SHA-256 differs from the ZIP")

result = {
    "schema_version": "1.0.0",
    "package": NAME,
    "manifest_rows": len(manifest),
    "zip_members": len(actual_zip_names),
    "zip_bytes": ZIP_PATH.stat().st_size,
    "zip_sha256": zip_sha,
    "failures": failures,
    "gate": "PASS_INDEPENDENT_FINAL_PACKAGE_VALIDATION" if not failures else "FAIL",
}
OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
if failures:
    raise SystemExit(1)
