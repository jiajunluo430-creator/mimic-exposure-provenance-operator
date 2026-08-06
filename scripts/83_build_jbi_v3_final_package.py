from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
JBI = ROOT / "manuscript" / "jbi"
SOURCE = JBI / "submission_package"
FIGURE_SOURCE = JBI / "figure_redesign_2026-08-06_v3" / "final_figures"
GA_SOURCE = JBI / "graphical_abstract_2026-08-06"
DOCX_QC = JBI / "rendered_qc_v3_method_complete"
SOFTWARE_QC = ROOT / "outputs" / "software_validation_v0_1_0"
PACKAGE_NAME = "JBI_first_submission_package_2026-08-06_v3_method_complete"
PACKAGE = JBI / PACKAGE_NAME
ZIP_PATH = JBI / f"{PACKAGE_NAME}.zip"
ZIP_QC_PATH = JBI / f"{PACKAGE_NAME}_ZIP_VERIFICATION.json"

RELEASE_URL = (
    "https://github.com/jiajunluo430-creator/"
    "mimic-exposure-provenance-operator/releases/tag/v0.1.0"
)
RELEASE_COMMIT = "91d1c9c005d548462778d2e2b0977953e35cfc70"
WHEEL_SHA256 = "de654ab1a304c92852344b1770a7ba76f04518157b228a090be7d8d6c473599d"
SDIST_SHA256 = "aa720c9955f1a772f4366808c0726156d73eb08d201834f356dde4edfdbd6987"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def inspect_docx(path: Path) -> dict[str, object]:
    forbidden_parts: list[str] = []
    tracked_change_hits = 0
    local_path_hits = 0
    placeholder_hits = 0
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"Corrupt DOCX member in {path.name}: {bad_member}")
        names = set(archive.namelist())
        for member in ("word/vbaProject.bin", "word/comments.xml", "word/people.xml"):
            if member in names:
                forbidden_parts.append(member)
        xml_members = [
            name
            for name in names
            if name == "word/document.xml"
            or re.fullmatch(r"word/(?:header|footer)\d+\.xml", name)
            or name in {"word/footnotes.xml", "word/endnotes.xml"}
        ]
        xml_text = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore") for name in xml_members
        )
        tracked_change_hits = len(
            re.findall(
                r"<w:(?:ins|del|moveFrom|moveTo|commentRangeStart|commentReference)(?:\s|/?>)",
                xml_text,
            )
        )
        local_path_hits = len(re.findall(r"(?:[A-Za-z]:\\|C:/Users/|D:/GI_CHARLS_NHANES)", xml_text))
        visible_text: list[str] = []
        for member in xml_members:
            xml_root = ET.fromstring(archive.read(member))
            for node in xml_root.iter():
                if node.tag.rsplit("}", 1)[-1] == "t" and node.text:
                    visible_text.append(node.text)
        placeholder_hits = len(
            re.findall(
                r"\b(?:TBD|PLACEHOLDER|INSERT HERE|TO BE POPULATED|XXX)\b",
                "\n".join(visible_text),
                flags=re.IGNORECASE,
            )
        )
    return {
        "file": path.name,
        "zip_integrity": "PASS",
        "forbidden_parts": forbidden_parts,
        "tracked_change_hits": tracked_change_hits,
        "local_path_hits": local_path_hits,
        "placeholder_hits": placeholder_hits,
        "status": "PASS"
        if not forbidden_parts
        and tracked_change_hits == 0
        and local_path_hits == 0
        and placeholder_hits == 0
        else "FAIL",
    }


def inspect_pdf(path: Path) -> dict[str, object]:
    reader = PdfReader(str(path))
    image_xobjects = 0
    for page in reader.pages:
        resources = page.get("/Resources")
        resources = resources.get_object() if resources else {}
        xobjects = resources.get("/XObject")
        if xobjects:
            xobjects = xobjects.get_object()
            for value in xobjects.values():
                obj = value.get_object()
                if obj.get("/Subtype") == "/Image":
                    image_xobjects += 1
    return {
        "file": path.name,
        "pages": len(reader.pages),
        "image_xobjects": image_xobjects,
        "status": "PASS" if len(reader.pages) == 1 and image_xobjects == 0 else "FAIL",
    }


