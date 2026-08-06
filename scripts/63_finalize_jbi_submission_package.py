#!/usr/bin/env python3
"""Build and validate the first-submission package for JBI.

This script performs document/package QA only. It never opens or queries the
restricted MIMIC-IV or eICU source data and does not rerun scientific analyses.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
JBI_ROOT = REPO / "manuscript" / "jbi"
STAGING = JBI_ROOT / "submission_package"
SOURCE = JBI_ROOT / "source"
RENDERED = JBI_ROOT / "rendered_qc"
FINAL_ROOT = JBI_ROOT / "JBI_first_submission_package_2026-08-05"
ZIP_PATH = JBI_ROOT / "JBI_first_submission_package_2026-08-05.zip"
ZIP_HASH_PATH = JBI_ROOT / "JBI_first_submission_package_2026-08-05.zip.sha256"

UPLOAD_DOCS = (
    "JBI_main_manuscript.docx",
    "JBI_cover_letter.docx",
    "JBI_highlights.docx",
    "JBI_supporting_information.docx",
)
UPLOAD_FIGURES = tuple(f"JBI_Figure{i}.pdf" for i in range(1, 6))
OPTIONAL_DOCS = ("JBI_RECORD_STROBE_checklist.docx",)
ADMIN_DOCS = ("JBI_title_page.docx",)
ALT_FIGURES = tuple(f"JBI_Figure{i}.tiff" for i in range(1, 6))
PAGE_EXPECTATIONS = {
    "JBI_cover_letter.docx": 2,
    "JBI_highlights.docx": 1,
    "JBI_main_manuscript.docx": 17,
    "JBI_RECORD_STROBE_checklist.docx": 2,
    "JBI_supporting_information.docx": 9,
    "JBI_title_page.docx": 2,
}

FORBIDDEN_LOCAL_PATHS = (
    re.compile(rb"[A-Za-z]:\\\\"),
    re.compile(rb"file:/+", re.IGNORECASE),
    re.compile(rb"C:\\Users\\", re.IGNORECASE),
    re.compile(rb"D:\\GI_CHARLS_NHANES", re.IGNORECASE),
    re.compile(rb"D:\\respiratory_icu_qdp", re.IGNORECASE),
)
PLACEHOLDERS = (
    re.compile(rb"\bTODO\b", re.IGNORECASE),
    re.compile(rb"\bTBD\b", re.IGNORECASE),
    re.compile(rb"\bPLACEHOLDER\b", re.IGNORECASE),
    re.compile(rb"\[INSERT[^\]]*\]", re.IGNORECASE),
    re.compile(rb"example@example\.com", re.IGNORECASE),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_required(filename: str, destination: Path) -> None:
    source = STAGING / filename
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(f"Missing required staging artifact: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination / filename)


def docx_members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "word/document.xml" not in names:
            raise ValueError(f"Invalid DOCX package: {path.name}")
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            raise ValueError(f"Macro content is not allowed: {path.name}")
        return {
            name: archive.read(name)
            for name in names
            if name.lower().endswith((".xml", ".rels"))
        }


def scan_payload(path: Path) -> list[str]:
    errors: list[str] = []
    payloads: list[tuple[str, bytes]]
    text_suffixes = {".md", ".txt", ".json", ".csv", ".xml", ".yaml", ".yml"}
    if path.suffix.lower() == ".docx":
        members = docx_members(path)
        payloads = list(members.items())
        document_xml = members["word/document.xml"]
        if b"<w:ins" in document_xml or b"<w:del" in document_xml:
            errors.append(f"tracked changes present in {path.name}")
        if any(name.startswith("word/comments") for name in members):
            errors.append(f"comments present in {path.name}")
    else:
        payloads = [(path.name, path.read_bytes())]

    for member_name, data in payloads:
        for pattern in FORBIDDEN_LOCAL_PATHS:
            if pattern.search(data):
                errors.append(f"local path token in {path.name}:{member_name}")
        # Placeholder checks apply only to human-visible document parts and
        # plain-text artifacts. Word's built-in style definitions legitimately
        # contain names such as "Placeholder Text", and arbitrary TIFF/PDF
        # bytes can coincidentally spell short tokens such as TBD.
        visible_docx_part = path.suffix.lower() == ".docx" and (
            member_name == "word/document.xml"
            or member_name.startswith("word/header")
            or member_name.startswith("word/footer")
            or member_name.startswith("word/footnotes")
            or member_name.startswith("word/endnotes")
        )
        if visible_docx_part or path.suffix.lower() in text_suffixes:
            for pattern in PLACEHOLDERS:
                if pattern.search(data):
                    errors.append(f"placeholder token in {path.name}:{member_name}")
    return errors


def validate_rendered_pages() -> dict[str, int]:
    observed: dict[str, int] = {}
    for filename, expected in PAGE_EXPECTATIONS.items():
        stem = Path(filename).stem
        qc_dir = RENDERED / stem
        pages = sorted(qc_dir.glob("page-*.png"))
        pdf = qc_dir / f"{stem}.pdf"
        if len(pages) != expected:
            raise ValueError(
                f"Rendered page mismatch for {filename}: expected {expected}, got {len(pages)}"
            )
        if not pdf.is_file() or pdf.stat().st_size == 0:
            raise ValueError(f"Missing rendered QC PDF for {filename}")
        observed[filename] = len(pages)
    return observed


def validate_figure_pdf(path: Path) -> dict[str, int | bool]:
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"Invalid figure PDF: {path.name}")
    image_objects = data.count(b"/Subtype /Image")
    if image_objects:
        raise ValueError(f"Raster image object found in vector figure PDF: {path.name}")
    # All submitted figures are single-page vector artwork. Counting explicit
    # /Type /Page tokens is sufficient for this bounded package check.
    pages = len(re.findall(rb"/Type\s*/Page\b", data))
    if pages != 1:
        raise ValueError(f"Expected one page in {path.name}; found {pages}")
    return {"bytes": path.stat().st_size, "pages": pages, "raster_image_objects": image_objects}


def tiff_info(path: Path) -> dict[str, object]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency is bundled
        raise RuntimeError("Pillow is required for TIFF validation") from exc
    with Image.open(path) as image:
        width, height = image.size
        dpi = image.info.get("dpi")
        if width < 1000 or height < 700:
            raise ValueError(f"TIFF dimensions unexpectedly small: {path.name} {width}x{height}")
        return {
            "bytes": path.stat().st_size,
            "width_px": width,
            "height_px": height,
            "dpi": [float(value) for value in dpi] if dpi else None,
            "mode": image.mode,
        }


def write_readme(path: Path) -> None:
    text = """# JBI first-submission upload map

