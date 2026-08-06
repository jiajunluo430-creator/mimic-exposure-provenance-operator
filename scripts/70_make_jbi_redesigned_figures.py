#!/usr/bin/env python3
"""Render a restrained, data-first redesign of the five JBI main figures.

The script reuses the tested vector scene graph and structural QC from
60_make_jbi_figures.py. It reads only committed aggregate outputs. No patient,
encounter, order, pharmacy, or eMAR identifiers are accessed.

Visual contract:
- white background and square-cornered geometry;
- thin rules, aligned axes, direct labels, and shape plus color encoding;
- no decorative cards, gradients, shadows, or raster elements;
- frozen counts, analysis units, windows, and noncausal claim boundaries.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


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
PALE = "#F5F7F8"
PALE_BLUE = "#EAF2F7"
BLUE = "#3F78A8"
NAVY = "#28557D"
TEAL = "#249A8D"
ORANGE = "#E58A28"
RED = "#C94F4F"
PURPLE = "#8066A8"
GRAY = "#A8B1B8"
DARK_GRAY = "#6D7881"


def header(panel: Panel, title: str, subtitle: str | None = None) -> None:
    panel.text("annotations", 14, 24, panel.letter, size=17, weight="bold", fill=INK, stem="panel_tag")
    panel.text("labels", 42, 24, title, size=14.5, weight="bold", fill=INK, stem="panel_title")
    if subtitle:
        panel.text("labels", 42, 43, subtitle, size=9.5, fill=MUTED, stem="panel_subtitle")
    panel.line("axis", 14, 58, panel.width - 14, 58, stroke=GRID, stroke_width=0.8, stem="header_rule")


def footer_rule(panel: Panel, y: float, text: str, *, color: str = MUTED, stem: str = "footer") -> None:
    panel.line("annotations", 18, y, 42, y, stroke=color, stroke_width=1.8, stem=f"{stem}_rule")
    panel.text("annotations", 50, y + 4, text, size=8.9, fill=MUTED, stem=f"{stem}_text")


def status_glyph(panel: Panel, x: float, y: float, status: str, stem: str) -> None:
    if status == "supported":
        panel.circle("data", x, y, 6.2, fill=TEAL, stroke=TEAL, stroke_width=1.0, stem=f"{stem}_supported")
    elif status == "partial":
        panel.circle("data", x, y, 6.4, fill=WHITE, stroke=ORANGE, stroke_width=2.0, stem=f"{stem}_partial_ring")
        panel.circle("data", x, y, 2.1, fill=ORANGE, stroke=ORANGE, stroke_width=0.5, stem=f"{stem}_partial_dot")
    elif status == "unavailable":
        panel.line("data", x - 5, y - 5, x + 5, y + 5, stroke=DARK_GRAY, stroke_width=1.7, stem=f"{stem}_x1")
        panel.line("data", x - 5, y + 5, x + 5, y - 5, stroke=DARK_GRAY, stroke_width=1.7, stem=f"{stem}_x2")
    else:
        raise ValueError(status)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def figure1() -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    a = Panel("A", 520, 520)
    header(a, "Adapters preserve source role before normalization")
    a.text("labels", 28, 82, "NATIVE REPRESENTATION", size=8.8, weight="bold", fill=MUTED, stem="source_heading")
    a.text("labels", 248, 82, "ADAPTER", size=8.8, weight="bold", fill=MUTED, anchor="middle", stem="adapter_heading")
    a.text("labels", 428, 82, "CANONICAL EVENT", size=8.8, weight="bold", fill=MUTED, anchor="middle", stem="canonical_heading")

    sources = [
        ("Native EHR", "POE / pharmacy / eMAR", "request · dispense · administration", BLUE),
        ("FHIR R4", "MedicationRequest / Dispense", "MedicationAdministration", TEAL),
        ("OMOP CDM", "DRUG_EXPOSURE", "type and source values", PURPLE),
        ("eICU", "medication / infusionDrug", "treatment documentation", ORANGE),
    ]
    ys = [122, 190, 258, 326]
    spine_x = 338
    for idx, (name, line1, line2, color) in enumerate(sources):
        y = ys[idx]
        a.circle("data", 34, y, 4.8, fill=color, stroke=color, stem=f"source_{idx}_marker")
        a.text("labels", 47, y - 4, name, size=11.2, weight="bold", fill=INK, stem=f"source_{idx}_name")
        a.text("labels", 47, y + 14, line1, size=8.9, fill=MUTED, stem=f"source_{idx}_line1")
        a.text("labels", 47, y + 29, line2, size=8.9, fill=MUTED, stem=f"source_{idx}_line2")
        a.line("axis", 28, y + 39, 322, y + 39, stroke=GRID, stroke_width=0.7, stem=f"lane_{idx}_rule")
        a.arrow("axis", 205, y, 316, y, stroke=color, stroke_width=1.5, stem=f"source_{idx}_adapter")
        a.text("labels", 260, y - 8, name.split()[0], size=8.5, fill=color, anchor="middle", stem=f"source_{idx}_adapter_label")
        a.line("axis", 316, y, spine_x, y, stroke=DARK_GRAY, stroke_width=1.0, stem=f"source_{idx}_join")
    a.line("axis", spine_x, ys[0], spine_x, ys[-1], stroke=DARK_GRAY, stroke_width=1.2, stem="canonical_spine")
    a.arrow("axis", spine_x, 224, 360, 224, stroke=NAVY, stroke_width=1.6, stem="spine_to_canonical")

    tx, ty, tw, row_h = 360, 96, 144, 47
    a.rect("axis", tx, ty, tw, row_h * 6, fill=WHITE, stroke=NAVY, stroke_width=1.2, rx=0, stem="canonical_table")
    a.rect("data", tx, ty, tw, row_h, fill=PALE_BLUE, stroke=NAVY, stroke_width=1.0, rx=0, stem="canonical_header")
    a.text("labels", tx + 10, ty + 29, "Canonical medication event", size=10.0, weight="bold", stem="canonical_title")
    fields = [
        ("clinical role", "request / dispense / admin"),
        ("native identity", "retained if available; never inferred"),
        ("event time", "source anchored"),
        ("literal state", "preserved"),
        ("route / dose", "required when construct-bound"),
    ]
    for i, (label, detail) in enumerate(fields):
        y = ty + row_h * (i + 1)
        a.line("axis", tx, y, tx + tw, y, stroke=GRID, stroke_width=0.7, stem=f"canonical_row_{i}")
        a.text("labels", tx + 9, y + 17, label, size=8.8, weight="bold", stem=f"canonical_{i}_label")
        a.text("labels", tx + 9, y + 34, detail, size=7.7, fill=MUTED, stem=f"canonical_{i}_detail")
    footer_rule(a, 454, "Version-gated mappings retain source identity; public outputs remain aggregate-only", color=NAVY, stem="version_note")
    a.text("annotations", 18, 493, "No source is treated as intrinsically superior; each represents a distinct clinical workflow layer.", size=8.8, fill=MUTED, stem="source_boundary")

    b = Panel("B", 520, 520)
    header(b, "Five dimensions compile to explicit terminal states")
    b.text("labels", 24, 84, "OPERATOR", size=8.8, weight="bold", fill=MUTED, stem="operator_heading")
    b.line("axis", 54, 116, 466, 116, stroke=NAVY, stroke_width=1.2, stem="dimension_spine")
    dims = [("S", "source", BLUE), ("I", "identity", TEAL), ("T", "time", ORANGE), ("E", "event semantics", PURPLE), ("M", "metadata", DARK_GRAY)]
    dxs = [60, 160, 260, 360, 460]
    for i, ((symbol, label, color), x) in enumerate(zip(dims, dxs)):
        b.circle("data", x, 116, 7.0, fill=WHITE, stroke=color, stroke_width=2.0, stem=f"dimension_{symbol}")
        b.text("labels", x, 96, symbol, size=14.0, weight="bold", fill=color, anchor="middle", stem=f"dimension_{symbol}_symbol")
        b.text("labels", x, 143, label, size=8.6, fill=INK, anchor="middle", stem=f"dimension_{symbol}_label")
    b.text("annotations", 260, 166, "O = (S, I, T, E, M)", size=9.0, fill=MUTED, anchor="middle", stem="operator_formula")

    b.text("labels", 24, 194, "VALIDATION CHAIN", size=8.8, weight="bold", fill=MUTED, stem="validation_heading")
    stages = ["syntax", "adapter", "measurable", "executable", "traceable"]
    sxs = [60, 160, 260, 360, 460]
    b.line("axis", 60, 220, 460, 220, stroke=GRAY, stroke_width=1.1, stem="validation_spine")
    for i, (label, x) in enumerate(zip(stages, sxs)):
        b.circle("data", x, 220, 4.2, fill=NAVY if i < 4 else WHITE, stroke=NAVY, stroke_width=1.3, stem=f"gate_{i}")
        b.text("labels", x, 244, label, size=8.5, anchor="middle", stem=f"gate_{i}_label")
    b.arrow("axis", 260, 260, 260, 284, stroke=DARK_GRAY, stroke_width=1.2, stem="gates_to_states")

    state_xs = [64, 190, 322, 456]
    states = [("exposed", TEAL), ("unexposed", BLUE), ("unresolved", ORANGE), ("unmeasurable", DARK_GRAY)]
    b.line("axis", state_xs[0], 304, state_xs[-1], 304, stroke=GRAY, stroke_width=1.0, stem="state_branch")
    for i, ((label, color), x) in enumerate(zip(states, state_xs)):
        b.line("axis", x, 304, x, 318, stroke=GRAY, stroke_width=1.0, stem=f"state_{i}_drop")
        b.circle("data", x, 326, 6.0, fill=color, stroke=color, stem=f"state_{i}_marker")
        b.text("labels", x, 350, label, size=9.2, weight="bold", fill=color, anchor="middle", stem=f"state_{i}_label")
    b.text("annotations", 260, 374, "Missing capability remains visible; it is never silently relabeled as unexposed.", size=8.8, fill=MUTED, anchor="middle", stem="fail_closed_note")

    b.line("axis", 260, 400, 260, 482, stroke=GRID, stroke_width=1.0, stem="output_divider")
    b.text("labels", 28, 414, "AGGREGATE COMPARISON", size=9.1, weight="bold", fill=BLUE, stem="aggregate_title")
    b.text("labels", 28, 438, "classification retention", size=8.8, stem="aggregate_1")
    b.text("labels", 28, 456, "reclassification · timing · semantic loss", size=8.8, stem="aggregate_2")
    b.text("labels", 282, 414, "DOWNSTREAM STRESS TEST", size=9.1, weight="bold", fill=ORANGE, stem="stress_title")
    b.text("labels", 282, 438, "paired exposure cohorts", size=8.8, stem="stress_1")
    b.text("labels", 282, 456, "effect-estimate drift · no causal drug claim", size=8.8, stem="stress_2")
    b.text("annotations", 260, 505, "C(u) is deterministic for each prespecified analysis unit.", size=8.8, fill=MUTED, anchor="middle", stem="deterministic_note")
    return "JBI_Figure1", [a, b], 1060, 520, [(a, 0, 0, 1), (b, 540, 0, 1)]


def figure2(repo: Path, data_dir: Path) -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    parity = base.read_tsv(repo / "outputs/method_evaluation_v0_1_0/tables/mimic_six_class_parity.tsv")
    ablation = base.read_tsv(repo / "outputs/method_evaluation_v0_1_0/tables/operator_ablation_matrix.tsv")
    write_csv(data_dir / "Figure2_native_parity.csv", parity)
    write_csv(data_dir / "Figure2_ablation.csv", ablation)

    a = Panel("A", 530, 500)
    header(a, "Native outputs reproduce the frozen six-class benchmark", "Expected counts versus medprov 0.1.0 output")
    x0, y0, w, h = 78, 84, 395, 330
    lo, hi = 3.0, 5.2

    def sx(value: float) -> float:
        return x0 + (math.log10(value) - lo) / (hi - lo) * w

    def sy(value: float) -> float:
        return y0 + h - (math.log10(value) - lo) / (hi - lo) * h

    for tick in (1_000, 10_000, 100_000):
        x, y = sx(tick), sy(tick)
        a.line("axis", x, y0, x, y0 + h, stroke=GRID, stroke_width=0.7, stem=f"xgrid_{tick}")
        a.line("axis", x0, y, x0 + w, y, stroke=GRID, stroke_width=0.7, stem=f"ygrid_{tick}")
        label = f"10^{int(math.log10(tick))}"
        a.text("labels", x, y0 + h + 22, label, size=9.2, fill=MUTED, anchor="middle", stem=f"xtick_{tick}")
        a.text("labels", x0 - 10, y + 4, label, size=9.2, fill=MUTED, anchor="end", stem=f"ytick_{tick}")
    a.line("axis", x0, y0 + h, x0 + w, y0 + h, stroke=INK, stroke_width=1.0, stem="x_axis")
    a.line("axis", x0, y0, x0, y0 + h, stroke=INK, stroke_width=1.0, stem="y_axis")
    a.line("axis", sx(10**lo), sy(10**lo), sx(10**hi), sy(10**hi), stroke=DARK_GRAY, stroke_width=1.1, dash="5,4", stem="identity")

    categories = [
        ("orders", "expected_orders_n", "actual_orders_n", BLUE, "circle"),
        ("strict administration", "expected_strict_n", "actual_strict_n", ORANGE, "square"),
        ("same class/window", "expected_broad_n", "actual_broad_n", TEAL, "diamond"),
    ]
    for label, expected_key, actual_key, color, shape in categories:
        for row in parity:
            x, y = sx(float(row[expected_key])), sy(float(row[actual_key]))
            stem = f"{label}_{row['drug_class']}"
            if shape == "circle":
                a.circle("data", x, y, 4.7, fill=color, stroke=WHITE, stroke_width=1.0, stem=stem)
            elif shape == "square":
                a.rect("data", x - 4.5, y - 4.5, 9, 9, fill=color, stroke=WHITE, stroke_width=1.0, rx=0, stem=stem)
            else:
                a.polygon("data", [(x, y - 5.5), (x + 5.5, y), (x, y + 5.5), (x - 5.5, y)], fill=color, stroke=WHITE, stroke_width=1.0, stem=stem)
    a.text("annotations", 466, 96, "19 / 19 checks passed", size=10.4, weight="bold", fill=TEAL, anchor="end", stem="parity_note")
    a.text("labels", x0 + w / 2, 458, "Frozen expected count (log scale)", size=10.8, anchor="middle", stem="x_title")
    a.text("labels", 18, 252, "medprov count", size=10.8, stem="y_title")
    for i, (label, _, _, color, shape) in enumerate(categories):
        x = 92 + i * 145
        if shape == "circle":
            a.circle("legend", x, 485, 4.4, fill=color, stroke=color, stem=f"legend_{i}")
        elif shape == "square":
            a.rect("legend", x - 4.3, 480.7, 8.6, 8.6, fill=color, stroke=color, rx=0, stem=f"legend_{i}")
        else:
            a.polygon("legend", [(x, 480), (x + 5, 485), (x, 490), (x - 5, 485)], fill=color, stroke=color, stem=f"legend_{i}")
        a.text("legend", x + 10, 489, label, size=8.7, stem=f"legend_{i}_label")

    b = Panel("B", 530, 500)
    header(b, "Ablation localizes information added by the operator", "Exposed proportion within the prespecified anchor cohorts")
    keep_labels = ["table only", "source + class + window", "collapsed event semantics", "full exact identity"]
    rows = {(r["anchor"], r["operator_label"]): r for r in ablation if r["anchor"] in {"A1", "A2"}}
    keys = ["table-only", "source+class+window", "collapsed event semantics", "full exact-identity operator"]
    px0, py0, pw = 210, 98, 270
    for tick in (0, 25, 50, 75, 100):
        x = px0 + pw * tick / 100
        b.line("axis", x, py0, x, 360, stroke=GRID, stroke_width=0.7, stem=f"grid_{tick}")
        b.text("labels", x, 383, f"{tick}%", size=8.9, fill=MUTED, anchor="middle", stem=f"tick_{tick}")
    b.line("axis", px0, 360, px0 + pw, 360, stroke=INK, stroke_width=1.0, stem="x_axis")
    ys = [120, 190, 260, 330]
    for i, (label, y) in enumerate(zip(keep_labels, ys)):
        b.text("labels", 22, y + 4, label, size=9.2, stem=f"operator_{i}")
        if i < 3:
            b.line("axis", 22, y + 31, 480, y + 31, stroke=GRID, stroke_width=0.6, stem=f"row_rule_{i}")
    anchor_styles = [("A1", 20248, BLUE, -5), ("A2", 2813, TEAL, 5)]
    for anchor, n, color, yoff in anchor_styles:
        points: list[tuple[float, float, float]] = []
        for i, key in enumerate(keys):
            row = rows[(anchor, key)]
            pct = int(row["exposed_n"]) / int(row["analysis_units_n"]) * 100
            x, y = px0 + pw * pct / 100, ys[i] + yoff
            points.append((x, y, pct))
        for i in range(len(points) - 1):
            b.line("data", points[i][0], points[i][1], points[i + 1][0], points[i + 1][1], stroke=color, stroke_width=1.4, stem=f"{anchor}_segment_{i}")
        for i, (x, y, pct) in enumerate(points):
            b.circle("data", x, y, 4.8, fill=color, stroke=WHITE, stroke_width=1.0, stem=f"{anchor}_point_{i}")
            b.text("annotations", x + 7, y + (0 if anchor == "A1" else 9), f"{pct:.1f}%", size=8.5, fill=color, stem=f"{anchor}_pct_{i}")
        b.text("legend", 478, points[0][1] + 3, f"{anchor} (n={n:,})", size=9.2, weight="bold", fill=color, anchor="end", stem=f"{anchor}_direct_label")
    footer_rule(b, 420, "Route-required A1 administration: 20,248 / 20,248 units were unmeasurable", color=DARK_GRAY, stem="route_note")
    b.text("annotations", 50, 448, "Required eMAR route was absent; the fail-closed operator did not relabel units as unexposed.", size=8.7, fill=MUTED, stem="route_detail")
    b.text("annotations", 265, 484, "Ablations remove prespecified information; they are not replacement exposure definitions.", size=8.7, fill=MUTED, anchor="middle", stem="ablation_boundary")
    return "JBI_Figure2", [a, b], 1080, 500, [(a, 0, 0, 1), (b, 550, 0, 1)]


def figure3(repo: Path, data_dir: Path) -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    fhir = base.read_json(repo / "outputs/transport_evaluation_v0_1_0/fhir_transport_summary.json")
    fhir_composite = base.read_csv(repo / "outputs/transport_evaluation_v0_1_0/fhir_administration_composite_pairing.csv")
    omop = base.read_json(repo / "outputs/omop_evaluation_v0_1_0/omop_evaluation_summary.json")
    eicu = base.read_json(repo / "outputs/eicu_transport_v0_1_0/eicu_transport_summary.json")
    (data_dir / "Figure3_transport_summary.json").write_text(json.dumps({"fhir": fhir, "omop": omop, "eicu": eicu}, indent=2, sort_keys=True), encoding="utf-8")

    a = Panel("A", 1040, 300)
    header(a, "Representation capability is dimension-specific", "Shape and color encode supported, partial or relocated, and structurally unavailable capabilities")
    cols = ["Source role", "Native identity", "Time", "Event semantics", "Route / dose", "Four-state output"]
    rows = [
        ("MIMIC-IV 3.1 native", ["supported", "supported", "supported", "supported", "partial", "supported"]),
        ("Matched native / FHIR demos", ["supported", "partial", "partial", "partial", "partial", "supported"]),
        ("MIMIC OMOP demo", ["partial", "partial", "supported", "unavailable", "partial", "supported"]),
        ("eICU 2.0", ["partial", "unavailable", "partial", "partial", "partial", "supported"]),
    ]
    x0, cell_w = 278, 118
    ys = [112, 158, 204, 250]
    for j, col in enumerate(cols):
        a.text("labels", x0 + j * cell_w, 82, col, size=9.0, weight="bold", anchor="middle", stem=f"col_{j}")
    for i, (row_label, statuses) in enumerate(rows):
        y = ys[i]
        a.rect("axis", 20, y - 19, 982, 38, fill=PALE if i % 2 else WHITE, stroke=WHITE, stroke_width=0, rx=0, stem=f"row_band_{i}")
        a.line("axis", 20, y + 20, 1002, y + 20, stroke=GRID, stroke_width=0.6, stem=f"row_rule_{i}")
        a.text("labels", 245, y + 4, row_label, size=9.7, weight="bold" if i == 0 else "normal", anchor="end", stem=f"row_{i}_label")
        for j, status in enumerate(statuses):
            status_glyph(a, x0 + j * cell_w, y, status, f"cell_{i}_{j}")
    legend = [("supported", "supported"), ("partial / relocated", "partial"), ("unavailable", "unavailable")]
    for i, (label, status) in enumerate(legend):
        x = 304 + i * 175
        status_glyph(a, x, 285, status, f"legend_{i}")
        a.text("legend", x + 14, 289, label, size=8.7, stem=f"legend_{i}_label")
    a.text("annotations", 1010, 289, "Capabilities are not a rank or superiority score", size=8.7, fill=MUTED, anchor="end", stem="capability_boundary")

    b = Panel("B", 510, 390)
    header(b, "Matched-demo FHIR concordance is high but incomplete")
    native_linkable = sum(int(row["native_linkable_events_n"]) for row in fhir_composite)
    composite_pct = fhir["headline_findings"]["admin_composite_matches_n"] / native_linkable * 100
    metrics = [
        ("Dispense ID × class", 100.0, "3,870 / 3,870 exact"),
        ("Request time", 100.0, "2,249 / 2,249 exact"),
        ("First administration time", 1347 / 1353 * 100, "1,347 / 1,353 exact"),
        ("Administration composite", composite_pct, f"5,220 / {native_linkable:,} native-linkable"),
    ]
    px0, pw = 228, 240
    for tick in (0, 25, 50, 75, 100):
        x = px0 + pw * tick / 100
        b.line("axis", x, 82, x, 304, stroke=GRID, stroke_width=0.7, stem=f"grid_{tick}")
        b.text("labels", x, 326, f"{tick}%", size=8.8, fill=MUTED, anchor="middle", stem=f"tick_{tick}")
    b.line("axis", px0, 304, px0 + pw, 304, stroke=INK, stroke_width=1.0, stem="x_axis")
    for i, (label, pct, detail) in enumerate(metrics):
        y = 104 + i * 55
        color = BLUE if i < 3 else TEAL
        b.text("labels", 18, y + 4, label, size=9.3, stem=f"metric_{i}_label")
        b.line("data", px0, y, px0 + pw * pct / 100, y, stroke=color, stroke_width=1.6, stem=f"metric_{i}_stem")
        b.circle("data", px0 + pw * pct / 100, y, 5.3, fill=color, stroke=WHITE, stroke_width=1.0, stem=f"metric_{i}_point")
        b.text("annotations", px0 + pw * pct / 100 - 7, y - 10, f"{pct:.1f}%", size=8.7, weight="bold", fill=color, anchor="end", stem=f"metric_{i}_pct")
        b.text("annotations", px0, y + 22, detail, size=8.2, fill=MUTED, stem=f"metric_{i}_detail")
    footer_rule(b, 350, "Native eMAR identifiers were not retained in FHIR administration resources", color=ORANGE, stem="fhir_identifier_note")
    b.text("annotations", 18, 382, "Matched public demonstrations support functional evaluation, not full-release validation.", size=8.6, fill=MUTED, stem="fhir_boundary")

    c = Panel("C", 510, 390)
    header(c, "Fail-closed states make semantic loss observable")
    state_colors = {"exposed": TEAL, "unexposed": BLUE, "unresolved": ORANGE, "unmeasurable": DARK_GRAY}
    bars = [
        ("OMOP demo: strict administration", {"exposed": 0, "unexposed": 0, "unresolved": 0, "unmeasurable": 37}),
        ("OMOP synthetic: extension present", {"exposed": 1, "unexposed": 1, "unresolved": 1, "unmeasurable": 1}),
        ("eICU full interface comparison", eicu["counts"]),
    ]
    px0, pw = 36, 430
    for i, (label, counts) in enumerate(bars):
        y = 102 + i * 78
        total = sum(int(counts.get(state, 0)) for state in state_colors)
        c.text("labels", px0, y - 12, label, size=9.5, weight="bold", stem=f"bar_{i}_label")
        c.text("annotations", px0 + pw, y - 12, f"n={total:,}", size=8.3, fill=MUTED, anchor="end", stem=f"bar_{i}_denominator")
        cursor = px0
        for state, color in state_colors.items():
            value = int(counts.get(state, 0))
            if value == 0:
                continue
            bw = pw * value / total
            c.rect("data", cursor, y, bw, 24, fill=color, stroke=WHITE, stroke_width=0.8, rx=0, stem=f"bar_{i}_{state}")
            if bw > 50:
                c.text("annotations", cursor + bw / 2, y + 17, f"{value / total * 100:.1f}%", size=8.7, weight="bold", fill=WHITE, anchor="middle", stem=f"bar_{i}_{state}_pct")
            cursor += bw
        c.line("axis", px0, y + 25, px0 + pw, y + 25, stroke=INK, stroke_width=0.7, stem=f"bar_{i}_axis")
    for i, (state, color) in enumerate(state_colors.items()):
        x = 28 + i * 119
        c.rect("legend", x, 335, 10, 10, fill=color, stroke=color, rx=0, stem=f"legend_{state}")
        c.text("legend", x + 15, 344, state, size=8.3, stem=f"legend_{state}_label")
    c.text("annotations", 25, 380, "eICU: 3 / 6 medication-class reconciliation gates passed; no native cross-source key.", size=8.6, fill=MUTED, stem="eicu_boundary")
    return "JBI_Figure3", [a, b, c], 1040, 710, [(a, 0, 0, 1), (b, 0, 320, 1), (c, 530, 320, 1)]


def figure4(repo: Path, data_dir: Path) -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    result = base.read_json(repo / "outputs/literature_validator_v0_1_0/literature_validator_result.json")
    summary = base.read_tsv(repo / "outputs/literature_validator_v0_1_0/tables/reporting_dimension_summary.tsv")
    write_csv(data_dir / "Figure4_reporting_dimensions.csv", summary)
    distribution = Counter(int(row["reported_dimensions_n"]) for row in result["records"])
    dist_rows = [{"reported_dimensions_n": str(key), "studies_n": str(distribution.get(key, 0))} for key in range(6)]
    write_csv(data_dir / "Figure4_reported_dimension_distribution.csv", dist_rows)

    a = Panel("A", 610, 470)
    header(a, "Published reports leave provenance dimensions underspecified", "Structured validator over 40 human-coded MIMIC medication studies")
    labels = {
        "source_layer": "Named native source",
        "identity_rule": "Executable identity rule",
        "time_origin_window": "Time origin / window",
        "event_semantics_map": "Native event semantics",
        "required_metadata": "Dose / route requirement",
    }
    px0, py0, pw = 218, 96, 330
    for tick in (0, 25, 50, 75, 100):
        x = px0 + pw * tick / 100
        a.line("axis", x, py0, x, 354, stroke=GRID, stroke_width=0.7, stem=f"grid_{tick}")
        a.text("labels", x, 378, f"{tick}%", size=8.8, fill=MUTED, anchor="middle", stem=f"tick_{tick}")
    a.line("axis", px0, 354, px0 + pw, 354, stroke=INK, stroke_width=1.0, stem="x_axis")
    for i, row in enumerate(summary):
        y = 112 + i * 52
        reported, sample = int(row["reported_n"]), int(row["sample_n"])
        pct = reported / sample * 100
        color = RED if reported == 0 else (ORANGE if pct < 25 else TEAL)
        a.text("labels", px0 - 15, y + 4, labels[row["dimension"]], size=9.7, anchor="end", stem=f"label_{i}")
        a.line("data", px0, y, px0 + pw * pct / 100, y, stroke=color, stroke_width=1.6, stem=f"stem_{i}")
        if reported == 0:
            a.line("data", px0 - 4, y - 4, px0 + 4, y + 4, stroke=color, stroke_width=1.6, stem=f"zero_{i}_a")
            a.line("data", px0 - 4, y + 4, px0 + 4, y - 4, stroke=color, stroke_width=1.6, stem=f"zero_{i}_b")
        else:
            a.circle("data", px0 + pw * pct / 100, y, 5.2, fill=color, stroke=WHITE, stroke_width=1.0, stem=f"point_{i}")
        a.text("annotations", px0 + pw * pct / 100 + 9, y + 4, f"{reported}/40", size=9.5, weight="bold", fill=color, stem=f"count_{i}")
    footer_rule(a, 415, "Main texts, 55 / 56 linked supplements, and 3 article-specific repositories were searched", color=NAVY, stem="scope")
    a.text("annotations", 20, 453, "Single-coded input; the validator reproduces the codebook deterministically but does not replace human review.", size=8.6, fill=MUTED, stem="coding_boundary")

    b = Panel("B", 430, 470)
    header(b, "Executability collapses across reporting gates")
    steps = [("Studies", 40, NAVY), ("Native\nsource", 7, BLUE), ("Identity\nrule", 2, ORANGE), ("Event\nsemantics", 0, RED), ("Complete\noperator", 0, DARK_GRAY)]
    x_positions = [48, 127, 206, 285, 364]
    y_top, y_bottom = 86, 268
    for tick in (0, 10, 20, 30, 40):
        y = y_bottom - (y_bottom - y_top) * tick / 40
        b.line("axis", 42, y, 378, y, stroke=GRID, stroke_width=0.7, stem=f"ygrid_{tick}")
        b.text("labels", 32, y + 4, str(tick), size=8.2, fill=MUTED, anchor="end", stem=f"ytick_{tick}")
    b.line("axis", 42, y_top, 42, y_bottom, stroke=INK, stroke_width=1.0, stem="y_axis")
    points: list[tuple[float, float]] = []
    for i, (label, value, color) in enumerate(steps):
        x = x_positions[i]
        y = y_bottom - (y_bottom - y_top) * value / 40
        points.append((x, y))
        if i > 0:
            b.line("data", points[i - 1][0], points[i - 1][1], x, y, stroke=GRAY, stroke_width=1.4, stem=f"gate_segment_{i}")
        b.circle("data", x, y, 5.8, fill=color, stroke=WHITE, stroke_width=1.0, stem=f"gate_{i}")
        b.text("annotations", x, y - 12, f"{value}/40", size=8.8, weight="bold", fill=color, anchor="middle", stem=f"gate_{i}_value")
        parts = label.split("\n")
        b.text("labels", x, 286, parts[0], size=8.0, anchor="middle", stem=f"gate_{i}_label_1")
        if len(parts) > 1:
            b.text("labels", x, 299, parts[1], size=8.0, anchor="middle", stem=f"gate_{i}_label_2")

    b.text("labels", 28, 332, "REPORTED DIMENSIONS PER STUDY", size=8.8, weight="bold", fill=MUTED, stem="distribution_title")
    max_count = max(distribution.values())
    for key in range(6):
        count = distribution.get(key, 0)
        x = 47 + key * 59
        h = 62 * count / max_count if max_count else 0
        b.rect("data", x, 425 - h, 28, h, fill=PURPLE, stroke=PURPLE, stroke_width=0.8, rx=0, stem=f"dist_{key}")
        b.text("labels", x + 14, 444, str(key), size=8.6, anchor="middle", stem=f"dist_{key}_label")
        b.text("annotations", x + 14, 418 - h, str(count), size=8.2, anchor="middle", stem=f"dist_{key}_count")
    b.line("axis", 40, 425, 390, 425, stroke=INK, stroke_width=0.8, stem="dist_axis")
    return "JBI_Figure4", [a, b], 1060, 470, [(a, 0, 0, 1), (b, 630, 0, 1)]


def figure5(repo: Path, data_dir: Path) -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    reclass = base.read_tsv(repo / "outputs/method_evaluation_v0_1_0/tables/operator_reclassification_metrics.tsv")
    reclass = [row for row in reclass if row["comparison"] == "exact_identity_vs_same_class"]
    effects = base.read_csv(repo / "figures/data/Figure4C_operator_effects.csv")
    write_csv(data_dir / "Figure5_reclassification.csv", reclass)
    selected_keys = [
        ("A1", "original_strict", "A1 · exact identity"),
        ("A1", "original_broad", "A1 · same class/window"),
        ("A2", "original_strict", "A2 · original exact identity"),
        ("A2", "original_broad", "A2 · original same class/window"),
        ("A2", "hospital_overlap_strict", "A2 · hospital-overlap exact identity"),
        ("A2", "hospital_overlap_broad", "A2 · hospital-overlap same class/window"),
    ]
    selected_effects = [row for row in effects if row["model_variant"] == "published_style_minimal" and any(row["anchor_id"] == a and row["operator"] == o for a, o, _ in selected_keys)]
    write_csv(data_dir / "Figure5_effects.csv", selected_effects)

    a = Panel("A", 420, 540)
    header(a, "Identity simplification reclassifies exposure", "Exact identity versus same-class/window administration")
    segments = [("both positive", TEAL), ("same-class only", ORANGE), ("both negative", GRAY)]
    x0, w = 34, 350
    for i, row in enumerate(reclass):
        y = 116 + i * 126
        anchor, total = row["anchor"], int(row["analysis_units_n"])
        counts = [int(row["both_positive_n"]), int(row["right_only_n"]), int(row["both_negative_n"])]
        a.text("labels", x0, y - 20, f"{anchor} (n={total:,})", size=11.0, weight="bold", stem=f"anchor_{anchor}")
        cursor = x0
        for (label, color), count in zip(segments, counts):
            bw = w * count / total
            a.rect("data", cursor, y, bw, 34, fill=color, stroke=WHITE, stroke_width=0.8, rx=0, stem=f"{anchor}_{label}")
            if bw > 36:
                a.text("annotations", cursor + bw / 2, y + 22, f"{count / total * 100:.1f}%", size=9.0, weight="bold", fill=WHITE, anchor="middle", stem=f"{anchor}_{label}_pct")
            cursor += bw
        a.line("axis", x0, y + 35, x0 + w, y + 35, stroke=INK, stroke_width=0.7, stem=f"axis_{anchor}")
        a.text("annotations", x0, y + 61, f"Positive Jaccard = {float(row['positive_jaccard']):.3f}", size=9.2, fill=MUTED, stem=f"jaccard_{anchor}")
    for i, (label, color) in enumerate(segments):
        x = 34 + i * 122
        a.rect("legend", x, 378, 10, 10, fill=color, stroke=color, rx=0, stem=f"legend_{i}")
        a.text("legend", x + 15, 387, label, size=8.5, stem=f"legend_{i}_label")
    footer_rule(a, 440, "Construct measurability is independent of reclassification", color=DARK_GRAY, stem="construct_note")
    a.text("annotations", 50, 466, "A1 route: order 9,940 / 9,940 available; eMAR 0 / 87,569.", size=8.8, fill=MUTED, stem="construct_detail")
    a.text("annotations", 210, 523, "Same-class/window is a prespecified ablation, not a replacement definition.", size=8.5, fill=MUTED, anchor="middle", stem="reclass_boundary")

    b = Panel("B", 690, 540)
    header(b, "Operator changes propagate selectively to paired estimates", "Identical cohort, outcome, and covariates within each published-style pair")
    px0, pw = 270, 340
    xmin, xmax = math.log(0.75), math.log(2.4)

    def sx(value: float) -> float:
        return px0 + (math.log(value) - xmin) / (xmax - xmin) * pw

    for tick in (0.75, 1.0, 1.5, 2.0):
        x = sx(tick)
        b.line("axis", x, 82, x, 438, stroke=INK if tick == 1.0 else GRID, stroke_width=1.2 if tick == 1.0 else 0.7, stem=f"grid_{tick}")
        b.text("labels", x, 462, f"{tick:g}", size=8.8, fill=MUTED, anchor="middle", stem=f"tick_{tick}")
    by_key = {(row["anchor_id"], row["operator"], row["exposure_source"]): row for row in selected_effects}
    ys = [104, 159, 226, 281, 348, 403]
    b.text("labels", 18, 82, "A1", size=9.0, weight="bold", fill=MUTED, stem="group_a1")
    b.text("labels", 18, 204, "A2", size=9.0, weight="bold", fill=MUTED, stem="group_a2")
    for i, ((anchor, operator, label), y) in enumerate(zip(selected_keys, ys)):
        b.line("axis", 18, y + 26, 672, y + 26, stroke=GRID, stroke_width=0.5, stem=f"row_rule_{i}")
        b.text("labels", px0 - 14, y + 4, label, size=8.8, anchor="end", stem=f"row_{i}_label")
        order = by_key[(anchor, operator, "order")]
        admin = by_key[(anchor, operator, "administration")]
        ox, ax = sx(float(order["effect"])), sx(float(admin["effect"]))
        b.line("data", ox, y, ax, y, stroke=GRAY, stroke_width=1.8, stem=f"pair_{i}")
        for source, row, color, yy in (("order", order, BLUE, y - 4.5), ("administration", admin, ORANGE, y + 4.5)):
            low, high, effect = float(row["ci_low"]), float(row["ci_high"]), float(row["effect"])
            b.line("data", sx(low), yy, sx(high), yy, stroke=color, stroke_width=1.5, stem=f"ci_{i}_{source}")
            b.line("data", sx(low), yy - 3.5, sx(low), yy + 3.5, stroke=color, stroke_width=1.0, stem=f"ci_low_{i}_{source}")
            b.line("data", sx(high), yy - 3.5, sx(high), yy + 3.5, stroke=color, stroke_width=1.0, stem=f"ci_high_{i}_{source}")
            b.circle("data", sx(effect), yy, 4.6, fill=color, stroke=WHITE, stroke_width=0.8, stem=f"point_{i}_{source}")
        delta = abs(math.log(float(admin["effect"])) - math.log(float(order["effect"])))
        b.text("annotations", 678, y + 4, f"|Δ log| {delta:.3f}", size=8.0, fill=MUTED, anchor="end", stem=f"delta_{i}")
    b.text("labels", px0 + pw / 2, 488, "Paired OR or HR (log scale)", size=10.4, anchor="middle", stem="x_title")
    b.circle("legend", 314, 513, 4.4, fill=BLUE, stroke=BLUE, stem="legend_order")
    b.text("legend", 327, 517, "order-defined", size=8.7, stem="legend_order_label")
    b.circle("legend", 442, 513, 4.4, fill=ORANGE, stroke=ORANGE, stem="legend_admin")
    b.text("legend", 455, 517, "administration-defined", size=8.7, stem="legend_admin_label")
    b.text("annotations", 345, 538, "Measurement stress tests only; estimates are not causal drug effects.", size=8.5, fill=MUTED, anchor="middle", stem="claim_boundary")
    return "JBI_Figure5", [a, b], 1130, 540, [(a, 0, 0, 1), (b, 440, 0, 1)]


def style_template() -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    a = Panel("A", 900, 520)
    header(a, "JBI data-first figure template", "Reusable visual grammar for architecture, capability, and quantitative evidence")
    a.text("labels", 24, 86, "1  PROCESS SPINE", size=9.2, weight="bold", fill=NAVY, stem="process_title")
    nodes = [("native source", BLUE), ("adapter", TEAL), ("canonical event", NAVY), ("four-state output", ORANGE)]
    xs = [55, 175, 310, 455]
    a.line("axis", xs[0], 132, xs[-1], 132, stroke=GRAY, stroke_width=1.2, stem="template_spine")
    for i, ((label, color), x) in enumerate(zip(nodes, xs)):
        a.circle("data", x, 132, 6, fill=WHITE, stroke=color, stroke_width=2.0, stem=f"template_node_{i}")
        a.text("labels", x, 158, label, size=8.6, fill=INK, anchor="middle", stem=f"template_node_{i}_label")
    a.text("annotations", 255, 184, "Use lanes, rules, and labeled edges; avoid decorative containers.", size=8.5, fill=MUTED, anchor="middle", stem="process_note")

    a.text("labels", 535, 86, "2  STATUS GLYPHS", size=9.2, weight="bold", fill=NAVY, stem="status_title")
    for i, (label, status) in enumerate((("supported", "supported"), ("partial / relocated", "partial"), ("unavailable", "unavailable"))):
        y = 122 + i * 42
        status_glyph(a, 555, y, status, f"template_status_{i}")
        a.text("labels", 575, y + 4, label, size=8.8, stem=f"template_status_{i}_label")
    a.text("annotations", 555, 246, "Shape + color preserves meaning in grayscale and for color-vision differences.", size=8.3, fill=MUTED, stem="status_note")

    a.line("axis", 20, 280, 880, 280, stroke=GRID, stroke_width=0.8, stem="mid_rule")
    a.text("labels", 24, 310, "3  QUANTITATIVE MARKS", size=9.2, weight="bold", fill=NAVY, stem="quant_title")
    qx0, qy = 180, 355
    a.line("axis", qx0, qy, 480, qy, stroke=GRID, stroke_width=1.0, stem="lollipop_base")
    a.line("data", qx0, qy, 390, qy, stroke=TEAL, stroke_width=1.6, stem="lollipop_stem")
    a.circle("data", 390, qy, 5.5, fill=TEAL, stroke=WHITE, stem="lollipop_point")
    a.text("labels", 24, qy + 4, "directly labeled estimate", size=8.8, stem="lollipop_label")
    a.text("annotations", 402, qy + 4, "70.0%", size=8.8, weight="bold", fill=TEAL, stem="lollipop_value")
    a.line("data", 260, 408, 430, 408, stroke=BLUE, stroke_width=1.5, stem="ci_line")
    a.line("data", 260, 403, 260, 413, stroke=BLUE, stroke_width=1.0, stem="ci_low")
    a.line("data", 430, 403, 430, 413, stroke=BLUE, stroke_width=1.0, stem="ci_high")
    a.circle("data", 348, 408, 5.0, fill=BLUE, stroke=WHITE, stem="ci_point")
    a.text("labels", 24, 412, "effect with interval", size=8.8, stem="ci_label")
    a.text("annotations", 442, 412, "1.64 (1.51–1.79)", size=8.5, fill=MUTED, stem="ci_value")

    a.text("labels", 535, 310, "4  TYPOGRAPHY + PALETTE", size=9.2, weight="bold", fill=NAVY, stem="type_title")
    a.text("labels", 555, 347, "Arial / Helvetica · live text", size=9.0, weight="bold", stem="type_1")
    a.text("labels", 555, 369, "14.5 pt panel title · 8–10 pt labels", size=8.6, fill=MUTED, stem="type_2")
    a.text("labels", 555, 391, "0.8–1.2 pt rules · square corners", size=8.6, fill=MUTED, stem="type_3")
    colors = [("source", BLUE), ("delivered", TEAL), ("unresolved", ORANGE), ("unavailable", DARK_GRAY)]
    for i, (label, color) in enumerate(colors):
        x = 555 + (i % 2) * 150
        y = 423 + (i // 2) * 35
        a.rect("legend", x, y, 14, 14, fill=color, stroke=color, rx=0, stem=f"swatch_{i}")
        a.text("legend", x + 21, y + 12, label, size=8.3, stem=f"swatch_{i}_label")
    a.text("annotations", 450, 503, "White background · no gradients · no shadows · no rounded-card dashboard composition", size=8.7, fill=MUTED, anchor="middle", stem="template_boundary")
    return "JBI_Style_Template", [a], 900, 520, [(a, 0, 0, 1)]


def write_alt_text(root: Path) -> None:
    text = """# Figure legends and alt text