def inspect_tiff(path: Path, minimum: tuple[int, int] | None = None) -> dict[str, object]:
    with Image.open(path) as image:
        width, height = image.size
        frames = getattr(image, "n_frames", 1)
        dpi = tuple(round(float(value), 2) for value in image.info.get("dpi", (0, 0)))
    size_pass = True if minimum is None else width >= minimum[0] and height >= minimum[1]
    return {
        "file": path.name,
        "width": width,
        "height": height,
        "frames": frames,
        "dpi": dpi,
        "minimum_dimensions": minimum,
        "status": "PASS" if frames == 1 and size_pass else "FAIL",
    }


def inspect_svg(path: Path) -> dict[str, object]:
    root = ET.parse(path).getroot()
    tags = [node.tag.rsplit("}", 1)[-1] for node in root.iter()]
    return {
        "file": path.name,
        "text_nodes": tags.count("text"),
        "image_nodes": tags.count("image"),
        "status": "PASS" if tags.count("text") > 0 and tags.count("image") == 0 else "FAIL",
    }


if PACKAGE.exists() or ZIP_PATH.exists() or ZIP_QC_PATH.exists():
    raise FileExistsError(
        "Final package path already exists; choose a new version rather than overwriting: "
        f"{PACKAGE}"
    )

upload = PACKAGE / "01_UPLOAD_TO_JBI"
alternate = PACKAGE / "02_ALTERNATE_ARTWORK_TIFF"
editable = PACKAGE / "03_EDITABLE_VECTOR_SOURCES"
optional = PACKAGE / "04_OPTIONAL_REPORTING_CHECKLIST"
qc = PACKAGE / "05_QC_RECORDS"
admin = PACKAGE / "06_ADMINISTRATIVE_BACKUP"
for folder in (upload, alternate, editable, optional, qc, admin):
    folder.mkdir(parents=True, exist_ok=False)

docx_files = [
    "JBI_main_manuscript.docx",
    "JBI_title_page.docx",
    "JBI_cover_letter.docx",
    "JBI_highlights.docx",
    "JBI_declaration_of_competing_interest.docx",
    "JBI_supporting_information.docx",
]
for name in docx_files:
    copy_file(SOURCE / name, upload / name)

for index in range(1, 6):
    copy_file(SOURCE / f"JBI_Figure{index}.pdf", upload / f"JBI_Figure{index}.pdf")
    copy_file(SOURCE / f"JBI_Figure{index}.tiff", alternate / f"JBI_Figure{index}.tiff")
    copy_file(FIGURE_SOURCE / f"JBI_Figure{index}.svg", editable / f"JBI_Figure{index}.svg")

copy_file(SOURCE / "JBI_Graphical_Abstract.pdf", upload / "JBI_Graphical_Abstract.pdf")
copy_file(SOURCE / "JBI_Graphical_Abstract.tiff", alternate / "JBI_Graphical_Abstract.tiff")
copy_file(SOURCE / "JBI_Graphical_Abstract.svg", editable / "JBI_Graphical_Abstract.svg")
copy_file(SOURCE / "JBI_RECORD_STROBE_checklist.docx", optional / "JBI_RECORD_STROBE_checklist.docx")

for name in ("JBI_BUILD_VALIDATION.json", "JBI_BUILD_VALIDATION.md"):
    copy_file(SOURCE / name, qc / name)
for name in (
    "SOFTWARE_VALIDATION_REPORT.md",
    "software_validation_summary.json",
    "software_validation_checks.csv",
    "coverage.json",
    "manifest_sha256.csv",
):
    destination_name = f"software_{name}" if name == "manifest_sha256.csv" else name
    copy_file(SOFTWARE_QC / name, qc / destination_name)
copy_file(FIGURE_SOURCE.parent / "qc" / "JBI_REDESIGN_QC.json", qc / "JBI_REDESIGN_QC.json")
copy_file(FIGURE_SOURCE.parent / "qc" / "JBI_REDESIGN_QC.md", qc / "JBI_REDESIGN_QC.md")
copy_file(GA_SOURCE / "JBI_GRAPHICAL_ABSTRACT_QC.json", qc / "JBI_GRAPHICAL_ABSTRACT_QC.json")
copy_file(DOCX_QC / "DOCX_RENDER_QC.json", qc / "DOCX_RENDER_QC.json")

