#!/usr/bin/env python3
"""Build the separate JBI graphical abstract as editable vector artwork.

The graphical abstract is generated programmatically from locked aggregate
results. It contains no patient-level data and uses no generative-image tool.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


BASE_PATH = Path(__file__).with_name("60_make_jbi_figures.py")
SPEC = importlib.util.spec_from_file_location("jbi_figure_base", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load base renderer: {BASE_PATH}")
base = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = base
SPEC.loader.exec_module(base)

Panel = base.Panel
WHITE = "#FFFFFF"
INK = "#1B2733"
MUTED = "#607180"
GRID = "#D9E0E5"
BLUE = "#3F78A8"
NAVY = "#28557D"
TEAL = "#249A8D"
ORANGE = "#E58A28"
PURPLE = "#8066A8"
DARK_GRAY = "#6D7881"
PALE_BLUE = "#EAF2F7"


def build_graphical_abstract() -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    panel = Panel("GA", 1400, 560)
    panel.text(
        "labels",
        36,
        42,
        "Medication exposure is a provenance-sensitive computation",
        size=23,
        weight="bold",
        fill=INK,
        stem="title",
    )
    panel.text(
        "annotations",
        36,
        66,
        "A fail-closed operator preserves the difference between no documented exposure and no measurement capability",
        size=11.5,
        fill=MUTED,
        stem="subtitle",
    )
    panel.line("axis", 36, 84, 1364, 84, stroke=GRID, stroke_width=1.0, stem="title_rule")

    panel.text("labels", 42, 119, "EHR MEDICATION REPRESENTATIONS", size=10.5, weight="bold", fill=NAVY, stem="sources_heading")
    panel.text("labels", 528, 119, "EXECUTABLE PROVENANCE OPERATOR", size=10.5, weight="bold", fill=NAVY, stem="operator_heading")
    panel.text("labels", 984, 119, "FAIL-CLOSED CLASSIFICATION", size=10.5, weight="bold", fill=NAVY, stem="states_heading")

    sources = [
        ("Orders", "treatment intention", BLUE),
        ("Dispensing", "pharmacy workflow", TEAL),
        ("Administration", "documented delivery", ORANGE),
        ("FHIR", "resource roles", TEAL),
        ("OMOP", "DRUG_EXPOSURE", PURPLE),
        ("eICU", "non-equivalent interfaces", ORANGE),
    ]
    for index, (name, detail, color) in enumerate(sources):
        col = index % 2
        row = index // 2
        x = 54 + col * 210
        y = 166 + row * 74
        panel.circle("data", x, y, 7, fill=color, stroke=color, stem=f"source_{index}")
        panel.text("labels", x + 17, y - 2, name, size=12.0, weight="bold", stem=f"source_{index}_name")
        panel.text("annotations", x + 17, y + 17, detail, size=9.2, fill=MUTED, stem=f"source_{index}_detail")

    panel.line("axis", 465, 108, 465, 396, stroke=GRID, stroke_width=1.0, stem="separator_1")
    panel.line("axis", 938, 108, 938, 396, stroke=GRID, stroke_width=1.0, stem="separator_2")
    panel.arrow("data", 414, 242, 505, 242, stroke=DARK_GRAY, stroke_width=1.8, stem="source_to_operator")

    dimensions = [
        ("S", "source", BLUE),
        ("I", "identity", TEAL),
        ("T", "time", ORANGE),
        ("E", "event semantics", PURPLE),
        ("M", "metadata", DARK_GRAY),
    ]
    x_positions = [550, 625, 700, 775, 850]
    panel.line("data", x_positions[0], 196, x_positions[-1], 196, stroke=NAVY, stroke_width=2.0, stem="operator_spine")
    for index, ((symbol, label, color), x) in enumerate(zip(dimensions, x_positions)):
        panel.circle("data", x, 196, 13, fill=WHITE, stroke=color, stroke_width=3.0, stem=f"dimension_{index}")
        panel.text("labels", x, 166, symbol, size=18, weight="bold", fill=color, anchor="middle", stem=f"dimension_{index}_symbol")
        panel.text("labels", x, 230, label, size=9.5, anchor="middle", stem=f"dimension_{index}_label")
    panel.text("annotations", 700, 276, "O = (S, I, T, E, M)", size=12.5, weight="bold", fill=NAVY, anchor="middle", stem="formula")
    panel.text(
        "annotations",
        700,
        303,
        "versioned specification  >  adapter  >  deterministic gates",
        size=10.0,
        fill=MUTED,
        anchor="middle",
        stem="compiler",
    )
    panel.text("annotations", 700, 342, "Native identity retained when available; never inferred when absent", size=10.0, fill=INK, anchor="middle", stem="identity_rule")
    panel.arrow("data", 888, 242, 968, 242, stroke=DARK_GRAY, stroke_width=1.8, stem="operator_to_states")

    states = [
        ("exposed", TEAL),
        ("unexposed", BLUE),
        ("unresolved", ORANGE),
        ("unmeasurable", DARK_GRAY),
    ]
    state_x = [1008, 1117, 1226, 1342]
    for index, ((label, color), x) in enumerate(zip(states, state_x)):
        panel.circle("data", x, 199, 11, fill=color, stroke=color, stem=f"state_{index}")
        panel.text("labels", x, 234, label, size=10.5, weight="bold", fill=color, anchor="middle", stem=f"state_{index}_label")
    panel.text("annotations", 1174, 277, "Missing evidence stays visible", size=11.0, weight="bold", fill=INK, anchor="middle", stem="fail_closed")
    panel.text("annotations", 1174, 301, "It is not silently recoded as unexposed", size=9.8, fill=MUTED, anchor="middle", stem="fail_closed_detail")

    panel.line("axis", 36, 404, 1364, 404, stroke=GRID, stroke_width=1.0, stem="evidence_rule")
    panel.text("labels", 42, 440, "EXECUTED SEMANTIC-LOSS AUDIT", size=10.5, weight="bold", fill=NAVY, stem="audit_heading")
    panel.text("labels", 395, 440, "OMOP", size=10.5, weight="bold", fill=PURPLE, stem="omop_heading")
    panel.text("annotations", 395, 466, "record existence: 37 / 37 exposed", size=10.5, stem="omop_record")
    panel.text("annotations", 395, 490, "strict administration: 37 / 37 unmeasurable", size=10.5, weight="bold", fill=DARK_GRAY, stem="omop_strict")
    panel.text("labels", 825, 440, "FHIR", size=10.5, weight="bold", fill=TEAL, stem="fhir_heading")
    panel.text("annotations", 825, 466, "role / status: 6,697 positive", size=10.5, stem="fhir_role")
    panel.text("annotations", 825, 490, "event semantics: 5,740 strict positive", size=10.5, weight="bold", fill=TEAL, stem="fhir_strict")
    panel.arrow("data", 1224, 466, 1324, 466, stroke=ORANGE, stroke_width=1.8, stem="audit_to_effect")
    panel.text("labels", 1274, 438, "DOWNSTREAM", size=9.8, weight="bold", fill=ORANGE, anchor="middle", stem="downstream_heading")
    panel.text("annotations", 1274, 493, "reclassification and", size=9.6, fill=INK, anchor="middle", stem="downstream_text_1")
    panel.text("annotations", 1274, 511, "effect-estimate drift audit", size=9.6, fill=INK, anchor="middle", stem="downstream_text_2")

    panel.line("annotations", 42, 535, 70, 535, stroke=NAVY, stroke_width=2.0, stem="boundary_rule")
    panel.text("annotations", 80, 539, "Measurement method; no causal efficacy or safety claim", size=9.4, fill=MUTED, stem="boundary")
    return "JBI_Graphical_Abstract", [panel], 1400, 560, [(panel, 0, 0, 1)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output_dir or repo / "manuscript/jbi/graphical_abstract_2026-08-06").resolve()
    output.mkdir(parents=True, exist_ok=True)
    stem, panels, width, height, placements = build_graphical_abstract()
    base.save_figure(output, stem, panels, width, height, placements)
    base.render_preview(output / f"{stem}.pdf", output / f"{stem}.png", output / f"{stem}.tiff")
    svg = base.svg_qc(output / f"{stem}.svg", ["GA"])
    pdf = base.pdf_qc(output / f"{stem}.pdf")
    if svg["status"] != "PASS" or pdf["status"] != "PASS":
        raise RuntimeError(f"Graphical-abstract QC failed: {svg}, {pdf}")
    payload = {
        "status": "PASS_JBI_GRAPHICAL_ABSTRACT",
        "generated_from": "programmatic vector scene; locked aggregate values only",
        "generative_image_used": False,
        "svg": svg,
        "pdf": pdf,
    }
    (output / "JBI_GRAPHICAL_ABSTRACT_QC.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "JBI_GRAPHICAL_ABSTRACT_ALT_TEXT.md").write_text(
        "# Graphical abstract alt text\n\n"
        "Medication orders, dispensing records, documented administrations, FHIR, OMOP, and eICU interfaces feed a five-dimensional provenance operator covering source, identity, time, event semantics, and metadata. The operator returns exposed, unexposed, unresolved, or unmeasurable. An executed OMOP comparison changes 37 of 37 units from record-existence exposure to strict-administration unmeasurability when event state is absent, while an FHIR comparison reduces 6,697 role/status positives to 5,740 strict positives using relocated event semantics. The output supports reclassification and effect-estimate drift audits without making causal drug claims.\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
