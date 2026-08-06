#!/usr/bin/env python3
"""Validate the SHA-256 manifest inside the JBI figure redesign ZIP."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    args = parser.parse_args()
    zip_path = args.zip_path.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        file_names = {item.filename for item in archive.infolist() if not item.is_dir()}
        manifests = [name for name in file_names if name.endswith("/FILE_MANIFEST_SHA256.csv")]
        if len(manifests) != 1:
            raise RuntimeError(f"Expected one manifest, found {manifests}")
        manifest_name = manifests[0]
        root = manifest_name[: -len("FILE_MANIFEST_SHA256.csv")]
        rows = list(csv.DictReader(io.StringIO(archive.read(manifest_name).decode("utf-8-sig"))))
        expected = {manifest_name}
        failures: list[dict[str, str]] = []
        for row in rows:
            relative = row["RelativePath"].replace("\\", "/")
            member = root + relative
            expected.add(member)
            if member not in file_names:
                failures.append({"file": relative, "error": "missing"})
                continue
            payload = archive.read(member)
            observed = hashlib.sha256(payload).hexdigest().upper()
            if observed != row["SHA256"].upper():
                failures.append({"file": relative, "error": "hash_mismatch"})
            if len(payload) != int(row["Bytes"]):
                failures.append({"file": relative, "error": "size_mismatch"})
        extras = sorted(file_names - expected)
        result = {
            "status": "PASS" if not failures and not extras else "FAIL",
            "zip": str(zip_path),
            "manifest_rows": len(rows),
            "verified_files": len(rows) - len(failures),
            "failures": failures,
            "unexpected_files": extras,
        }
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
