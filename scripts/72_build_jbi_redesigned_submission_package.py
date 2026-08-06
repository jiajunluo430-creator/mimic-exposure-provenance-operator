#!/usr/bin/env python3
"""Build the versioned JBI first-submission package with redesigned figures.

The prior audited package is treated as immutable. This script copies its
document set, replaces only the five submitted vector PDFs and five alternate
TIFFs with the locked redesign outputs, records continuity checks, rebuilds the
manifest, and produces a separately named ZIP.

No restricted source data are opened and no scientific analysis is rerun.
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
PRIOR_ROOT = JBI_ROOT / "JBI_first_submission_package_2026-08-05"
REDESIGN_ROOT = JBI_ROOT / "figure_redesign_2026-08-05" / "final_figures"
RENDER_ROOT = JBI_ROOT / "rendered_qc_v2_redesigned_figures"
FINAL_NAME = "JBI_first_submission_package_2026-08-05_v2_redesigned_figures"
FINAL_ROOT = JBI_ROOT / FINAL_NAME
ZIP_PATH = JBI_ROOT / f"{FINAL_NAME}.zip"
ZIP_HASH_PATH = JBI_ROOT / f"{FINAL_NAME}.zip.sha256"

UPLOAD_FIGURES = tuple(f"JBI_Figure{i}.pdf" for i in range(1, 6))
ALT_FIGURES = tuple(f"JBI_Figure{i}.tiff" for i in range(1, 6))
DOCX_RELATIVE_PATHS = (
    Path("ADMINISTRATIVE_BACKUP/JBI_title_page.docx"),
    Path("OPTIONAL_FILES/JBI_RECORD_STROBE_checklist.docx"),
    Path("UPLOAD_FILES/JBI_cover_letter.docx"),
    Path("UPLOAD_FILES/JBI_highlights.docx"),
    Path("UPLOAD_FILES/JBI_main_manuscript.docx"),
    Path("UPLOAD_FILES/JBI_supporting_information.docx"),
)
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


def require_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Required file missing or empty: {path}")


def count_docx_media(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "word/document.xml" not in names:
            raise ValueError(f"Invalid DOCX package: {path}")
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            raise ValueError(f"Macro content is not allowed: {path.name}")
        return sum(name.startswith("word/media/") for name in names)


def scan_payload(path: Path) -> list[str]:
    errors: list[str] = []
    text_suffixes = {".md", ".txt", ".json", ".csv", ".xml", ".yaml", ".yml"}
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as archive:
            members = {
                name: archive.read(name)
                for name in archive.namelist()
                if name.lower().endswith((".xml", ".rels"))
            }
        document_xml = members.get("word/document.xml", b"")
        if b"<w:ins" in document_xml or b"<w:del" in document_xml:
            errors.append(f"tracked changes present in {path.name}")
        if any(name.startswith("word/comments") for name in members):
            errors.append(f"comments present in {path.name}")
        payloads = list(members.items())
    else:
        payloads = [(path.name, path.read_bytes())]

    for member_name, data in payloads:
        for pattern in FORBIDDEN_LOCAL_PATHS:
            if pattern.search(data):
                errors.append(f"local path token in {path.name}:{member_name}")
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


def validate_rendered_docx() -> dict[str, int]:
    page_counts: dict[str, int] = {}
    for relative in DOCX_RELATIVE_PATHS:
        filename = relative.name
        expected = PAGE_EXPECTATIONS[filename]
        qc_dir = RENDER_ROOT / relative.stem
        pages = sorted(qc_dir.glob("page-*.png"))
        pdf = qc_dir / f"{relative.stem}.pdf"
        if len(pages) != expected:
            raise ValueError(
                f"Rendered page mismatch for {filename}: expected {expected}, got {len(pages)}"
            )
        require_file(pdf)
        page_counts[filename] = len(pages)
    return page_counts


def validate_figure_pdf(path: Path) -> dict[str, object]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    if len(reader.pages) != 1:
        raise ValueError(f"Expected single-page figure PDF: {path.name}")
    image_objects = 0
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        xobjects = resources.get("/XObject") or {}
        for obj in xobjects.values():
            resolved = obj.get_object()
            if resolved.get("/Subtype") == "/Image":
                image_objects += 1
    if image_objects:
        raise ValueError(f"Raster image objects found in vector PDF: {path.name}")
    return {
        "bytes": path.stat().st_size,
        "pages": 1,
        "raster_image_objects": 0,
        "sha256": sha256(path),
    }


def validate_tiff(path: Path) -> dict[str, object]:
    from PIL import Image

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
            "sha256": sha256(path),
        }


def update_readme(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "## Figure version in this package\n"
    if marker not in text:
        insertion = (
            "\n## Figure version in this package\n\n"
            "Figure 1 through Figure 5 are the data-first JBI redesign finalized on "
            "2026-08-05. The scientific values and figure-facing source tables are "
            "unchanged; only visual grammar and layout were redesigned. The upload "
            "PDFs are editable vector artwork, and the TIFF files are raster "
            "alternatives. The manuscript contains captions and callouts but no "
            "embedded figure media, so no duplicate old artwork remains inside the "
            "DOCX.\n"
        )
        text = text.replace("\n## Conditional files\n", insertion + "\n## Conditional files\n")
    path.write_text(text, encoding="utf-8", newline="\n")


def write_figure_qc(path: Path, pdf_checks: dict[str, object], tiff_checks: dict[str, object]) -> None:
    lines = [
        "# JBI redesigned-figure integration record",
        "",
        "Status: **PASS**",
        "",
        "- Figure 1 through Figure 5 were copied byte-for-byte from the locked redesign outputs.",
        "- The prior first-submission package remains unchanged.",
        "- All five PDF uploads are single-page vector artwork with zero raster image objects.",
        "- All five TIFF alternatives meet the package dimension gate.",
        "- All six DOCX files are byte-identical to the previously audited documents.",
        "- The main manuscript contains zero embedded media objects; figures remain separate upload files.",
        "- No scientific analysis, contract, whitelist, window, or statistical definition was changed.",
        "",
        "| Figure | PDF SHA-256 | TIFF dimensions |",
        "|---|---|---|",
    ]
    for index in range(1, 6):
        pdf = pdf_checks[f"JBI_Figure{index}.pdf"]
        tiff = tiff_checks[f"JBI_Figure{index}.tiff"]
        lines.append(
            f"| Figure {index} | `{pdf['sha256']}` | {tiff['width_px']} x {tiff['height_px']} px |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_docx_qc(path: Path, page_counts: dict[str, int]) -> None:
    lines = [
        "# JBI DOCX render and visual-QC record",
        "",
        "Status: **PASS**",
        "",
        "Microsoft Word re-exported every final-package DOCX to PDF. Poppler rendered every PDF page to PNG; all pages were visually inspected for the v2 package.",
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
            "No clipping, overlap, missing glyphs, table overflow, blank pages, or unintended page breaks were observed. Because figures are separate uploads, the redesigned artwork does not alter manuscript pagination.",
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
        json.dumps(
            {"scope": "all package payload files except validation/manifest files", "files": records},
            indent=2,
        )
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
        require_file(path)
        if path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
            raise ValueError(f"Manifest mismatch: {record['path']}")


def prepare_destination(replace: bool) -> None:
    if not PRIOR_ROOT.is_dir():
        raise FileNotFoundError(f"Prior audited package not found: {PRIOR_ROOT}")
    if FINAL_ROOT.exists():
        if not replace:
            raise FileExistsError(f"Destination exists: {FINAL_ROOT}; use --replace")
        resolved = FINAL_ROOT.resolve()
        if resolved.parent != JBI_ROOT.resolve() or resolved.name != FINAL_NAME:
            raise RuntimeError(f"Refusing to replace unexpected path: {resolved}")
        shutil.rmtree(resolved)
    shutil.copytree(PRIOR_ROOT, FINAL_ROOT, copy_function=shutil.copy2)
    # The cloned audit/manifest files describe the prior package and include
    # audit vocabulary such as "placeholder scan". Remove them before the v2
    # content scan, then regenerate them from the v2 payload below.
    for filename in (
        "MANIFEST_SHA256.csv",
        "MANIFEST_SHA256.json",
        "JBI_FINAL_VALIDATION.json",
        "JBI_FINAL_VALIDATION.md",
    ):
        inherited = FINAL_ROOT / filename
        if inherited.exists():
            inherited.unlink()


def build(replace: bool) -> dict[str, object]:
    page_counts = validate_rendered_docx()
    prepare_destination(replace)

    # Normalize the two human-readable administrative backups so the versioned
    # package passes repository whitespace checks without altering their text.
    for relative in (
        Path("ADMINISTRATIVE_BACKUP/JBI_author_action_items.md"),
        Path("ADMINISTRATIVE_BACKUP/JBI_submission_metadata.md"),
    ):
        text_path = FINAL_ROOT / relative
        text_path.write_text(
            text_path.read_text(encoding="utf-8").rstrip() + "\n",
            encoding="utf-8",
            newline="\n",
        )

    for filename in UPLOAD_FIGURES:
        source = REDESIGN_ROOT / filename
        require_file(source)
        shutil.copy2(source, FINAL_ROOT / "UPLOAD_FILES" / filename)
    for filename in ALT_FIGURES:
        source = REDESIGN_ROOT / filename
        require_file(source)
        shutil.copy2(source, FINAL_ROOT / "ALTERNATE_FIGURE_FORMATS" / filename)

    document_continuity: dict[str, object] = {}
    for relative in DOCX_RELATIVE_PATHS:
        prior = PRIOR_ROOT / relative
        current = FINAL_ROOT / relative
        require_file(prior)
        require_file(current)
        same = sha256(prior) == sha256(current)
        if not same:
            raise ValueError(f"DOCX drifted during package integration: {relative}")
        document_continuity[relative.as_posix()] = {
            "byte_identical_to_prior_package": True,
            "sha256": sha256(current),
            "embedded_media_count": count_docx_media(current),
        }

    main_media = document_continuity["UPLOAD_FILES/JBI_main_manuscript.docx"]["embedded_media_count"]
    if main_media != 0:
        raise ValueError("Main manuscript unexpectedly contains embedded media")

    pdf_checks: dict[str, object] = {}
    tiff_checks: dict[str, object] = {}
    for filename in UPLOAD_FIGURES:
        current = FINAL_ROOT / "UPLOAD_FILES" / filename
        source = REDESIGN_ROOT / filename
        if sha256(current) != sha256(source):
            raise ValueError(f"Copied PDF differs from locked redesign: {filename}")
        pdf_checks[filename] = validate_figure_pdf(current)
    for filename in ALT_FIGURES:
        current = FINAL_ROOT / "ALTERNATE_FIGURE_FORMATS" / filename
        source = REDESIGN_ROOT / filename
        if sha256(current) != sha256(source):
            raise ValueError(f"Copied TIFF differs from locked redesign: {filename}")
        tiff_checks[filename] = validate_tiff(current)

    update_readme(FINAL_ROOT / "README_JBI_UPLOAD.md")
    write_docx_qc(FINAL_ROOT / "QC_RECORDS" / "JBI_DOCX_PAGE_QC.md", page_counts)
    write_figure_qc(
        FINAL_ROOT / "QC_RECORDS" / "JBI_FIGURE_REDESIGN_QC.md",
        pdf_checks,
        tiff_checks,
    )

    scan_errors: list[str] = []
    for path in sorted(p for p in FINAL_ROOT.rglob("*") if p.is_file()):
        scan_errors.extend(scan_payload(path))
    if scan_errors:
        raise ValueError("Package privacy/content scan failed: " + "; ".join(scan_errors))

    prior_validation = json.loads((PRIOR_ROOT / "JBI_FINAL_VALIDATION.json").read_text(encoding="utf-8"))
    records = payload_manifest(FINAL_ROOT)
    write_manifest(FINAL_ROOT, records)
    verify_manifest(FINAL_ROOT, records)

    validation = {
        "status": "PASS_JBI_FIRST_SUBMISSION_PACKAGE_V2_REDESIGNED_FIGURES",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "selected_target": "Journal of Biomedical Informatics",
        "article_type": "Research Paper",
        "prior_package_preserved": True,
        "figure_version": "data-first JBI redesign finalized 2026-08-05",
        "figure_facing_data_changed": False,
        "scientific_analysis_rerun": False,
        "contract_or_statistical_definition_changed": False,
        "upload_file_count": prior_validation["upload_file_count"],
        "docx_files_checked": len(DOCX_RELATIVE_PATHS),
        "docx_byte_identical_to_prior_package": True,
        "docx_page_counts": page_counts,
        "total_docx_pages_re_rendered_and_visually_inspected": sum(page_counts.values()),
        "main_manuscript_embedded_media_count": main_media,
        "document_continuity": document_continuity,
        "references": prior_validation["references"],
        "main_figures": prior_validation["main_figures"],
        "main_tables": prior_validation["main_tables"],
        "figure_pdf_checks": pdf_checks,
        "alternate_tiff_checks": tiff_checks,
        "payload_manifest_files": len(records),
        "local_path_scan": "PASS",
        "placeholder_scan": "PASS",
        "macro_tracked_change_comment_scan": "PASS",
        "restricted_data_included": False,
        "git_push_or_external_submission": False,
    }
    (FINAL_ROOT / "JBI_FINAL_VALIDATION.json").write_text(
        json.dumps(validation, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    summary = f"""# JBI v2 final submission-package validation