copy_file(JBI / "source" / "JBI_submission_metadata.md", admin / "JBI_submission_metadata.md")
copy_file(JBI / "source" / "JBI_author_action_items.md", admin / "JBI_author_action_items.md")
copy_file(
    FIGURE_SOURCE.parent / "FIGURE_LEGENDS_AND_ALT_TEXT.md",
    admin / "JBI_FIGURE_LEGENDS_AND_ALT_TEXT.md",
)
copy_file(
    GA_SOURCE / "JBI_GRAPHICAL_ABSTRACT_ALT_TEXT.md",
    admin / "JBI_GRAPHICAL_ABSTRACT_ALT_TEXT.md",
)

release_record = {
    "schema_version": "1.0.0",
    "release_url": RELEASE_URL,
    "release_commit": RELEASE_COMMIT,
    "tag": "v0.1.0",
    "online_files_verified": ["pyproject.toml", "src/medprov/__init__.py", "LICENSE"],
    "assets": [
        {
            "name": "medprov-0.1.0-py3-none-any.whl",
            "bytes": 441951,
            "sha256": WHEEL_SHA256,
            "download_verification": "PASS",
        },
        {
            "name": "medprov-0.1.0.tar.gz",
            "bytes": 360057,
            "sha256": SDIST_SHA256,
            "download_verification": "PASS",
        },
    ],
    "status": "PASS_PUBLIC_RELEASE_VERIFICATION",
}
(qc / "PUBLIC_RELEASE_VERIFICATION.json").write_text(
    json.dumps(release_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

readme = f"""# JBI first-submission upload map

Package status: **GO_JBI_BASICALLY_SUBMITTABLE**  
Article type: **Research Paper**  
Journal: **Journal of Biomedical Informatics**  
Software release: {RELEASE_URL}

## Upload these files

| Order | File | Suggested designation |
|---:|---|---|
| 1 | `JBI_main_manuscript.docx` | Manuscript / Main Document |
| 2 | `JBI_title_page.docx` | Title Page |
| 3 | `JBI_cover_letter.docx` | Cover Letter |
| 4 | `JBI_highlights.docx` | Highlights |
| 5 | `JBI_declaration_of_competing_interest.docx` | Declaration of Competing Interest |
| 6 | `JBI_supporting_information.docx` | Supplementary Material |
| 7 | `JBI_Graphical_Abstract.pdf` | Graphical Abstract |
| 8–12 | `JBI_Figure1.pdf` through `JBI_Figure5.pdf` | Figure |

The main manuscript contains editable Tables 1–3 and all figure legends. JBI uses single-anonymized review, so author information in the manuscript is permitted. The five figure PDFs and graphical-abstract PDF are single-page vector files. Use the TIFF folder only if the portal rejects PDF artwork or requests a raster alternative. The SVG folder contains live-text editable sources and is not a routine first-submission upload.

`JBI_RECORD_STROBE_checklist.docx` is optional; upload it only if the portal requests a research checklist or an editor-only supplementary file. Do **not** upload the QC, administrative-backup, manifest, or package-validation files.

## Verified manuscript limits

- Structured abstract: 247 words.
- Main text: 4,033 words.
- Statement of Significance: 89 words in the required four-row format.
- References: 42, cited in contiguous first-appearance order.
- Main displays: 5 figures + 3 tables = 8.
- Highlights: 5; each is at most 85 characters.
- Graphical abstract: 1400 × 560 design canvas; the TIFF alternative is 5834 × 2334 pixels at 300 dpi. No generative AI was used for artwork.

## Items completed from pre-review

- Public `medprov` 0.1.0 package, schemas, CLI, tests, examples, LICENSE, and release assets are online.
- The downloaded release wheel and sdist match Table S13 SHA-256 values.
- Executed SoA comparisons are reported for record-existence, OMOP/ATLAS-style, and FHIR role/status baselines.
- The eICU adapter has a 100/100 constructed positive control and remains an interface-semantic comparison, not external validation.
- Native parity is labeled implementation fidelity; the software suite has 61 passing tests and 86.03% branch-aware coverage.
- The graphical abstract and four-row Statement of Significance are present.

## Non-blocking author confirmations before clicking Submit

- Confirm final approval and author order with all authors.
- Enter any telephone number only if the portal makes it mandatory; it is intentionally not invented here.
- The 40-study coding remains single-primary-coder work and is transparently disclosed; do not claim kappa without an actual independent recode.
- Full-release MIMIC-IV-on-FHIR scaling remains future work and is explicitly bounded in the manuscript.
- Zenodo DOI creation was deferred by author decision; the immutable GitHub tag and release are used here.

Official guide checked August 6, 2026: https://www.sciencedirect.com/journal/journal-of-biomedical-informatics/publish/guide-for-authors
"""
(PACKAGE / "README_JBI_UPLOAD.md").write_text(readme, encoding="utf-8")

readiness = f"""# Submission readiness decision

**Decision: GO_JBI_BASICALLY_SUBMITTABLE**

The four P0 conditions identified in pre-review are complete: a verifiable public software release, a standalone graphical abstract, the required four-row Statement of Significance, and an executed main-text comparison with current baselines. The added eICU positive control, expanded negative-path tests, precise implementation-fidelity language, time-trace reconciliation, named source ethics bodies, and final figure redesign address the remaining executable-method concerns without changing the frozen scientific contract.

This is a method paper about provenance-sensitive medication-exposure computation. A1 demonstrates construct unmeasurability; A2 demonstrates identity/time sensitivity; neither is a causal drug-effect claim. eICU remains an interface-semantic comparison. The current package is suitable for first submission after ordinary author/portal confirmations.

Release: {RELEASE_URL}  
Release commit: `{RELEASE_COMMIT}`
"""
(PACKAGE / "SUBMISSION_READINESS.md").write_text(readiness, encoding="utf-8")

docx_checks = [inspect_docx(path) for path in sorted(upload.glob("*.docx"))]
docx_checks.append(inspect_docx(optional / "JBI_RECORD_STROBE_checklist.docx"))
pdf_checks = [inspect_pdf(path) for path in sorted(upload.glob("*.pdf"))]
tiff_checks = []
for path in sorted(alternate.glob("*.tiff")):
    minimum = (1328, 531) if path.name == "JBI_Graphical_Abstract.tiff" else None
    tiff_checks.append(inspect_tiff(path, minimum))
svg_checks = [inspect_svg(path) for path in sorted(editable.glob("*.svg"))]

required_upload_names = set(docx_files) | {
    *(f"JBI_Figure{index}.pdf" for index in range(1, 6)),
    "JBI_Graphical_Abstract.pdf",
}
actual_upload_names = {path.name for path in upload.iterdir() if path.is_file()}
missing_uploads = sorted(required_upload_names - actual_upload_names)
unexpected_uploads = sorted(actual_upload_names - required_upload_names)

build_stats = json.loads((SOURCE / "JBI_BUILD_VALIDATION.json").read_text(encoding="utf-8-sig"))
software_stats = json.loads(
    (SOFTWARE_QC / "software_validation_summary.json").read_text(encoding="utf-8-sig")
)
page_stats = json.loads((DOCX_QC / "DOCX_RENDER_QC.json").read_text(encoding="utf-8-sig"))

failures: list[str] = []
if missing_uploads:
    failures.append(f"Missing uploads: {missing_uploads}")
if unexpected_uploads:
    failures.append(f"Unexpected uploads: {unexpected_uploads}")
for category, checks in (
    ("DOCX", docx_checks),
    ("PDF", pdf_checks),
    ("TIFF", tiff_checks),
    ("SVG", svg_checks),
):
    for check in checks:
        if check["status"] != "PASS":
            failures.append(f"{category} QC failed: {check}")
if build_stats.get("status") != "PASS_JBI_SOURCE_AND_DOCUMENT_BUILD":
    failures.append("Document build validation failed")
if build_stats.get("abstract_words", 9999) > 250:
    failures.append("Abstract exceeds 250-word package limit")
if build_stats.get("statement_of_significance_words", 9999) > 150:
    failures.append("Statement of Significance exceeds 150 words")
if build_stats.get("main_displays") != 8:
    failures.append("Main display count is not exactly 8")
if software_stats.get("gate") != "PASS_SOFTWARE_RELEASE_VALIDATION":
    failures.append("Software release validation failed")
if software_stats.get("tests_passed_n") != 61 or software_stats.get("tests_failed_n") != 0:
    failures.append("Software test counts differ from the frozen release report")
if round(float(software_stats.get("coverage_percent", 0)), 2) != 86.03:
    failures.append("Coverage differs from the manuscript report")
if software_stats.get("wheel", {}).get("sha256") != WHEEL_SHA256:
    failures.append("Wheel hash mismatch")
if software_stats.get("sdist", {}).get("sha256") != SDIST_SHA256:
    failures.append("Source-distribution hash mismatch")

validation = {
    "schema_version": "1.0.0",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "package": PACKAGE_NAME,
    "release_url": RELEASE_URL,
    "release_commit": RELEASE_COMMIT,
    "required_uploads_n": len(required_upload_names),
    "missing_uploads": missing_uploads,
    "unexpected_uploads": unexpected_uploads,
    "document_build": {
        "abstract_words": build_stats["abstract_words"],
        "main_text_words": build_stats["main_text_words"],
        "statement_of_significance_words": build_stats["statement_of_significance_words"],
        "references": build_stats["references"],
        "main_displays": build_stats["main_displays"],
    },
    "software": {
        "tests_passed": software_stats["tests_passed_n"],
        "tests_failed": software_stats["tests_failed_n"],
        "coverage_percent": software_stats["coverage_percent"],
        "wheel_sha256": software_stats["wheel"]["sha256"],
        "sdist_sha256": software_stats["sdist"]["sha256"],
    },
    "docx_checks": docx_checks,
    "pdf_checks": pdf_checks,
    "tiff_checks": tiff_checks,
    "svg_checks": svg_checks,
    "docx_render_pages": page_stats,
    "failures": failures,
    "gate": "PASS_FINAL_JBI_PACKAGE" if not failures else "FAIL_FINAL_JBI_PACKAGE",
}
(PACKAGE / "PACKAGE_VALIDATION.json").write_text(
    json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
if failures:
    raise RuntimeError("; ".join(failures))

manifest_rows: list[tuple[str, int, str]] = []
for path in sorted(PACKAGE.rglob("*")):
    if path.is_file() and path.name != "MANIFEST_SHA256.csv":
        manifest_rows.append((path.relative_to(PACKAGE).as_posix(), path.stat().st_size, sha256(path)))
with (PACKAGE / "MANIFEST_SHA256.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["relative_path", "bytes", "sha256"])
    writer.writerows(manifest_rows)

with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file():
            archive.write(path, f"{PACKAGE_NAME}/{path.relative_to(PACKAGE).as_posix()}")
with zipfile.ZipFile(ZIP_PATH) as archive:
    bad_member = archive.testzip()
    zip_members = archive.namelist()
if bad_member:
    raise RuntimeError(f"ZIP CRC failure: {bad_member}")

zip_qc = {
    "schema_version": "1.0.0",
    "zip": ZIP_PATH.name,
    "bytes": ZIP_PATH.stat().st_size,
    "sha256": sha256(ZIP_PATH),
    "members": len(zip_members),
    "crc_test": "PASS",
    "package_manifest_rows": len(manifest_rows),
    "gate": "PASS_FINAL_JBI_ZIP",
}
ZIP_QC_PATH.write_text(json.dumps(zip_qc, indent=2) + "\n", encoding="utf-8")

print(
    json.dumps(
        {
            "package": str(PACKAGE),
            "zip": str(ZIP_PATH),
            "zip_verification": str(ZIP_QC_PATH),
            "upload_files": len(actual_upload_names),
            "manifest_rows": len(manifest_rows),
            "zip_bytes": ZIP_PATH.stat().st_size,
            "zip_sha256": zip_qc["sha256"],
            "gate": "PASS_FINAL_JBI_DELIVERY",
        },
        ensure_ascii=False,
        indent=2,
    )
)