## Figure 1. Machine-executable medication-exposure provenance architecture
Panel A uses four source lanes to show native EHR, FHIR, OMOP, and eICU representations passing through source-specific adapters into a canonical medication-event record while preserving clinical role and retaining native identity when available without inferring it when absent. Panel B shows the five operator dimensions, validation chain, explicit four-state output, and the two prespecified evaluation paths.

## Figure 2. Native parity and prespecified operator ablation
Panel A is a log-log parity plot in which all frozen and generated six-class counts fall on the identity line; 19 of 19 checks pass. Panel B is a connected dot plot showing exposed proportions after successive operator ablations in A1 and A2, with route-required A1 administration explicitly classified as unmeasurable.

## Figure 3. Bounded cross-representation and cross-database evaluation
Panel A is a shape-coded capability matrix for native MIMIC-IV, matched FHIR demonstrations, an OMOP demonstration, and eICU. Panel B is a lollipop plot of matched-demo FHIR identity and time concordance. Panel C shows fail-closed state distributions for OMOP and eICU evaluations.

## Figure 4. Structured reporting validator
Panel A is a lollipop plot showing how often 40 coded MIMIC medication studies reported each provenance dimension. Panel B shows the drop from 40 encoded studies to 7 naming a native source, 2 specifying an executable identity rule, and none specifying event semantics or a complete operator; a small histogram shows reported dimensions per study.