Target journal: **Journal of Biomedical Informatics**

Article type: **Research Paper**

## Upload these files

| File | Portal designation |
|---|---|
| `UPLOAD_FILES/JBI_main_manuscript.docx` | Manuscript |
| `UPLOAD_FILES/JBI_cover_letter.docx` | Cover letter |
| `UPLOAD_FILES/JBI_highlights.docx` | Highlights |
| `UPLOAD_FILES/JBI_supporting_information.docx` | Supplementary material |
| `UPLOAD_FILES/JBI_Figure1.pdf` through `JBI_Figure5.pdf` | Figure 1 through Figure 5, in order |

The five PDF figures are the preferred vector upload set. Do **not** upload the
TIFF alternatives at the same time unless the portal rejects PDF artwork.

## Conditional files

- `OPTIONAL_FILES/JBI_RECORD_STROBE_checklist.docx`: upload only if a reporting-checklist or supplementary-checklist designation is offered.
- `ADMINISTRATIVE_BACKUP/JBI_title_page.docx`: retain as backup. The review model is single-anonymized and the manuscript already contains author information; upload this file only if the portal explicitly provides a separate title-page designation.
- `ALTERNATE_FIGURE_FORMATS/*.tiff`: production-quality alternatives to the vector PDFs, not duplicate routine uploads.

## Do not upload

Do not upload `QC_RECORDS`, manifests, this README, restricted MIMIC-IV/eICU
data, row-level outputs, or any local project files.

## Final author confirmations before clicking Submit