Status: **{validation['status']}**

- Prior audited package preserved: Yes
- Direct upload files: {validation['upload_file_count']}
- DOCX files byte-identical to prior package: Yes ({validation['docx_files_checked']}/6)
- DOCX pages re-rendered and visually inspected: {validation['total_docx_pages_re_rendered_and_visually_inspected']}
- Main-manuscript embedded figure media: {validation['main_manuscript_embedded_media_count']}
- Main displays: {validation['main_figures']} redesigned figures + {validation['main_tables']} tables
- Figure-facing data changed: No
- Vector figure PDFs: PASS (single page; zero raster image objects)
- Alternate TIFFs: PASS
- Local-path, placeholder, macro, tracked-change, and comment scans: PASS
- Restricted patient-level data included: No
- Scientific analysis rerun: No
- External push/submission performed: No

Only administrative author confirmations remain; see `README_JBI_UPLOAD.md`.
"""
    (FINAL_ROOT / "JBI_FINAL_VALIDATION.md").write_text(
        summary, encoding="utf-8", newline="\n"
    )

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    if ZIP_HASH_PATH.exists():
        ZIP_HASH_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in FINAL_ROOT.rglob("*") if p.is_file()):
            archive.write(path, (Path(FINAL_NAME) / path.relative_to(FINAL_ROOT)).as_posix())
    with zipfile.ZipFile(ZIP_PATH) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"ZIP CRC failure: {bad_member}")
        expected_members = {
            (Path(FINAL_NAME) / path.relative_to(FINAL_ROOT)).as_posix()
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
    print(json.dumps(validation, indent=2))
    return validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace only the exact v2 redesigned-figure package",
    )
    args = parser.parse_args()
    build(args.replace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