## Figure 5. Reclassification and effect-estimate stress tests
Panel A shows exact-identity versus same-class/window reclassification in A1 and A2 and separately reports structural route non-measurability. Panel B is a paired forest plot comparing order-defined and administration-defined estimates under exact identity, same-class/window, and alternate time-window operators. These are measurement stress tests, not causal drug-effect estimates.
"""
    (root / "FIGURE_LEGENDS_AND_ALT_TEXT.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    root = (args.output_dir or repo / "manuscript/jbi/figure_redesign_2026-08-05").resolve()
    final_dir = root / "final_figures"
    template_dir = root / "template"
    data_dir = root / "data"
    qc_dir = root / "qc"
    for path in (final_dir, template_dir, data_dir, qc_dir):
        path.mkdir(parents=True, exist_ok=True)

    builders = [figure1(), figure2(repo, data_dir), figure3(repo, data_dir), figure4(repo, data_dir), figure5(repo, data_dir)]
    manifest: list[dict[str, Any]] = []
    for stem, panels, width, height, placements in builders:
        base.save_figure(final_dir, stem, panels, width, height, placements)
        base.render_preview(final_dir / f"{stem}.pdf", final_dir / f"{stem}.png", final_dir / f"{stem}.tiff")
        svg_result = base.svg_qc(final_dir / f"{stem}.svg", [p.letter for p in panels])
        pdf_result = base.pdf_qc(final_dir / f"{stem}.pdf")
        result = {"figure": stem, "svg": svg_result, "pdf": pdf_result}
        manifest.append(result)
        (qc_dir / f"{stem}_qc.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        if svg_result["status"] != "PASS" or pdf_result["status"] != "PASS":
            raise RuntimeError(f"QC failed for {stem}: {result}")
        for panel in panels:
            p_stem = f"{stem}_panel_{panel.letter}"
            p_svg = base.svg_qc(final_dir / "panels" / f"{p_stem}.svg", [panel.letter])
            p_pdf = base.pdf_qc(final_dir / "panels" / f"{p_stem}.pdf")
            if p_svg["status"] != "PASS" or p_pdf["status"] != "PASS":
                raise RuntimeError(f"Panel QC failed for {p_stem}")

    t_stem, t_panels, t_width, t_height, t_placements = style_template()
    base.save_figure(template_dir, t_stem, t_panels, t_width, t_height, t_placements)
    base.render_preview(template_dir / f"{t_stem}.pdf", template_dir / f"{t_stem}.png", template_dir / f"{t_stem}.tiff")
    t_svg = base.svg_qc(template_dir / f"{t_stem}.svg", ["A"])
    t_pdf = base.pdf_qc(template_dir / f"{t_stem}.pdf")
    if t_svg["status"] != "PASS" or t_pdf["status"] != "PASS":
        raise RuntimeError(f"Template QC failed: {t_svg}, {t_pdf}")

    payload = {"status": "PASS", "figures": manifest, "template": {"svg": t_svg, "pdf": t_pdf}}
    (qc_dir / "JBI_REDESIGN_QC.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["# JBI redesign structural QC", ""]
    for item in manifest:
        lines.append(f"- {item['figure']}: SVG {item['svg']['status']} ({item['svg']['live_text_n']} live text, {item['svg']['image_elements_n']} images); PDF {item['pdf']['status']} ({item['pdf']['image_xobjects_n']} image XObjects; fonts {', '.join(item['pdf']['font_subtypes'])}).")
    lines.append(f"- {t_stem}: SVG {t_svg['status']} ({t_svg['live_text_n']} live text, {t_svg['image_elements_n']} images); PDF {t_pdf['status']} ({t_pdf['image_xobjects_n']} image XObjects).")
    (qc_dir / "JBI_REDESIGN_QC.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_alt_text(root)
    print(json.dumps({"status": "PASS", "figures_n": len(manifest), "output_dir": str(root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