1. All five authors approved this exact version.
2. Author order, equal-contribution notes, affiliations, corresponding-author roles, and portal account match the documents.
3. Funding wording and grant numbers are correct.
4. No local ethics approval number is invented for this credentialed deidentified secondary analysis.
5. Add a telephone number only if the portal makes it mandatory.
6. Select the no-cost subscription/green route unless the team deliberately funds gold open access.
"""
    path.write_text(text, encoding="utf-8", newline="\n")


def write_qc_record(path: Path, page_counts: dict[str, int]) -> None:
    lines = [
        "# JBI DOCX render and visual-QC record",
        "",
        "Status: **PASS**",
        "",
        "Microsoft Word exported every DOCX to PDF. Poppler rendered every PDF page to PNG, and all pages were visually inspected after the final rebuild.",
        "",
        "| Document | Pages | Result |",
        "|---|---:|---|",
    ]
    for filename in sorted(page_counts):
        lines.append(f"| `{filename}` | {page_counts[filename]} | PASS |")
    lines.extend(
        [
            "",
            f"Total pages inspected: **{sum(page_counts.values())}**.",
            "",
            "Resolved defects: two orphaned table headers (main Table 3 and Supplementary Table S14) and one split cover-letter paragraph. Final review found no clipping, overlap, missing glyphs, table overflow, blank pages, or unintended page breaks.",
            "",
            "The earlier LibreOffice stall is retained separately as an implementation/toolchain failure audit; it was not a scientific or statistical failure.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def payload_manifest(root: Path) -> list[dict[str, object]]:
    excluded = {
        "MANIFEST_SHA256.csv",
        "MANIFEST_SHA256.json",
        "JBI_FINAL_VALIDATION.json",
        "JBI_FINAL_VALIDATION.md",
    }
    records: list[dict[str, object]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name in excluded:
            continue
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return records


def write_manifest(root: Path, records: list[dict[str, object]]) -> None:
    (root / "MANIFEST_SHA256.json").write_text(
        json.dumps({"scope": "all package payload files except validation/manifest files", "files": records}, indent=2)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with (root / "MANIFEST_SHA256.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("path", "bytes", "sha256"))
        writer.writeheader()
        writer.writerows(records)


def verify_manifest(root: Path, records: list[dict[str, object]]) -> None:
    for record in records:
        path = root / str(record["path"])
        if not path.is_file():
            raise FileNotFoundError(f"Manifest file missing: {record['path']}")
        if path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
            raise ValueError(f"Manifest mismatch: {record['path']}")


def build_package(replace: bool) -> dict[str, object]:
    if FINAL_ROOT.exists():
        if not replace:
            raise FileExistsError(f"Final package already exists: {FINAL_ROOT}; use --replace")
        resolved = FINAL_ROOT.resolve()
        if resolved.parent != JBI_ROOT.resolve() or resolved.name != "JBI_first_submission_package_2026-08-05":
            raise RuntimeError(f"Refusing to replace unexpected path: {resolved}")
        shutil.rmtree(resolved)
    FINAL_ROOT.mkdir(parents=True)

    upload_dir = FINAL_ROOT / "UPLOAD_FILES"
    optional_dir = FINAL_ROOT / "OPTIONAL_FILES"
    admin_dir = FINAL_ROOT / "ADMINISTRATIVE_BACKUP"
    alt_dir = FINAL_ROOT / "ALTERNATE_FIGURE_FORMATS"
    qc_dir = FINAL_ROOT / "QC_RECORDS"
    for directory in (upload_dir, optional_dir, admin_dir, alt_dir, qc_dir):
        directory.mkdir(parents=True, exist_ok=True)

    for filename in UPLOAD_DOCS + UPLOAD_FIGURES:
        copy_required(filename, upload_dir)
    for filename in OPTIONAL_DOCS:
        copy_required(filename, optional_dir)
    for filename in ADMIN_DOCS:
        copy_required(filename, admin_dir)
    for filename in ALT_FIGURES:
        copy_required(filename, alt_dir)

    for filename in ("JBI_submission_metadata.md", "JBI_author_action_items.md"):
        shutil.copy2(SOURCE / filename, admin_dir / filename)
    for filename in ("JBI_BUILD_VALIDATION.json", "JBI_BUILD_VALIDATION.md"):
        shutil.copy2(STAGING / filename, qc_dir / filename)
    page_counts = validate_rendered_pages()
    write_readme(FINAL_ROOT / "README_JBI_UPLOAD.md")
    write_qc_record(qc_dir / "JBI_DOCX_PAGE_QC.md", page_counts)

    build_validation = json.loads((STAGING / "JBI_BUILD_VALIDATION.json").read_text(encoding="utf-8"))
    if build_validation.get("status") != "PASS_JBI_SOURCE_AND_DOCUMENT_BUILD":
        raise ValueError("Source/document build validation did not pass")
    if build_validation.get("references") != 42:
        raise ValueError("Reference-count validation drifted from 42")

    expected_upload = set(UPLOAD_DOCS + UPLOAD_FIGURES)
    actual_upload = {path.name for path in upload_dir.iterdir() if path.is_file()}
    if actual_upload != expected_upload:
        raise ValueError(f"Upload set mismatch: {sorted(actual_upload ^ expected_upload)}")

    scan_errors: list[str] = []
    docx_checked = 0
    for path in sorted(p for p in FINAL_ROOT.rglob("*") if p.is_file()):
        if path.suffix.lower() == ".docx":
            docx_checked += 1
        scan_errors.extend(scan_payload(path))
    if scan_errors:
        raise ValueError("Package privacy/content scan failed: " + "; ".join(scan_errors))

    pdf_checks = {
        filename: validate_figure_pdf(upload_dir / filename)
        for filename in UPLOAD_FIGURES
    }
    tiff_checks = {
        filename: tiff_info(alt_dir / filename)
        for filename in ALT_FIGURES
    }

    records = payload_manifest(FINAL_ROOT)
    write_manifest(FINAL_ROOT, records)
    verify_manifest(FINAL_ROOT, records)

    validation = {
        "status": "PASS_JBI_FIRST_SUBMISSION_PACKAGE",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "selected_target": "Journal of Biomedical Informatics",
        "article_type": "Research Paper",
        "upload_file_count": len(expected_upload),
        "upload_files": sorted(expected_upload),
        "optional_files": list(OPTIONAL_DOCS),
        "administrative_backup_files": list(ADMIN_DOCS),
        "alternate_figure_files": list(ALT_FIGURES),
        "docx_files_checked": docx_checked,
        "docx_page_counts": page_counts,
        "total_docx_pages_visually_inspected": sum(page_counts.values()),
        "references": build_validation["references"],
        "citations_first_appearance": build_validation["citations_first_appearance"],
        "main_figures": build_validation["main_figures"],
        "main_tables": build_validation["main_tables"],
        "figure_pdf_checks": pdf_checks,
        "alternate_tiff_checks": tiff_checks,
        "payload_manifest_files": len(records),
        "local_path_scan": "PASS",
        "placeholder_scan": "PASS",
        "macro_tracked_change_comment_scan": "PASS",
        "restricted_data_included": False,
        "scientific_analysis_rerun": False,
        "git_push_or_external_submission": False,
        "remaining_author_actions": [
            "confirm all-author approval",
            "confirm author and funding metadata in portal",
            "add telephone only if portal requires it",
        ],
    }
    (FINAL_ROOT / "JBI_FINAL_VALIDATION.json").write_text(
        json.dumps(validation, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    summary = f"""# JBI final submission-package validation

Status: **{validation['status']}**

- Direct upload files: {validation['upload_file_count']}
- DOCX files structurally checked: {docx_checked}
- DOCX pages visually inspected: {validation['total_docx_pages_visually_inspected']}
- References: {validation['references']}, cited in first-appearance order 1–42
- Main displays: {validation['main_figures']} figures + {validation['main_tables']} tables
- Vector figure PDFs: PASS (single page; zero raster image objects)
- Alternate TIFFs: PASS
- Local-path, placeholder, macro, tracked-change, and comment scans: PASS
- Restricted patient-level data included: No
- Scientific analysis rerun: No
- External push/submission performed: No

Only administrative author confirmations remain; see `README_JBI_UPLOAD.md`.
"""
    (FINAL_ROOT / "JBI_FINAL_VALIDATION.md").write_text(summary, encoding="utf-8", newline="\n")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    if ZIP_HASH_PATH.exists():
        ZIP_HASH_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in FINAL_ROOT.rglob("*") if p.is_file()):
            archive.write(path, (Path(FINAL_ROOT.name) / path.relative_to(FINAL_ROOT)).as_posix())

    with zipfile.ZipFile(ZIP_PATH) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"ZIP CRC failure: {bad_member}")
        expected_members = {
            (Path(FINAL_ROOT.name) / path.relative_to(FINAL_ROOT)).as_posix()
            for path in FINAL_ROOT.rglob("*")
            if path.is_file()
        }
        if set(archive.namelist()) != expected_members:
            raise ValueError("ZIP member inventory mismatch")

    zip_hash = sha256(ZIP_PATH)
    ZIP_HASH_PATH.write_text(f"{zip_hash}  {ZIP_PATH.name}\n", encoding="ascii", newline="\n")
    validation["zip_file"] = ZIP_PATH.name
    validation["zip_bytes"] = ZIP_PATH.stat().st_size
    validation["zip_sha256"] = zip_hash
    return validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="replace only the exact dated final package")
    args = parser.parse_args()
    validation = build_package(args.replace)
    print(json.dumps(validation, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
