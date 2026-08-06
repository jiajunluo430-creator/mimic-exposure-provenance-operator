#!/usr/bin/env python3
"""Build the five JBI main figures from committed aggregate outputs.

The renderer uses one scene graph for SVG and PDF. SVG text remains live and
all panel/subgroup identifiers are semantic. PDF output uses vector-native
ReportLab primitives. PNG/TIFF files are rendered from the assembled vector PDF.
No patient-, encounter-, order-, pharmacy-, or eMAR-level identifiers are read
or written.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from PIL import Image
from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

INK = "#17212B"
MUTED = "#61717F"
GRID = "#DCE3E8"
LIGHT = "#F4F7F9"
BLUE = "#4C78A8"
NAVY = "#244A73"
ORANGE = "#F28E2B"
TEAL = "#2A9D8F"
GREEN = "#59A14F"
RED = "#E15759"
PURPLE = "#8F63B8"
GRAY = "#A7B0B7"
DARK_GRAY = "#6B747C"
WHITE = "#FFFFFF"
UNMEASURABLE = "#7D8790"


def slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    return value.strip("_") or "item"


def rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@dataclass
class Panel:
    letter: str
    width: float
    height: float
    groups: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {
            "axis": [],
            "data": [],
            "labels": [],
            "legend": [],
            "annotations": [],
        }
    )
    _counter: int = 0

    def _id(self, stem: str) -> str:
        self._counter += 1
        return f"panel_{self.letter}_{slug(stem)}_{self._counter:03d}"

    def add(self, group: str, kind: str, stem: str, **kwargs: Any) -> None:
        if group not in self.groups:
            raise KeyError(group)
        self.groups[group].append({"kind": kind, "id": self._id(stem), **kwargs})

    def rect(
        self,
        group: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str = WHITE,
        stroke: str = GRID,
        stroke_width: float = 1.0,
        rx: float = 0,
        stem: str = "rect",
    ) -> None:
        self.add(group, "rect", stem, x=x, y=y, w=w, h=h, fill=fill, stroke=stroke, stroke_width=stroke_width, rx=rx)

    def line(
        self,
        group: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: str = INK,
        stroke_width: float = 1.5,
        dash: str | None = None,
        stem: str = "line",
    ) -> None:
        self.add(group, "line", stem, x1=x1, y1=y1, x2=x2, y2=y2, stroke=stroke, stroke_width=stroke_width, dash=dash)

    def circle(
        self,
        group: str,
        cx: float,
        cy: float,
        r: float,
        *,
        fill: str,
        stroke: str = WHITE,
        stroke_width: float = 1.0,
        stem: str = "circle",
    ) -> None:
        self.add(group, "circle", stem, cx=cx, cy=cy, r=r, fill=fill, stroke=stroke, stroke_width=stroke_width)

    def polygon(
        self,
        group: str,
        points: list[tuple[float, float]],
        *,
        fill: str,
        stroke: str = INK,
        stroke_width: float = 1.0,
        stem: str = "polygon",
    ) -> None:
        self.add(group, "polygon", stem, points=points, fill=fill, stroke=stroke, stroke_width=stroke_width)

    def text(
        self,
        group: str,
        x: float,
        y: float,
        value: str,
        *,
        size: float = 13,
        fill: str = INK,
        weight: str = "normal",
        anchor: str = "start",
        family: str = "Arial",
        stem: str = "text",
    ) -> None:
        self.add(group, "text", stem, x=x, y=y, text=value, size=size, fill=fill, weight=weight, anchor=anchor, family=family)

    def arrow(
        self,
        group: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: str = DARK_GRAY,
        stroke_width: float = 2.0,
        stem: str = "arrow",
    ) -> None:
        self.line(group, x1, y1, x2, y2, stroke=stroke, stroke_width=stroke_width, stem=f"{stem}_shaft")
        angle = math.atan2(y2 - y1, x2 - x1)
        head = 9
        wing = 4.5
        base_x = x2 - head * math.cos(angle)
        base_y = y2 - head * math.sin(angle)
        left = (base_x + wing * math.sin(angle), base_y - wing * math.cos(angle))
        right = (base_x - wing * math.sin(angle), base_y + wing * math.cos(angle))
        self.polygon(group, [(x2, y2), left, right], fill=stroke, stroke=stroke, stem=f"{stem}_head")


def add_panel_header(panel: Panel, title: str, subtitle: str | None = None) -> None:
    panel.text("annotations", 18, 27, panel.letter, size=20, weight="bold", stem="panel_tag")
    panel.text("labels", 50, 27, title, size=17, weight="bold", stem="panel_title")
    if subtitle:
        panel.text("labels", 50, 48, subtitle, size=11.5, fill=MUTED, stem="panel_subtitle")


def add_box(
    panel: Panel,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    lines: Iterable[str],
    *,
    fill: str,
    stroke: str,
    title_size: float = 13,
    text_size: float = 10.5,
    stem: str,
) -> None:
    panel.rect("data", x, y, w, h, fill=fill, stroke=stroke, stroke_width=1.4, rx=10, stem=f"{stem}_box")
    panel.text("labels", x + 12, y + 22, title, size=title_size, weight="bold", fill=INK, stem=f"{stem}_title")
    for i, line in enumerate(lines):
        panel.text("labels", x + 12, y + 43 + i * 16, line, size=text_size, fill=MUTED, stem=f"{stem}_line_{i}")


def write_svg(path: Path, width: float, height: float, placements: list[tuple[Panel, float, float, float]]) -> None:
    root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "version": "1.1",
            "width": f"{width:g}",
            "height": f"{height:g}",
            "viewBox": f"0 0 {width:g} {height:g}",
            "role": "img",
            "aria-label": path.stem.replace("_", " "),
        },
    )
    for panel, xoff, yoff, scale in placements:
        attrs = {"id": f"panel_{panel.letter}"}
        if xoff or yoff or scale != 1:
            attrs["transform"] = f"translate({xoff:g} {yoff:g}) scale({scale:g})"
        pgroup = ET.SubElement(root, f"{{{SVG_NS}}}g", attrs)
        for group_name in ("axis", "data", "labels", "legend", "annotations"):
            subgroup = ET.SubElement(pgroup, f"{{{SVG_NS}}}g", {"id": f"panel_{panel.letter}_{group_name}"})
            for cmd in panel.groups[group_name]:
                _svg_command(subgroup, cmd)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _svg_command(parent: ET.Element, cmd: dict[str, Any]) -> None:
    kind = cmd["kind"]
    common = {"id": cmd["id"]}
    if kind == "rect":
        attrs = {
            **common,
            "x": f"{cmd['x']:g}",
            "y": f"{cmd['y']:g}",
            "width": f"{cmd['w']:g}",
            "height": f"{cmd['h']:g}",
            "fill": cmd["fill"],
            "stroke": cmd["stroke"],
            "stroke-width": f"{cmd['stroke_width']:g}",
        }
        if cmd["rx"]:
            attrs["rx"] = f"{cmd['rx']:g}"
        ET.SubElement(parent, f"{{{SVG_NS}}}rect", attrs)
    elif kind == "line":
        attrs = {
            **common,
            "x1": f"{cmd['x1']:g}",
            "y1": f"{cmd['y1']:g}",
            "x2": f"{cmd['x2']:g}",
            "y2": f"{cmd['y2']:g}",
            "stroke": cmd["stroke"],
            "stroke-width": f"{cmd['stroke_width']:g}",
            "stroke-linecap": "round",
        }
        if cmd.get("dash"):
            attrs["stroke-dasharray"] = cmd["dash"]
        ET.SubElement(parent, f"{{{SVG_NS}}}line", attrs)
    elif kind == "circle":
        ET.SubElement(
            parent,
            f"{{{SVG_NS}}}circle",
            {
                **common,
                "cx": f"{cmd['cx']:g}",
                "cy": f"{cmd['cy']:g}",
                "r": f"{cmd['r']:g}",
                "fill": cmd["fill"],
                "stroke": cmd["stroke"],
                "stroke-width": f"{cmd['stroke_width']:g}",
            },
        )
    elif kind == "polygon":
        ET.SubElement(
            parent,
            f"{{{SVG_NS}}}polygon",
            {
                **common,
                "points": " ".join(f"{x:g},{y:g}" for x, y in cmd["points"]),
                "fill": cmd["fill"],
                "stroke": cmd["stroke"],
                "stroke-width": f"{cmd['stroke_width']:g}",
            },
        )
    elif kind == "text":
        element = ET.SubElement(
            parent,
            f"{{{SVG_NS}}}text",
            {
                **common,
                "x": f"{cmd['x']:g}",
                "y": f"{cmd['y']:g}",
                "fill": cmd["fill"],
                "font-family": cmd["family"],
                "font-size": f"{cmd['size']:g}px",
                "font-weight": "700" if cmd["weight"] == "bold" else "400",
                "text-anchor": cmd["anchor"],
            },
        )
        element.text = cmd["text"]
    else:
        raise ValueError(kind)


def write_pdf(path: Path, width: float, height: float, placements: list[tuple[Panel, float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = pdfcanvas.Canvas(str(path), pagesize=(width, height), pageCompression=1)
    canvas.setTitle(path.stem)
    for panel, xoff, yoff, scale in placements:
        for group_name in ("axis", "data", "labels", "legend", "annotations"):
            for cmd in panel.groups[group_name]:
                _pdf_command(canvas, cmd, width, height, xoff, yoff, scale)
    canvas.showPage()
    canvas.save()


def _pdf_command(
    canvas: pdfcanvas.Canvas,
    cmd: dict[str, Any],
    width: float,
    height: float,
    xoff: float,
    yoff: float,
    scale: float,
) -> None:
    del width
    tx = lambda x: xoff + scale * x
    ty = lambda y: height - (yoff + scale * y)
    kind = cmd["kind"]
    canvas.setLineWidth(cmd.get("stroke_width", 1) * scale)
    if "stroke" in cmd:
        canvas.setStrokeColorRGB(*rgb(cmd["stroke"]))
    if "fill" in cmd:
        canvas.setFillColorRGB(*rgb(cmd["fill"]))
    if kind == "rect":
        y_bottom = height - (yoff + scale * (cmd["y"] + cmd["h"]))
        if cmd["rx"]:
            canvas.roundRect(tx(cmd["x"]), y_bottom, scale * cmd["w"], scale * cmd["h"], scale * cmd["rx"], stroke=1, fill=1)
        else:
            canvas.rect(tx(cmd["x"]), y_bottom, scale * cmd["w"], scale * cmd["h"], stroke=1, fill=1)
    elif kind == "line":
        if cmd.get("dash"):
            canvas.setDash(*[float(x) * scale for x in cmd["dash"].split(",")])
        else:
            canvas.setDash()
        canvas.line(tx(cmd["x1"]), ty(cmd["y1"]), tx(cmd["x2"]), ty(cmd["y2"]))
        canvas.setDash()
    elif kind == "circle":
        canvas.circle(tx(cmd["cx"]), ty(cmd["cy"]), scale * cmd["r"], stroke=1, fill=1)
    elif kind == "polygon":
        points = cmd["points"]
        path = canvas.beginPath()
        path.moveTo(tx(points[0][0]), ty(points[0][1]))
        for x, y in points[1:]:
            path.lineTo(tx(x), ty(y))
        path.close()
        canvas.drawPath(path, stroke=1, fill=1)
    elif kind == "text":
        font = "Helvetica-Bold" if cmd["weight"] == "bold" else "Helvetica"
        size = cmd["size"] * scale
        canvas.setFont(font, size)
        canvas.setFillColorRGB(*rgb(cmd["fill"]))
        x = tx(cmd["x"])
        value = cmd["text"]
        if cmd["anchor"] == "middle":
            x -= stringWidth(value, font, size) / 2
        elif cmd["anchor"] == "end":
            x -= stringWidth(value, font, size)
        canvas.drawString(x, ty(cmd["y"]), value)
    else:
        raise ValueError(kind)


def save_figure(
    out_dir: Path,
    stem: str,
    panels: list[Panel],
    width: float,
    height: float,
    placements: list[tuple[Panel, float, float, float]],
) -> None:
    panel_dir = out_dir / "panels"
    for panel in panels:
        p_stem = f"{stem}_panel_{panel.letter}"
        write_svg(panel_dir / f"{p_stem}.svg", panel.width, panel.height, [(panel, 0, 0, 1)])
        write_pdf(panel_dir / f"{p_stem}.pdf", panel.width, panel.height, [(panel, 0, 0, 1)])
    write_svg(out_dir / f"{stem}.svg", width, height, placements)
    write_pdf(out_dir / f"{stem}.pdf", width, height, placements)


def figure1() -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    a = Panel("A", 520, 590)
    add_panel_header(a, "Adapters preserve clinical role before normalization")
    sources = [
        ("Native EHR", ["POE / pharmacy / eMAR", "request / dispense / administration"], BLUE),
        ("FHIR R4", ["MedicationRequest / Dispense", "MedicationAdministration"], TEAL),
        ("OMOP CDM", ["DRUG_EXPOSURE", "type and source values"], PURPLE),
        ("eICU", ["medication / infusionDrug", "treatment documentation"], ORANGE),
    ]
    y_positions = [82, 190, 298, 406]
    for (title, lines, color), y in zip(sources, y_positions):
        add_box(a, 22, y, 190, 82, title, lines, fill=LIGHT, stroke=color, stem=title)
        add_box(a, 260, y + 8, 98, 66, "Adapter", [title.split()[0]], fill=WHITE, stroke=color, title_size=12, text_size=10, stem=f"{title}_adapter")
        a.arrow("axis", 214, y + 41, 256, y + 41, stroke=color, stem=f"{title}_to_adapter")
        a.arrow("axis", 360, y + 41, 400, 292, stroke=DARK_GRAY, stem=f"{title}_to_cir")
    add_box(
        a,
        388,
        217,
        118,
        150,
        "Canonical event",
        ["clinical role", "native identity", "event time", "literal state", "route / dose"],
        fill="#EAF3F8",
        stroke=NAVY,
        title_size=12,
        text_size=9.6,
        stem="canonical_event",
    )
    a.line("legend", 24, 540, 52, 540, stroke=NAVY, stroke_width=2, stem="legend_line")
    a.text("legend", 60, 545, "Source-specific mapping remains version-gated", size=10.5, fill=MUTED, stem="legend_text")
    a.text("annotations", 260, 575, "Identifiers remain local; public outputs are aggregate-only", size=10.5, fill=MUTED, anchor="middle", stem="privacy_note")

    b = Panel("B", 520, 590)
    add_panel_header(b, "Five dimensions compile to four auditable states")
    dims = [
        ("S", "Source", BLUE),
        ("I", "Identity", TEAL),
        ("T", "Time", ORANGE),
        ("E", "Event semantics", PURPLE),
        ("M", "Required metadata", GREEN),
    ]
    for i, (symbol, label, color) in enumerate(dims):
        x = 18 + i * 99
        b.rect("data", x, 82, 88, 64, fill=LIGHT, stroke=color, stroke_width=1.5, rx=10, stem=f"dim_{symbol}")
        b.text("labels", x + 44, 108, symbol, size=22, weight="bold", fill=color, anchor="middle", stem=f"dim_{symbol}_symbol")
        b.text("labels", x + 44, 132, label, size=9.5, fill=INK, anchor="middle", stem=f"dim_{symbol}_label")
    b.arrow("axis", 260, 151, 260, 184, stroke=DARK_GRAY, stem="dims_to_validator")
    stages = ["syntactically valid", "adapter supported", "measurable", "executable", "traceable"]
    for i, stage in enumerate(stages):
        x = 16 + i * 101
        b.rect("data", x, 190, 90, 48, fill=WHITE, stroke=NAVY, rx=7, stem=f"gate_{i}")
        b.text("labels", x + 45, 218, stage, size=9.2, anchor="middle", stem=f"gate_{i}_label")
        if i < len(stages) - 1:
            b.arrow("axis", x + 91, 214, x + 100, 214, stroke=DARK_GRAY, stroke_width=1.4, stem=f"gate_arrow_{i}")
    b.arrow("axis", 260, 243, 260, 280, stroke=DARK_GRAY, stem="validator_to_states")
    states = [
        ("exposed", TEAL),
        ("unexposed", BLUE),
        ("unresolved", ORANGE),
        ("unmeasurable", UNMEASURABLE),
    ]
    for i, (state, color) in enumerate(states):
        x = 22 + i * 124
        b.rect("data", x, 288, 112, 54, fill=color, stroke=color, rx=9, stem=f"state_{state}")
        b.text("labels", x + 56, 321, state, size=11.3, weight="bold", fill=WHITE, anchor="middle", stem=f"state_{state}_label")
    b.arrow("axis", 260, 350, 260, 392, stroke=DARK_GRAY, stem="states_to_outputs")
    add_box(b, 36, 400, 206, 90, "Aggregate comparison", ["classification retention", "reclassification / timing", "semantic loss"], fill="#F1F6FB", stroke=BLUE, stem="aggregate_comparison")
    add_box(b, 278, 400, 206, 90, "Downstream stress test", ["paired exposure cohorts", "effect-estimate drift", "no causal drug claim"], fill="#FFF5E9", stroke=ORANGE, stem="downstream_stress")
    b.line("legend", 24, 535, 52, 535, stroke=ORANGE, stroke_width=2, stem="legend_line")
    b.text("legend", 60, 540, "Failure is explicit; missing capability does not become unexposed", size=10.5, fill=MUTED, stem="legend_text")
    b.text("annotations", 260, 575, "O = (S, I, T, E, M); C(u) is deterministic for each analysis unit", size=10.5, fill=MUTED, anchor="middle", stem="formula_note")
    return "Figure1_medprov_architecture", [a, b], 1060, 590, [(a, 0, 0, 1), (b, 540, 0, 1)]


def figure2(repo: Path, data_dir: Path) -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    parity = read_tsv(repo / "outputs/method_evaluation_v0_1_0/tables/mimic_six_class_parity.tsv")
    ablation = read_tsv(repo / "outputs/method_evaluation_v0_1_0/tables/operator_ablation_matrix.tsv")
    with (data_dir / "Figure2_native_parity.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(parity[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(parity)
    with (data_dir / "Figure2_ablation.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(ablation[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(ablation)

    a = Panel("A", 530, 540)
    add_panel_header(a, "Exact native parity across six medication classes", "Expected frozen counts versus medprov 0.1.0 output")
    plot_x0, plot_y0, plot_w, plot_h = 84, 82, 390, 360
    a.line("axis", plot_x0, plot_y0 + plot_h, plot_x0 + plot_w, plot_y0 + plot_h, stroke=INK, stem="x_axis")
    a.line("axis", plot_x0, plot_y0, plot_x0, plot_y0 + plot_h, stroke=INK, stem="y_axis")
    lo, hi = 3.0, 5.2
    def scale_x(value: float) -> float:
        return plot_x0 + (math.log10(value) - lo) / (hi - lo) * plot_w
    def scale_y(value: float) -> float:
        return plot_y0 + plot_h - (math.log10(value) - lo) / (hi - lo) * plot_h
    a.line("axis", scale_x(10**lo), scale_y(10**lo), scale_x(10**hi), scale_y(10**hi), stroke=GRAY, stroke_width=1.5, dash="5,5", stem="identity_line")
    for tick in (1_000, 10_000, 100_000):
        x, y = scale_x(tick), scale_y(tick)
        a.line("axis", x, plot_y0 + plot_h, x, plot_y0 + plot_h + 6, stroke=INK, stem=f"xtick_{tick}")
        a.line("axis", plot_x0 - 6, y, plot_x0, y, stroke=INK, stem=f"ytick_{tick}")
        label = f"10^{int(math.log10(tick))}"
        a.text("labels", x, plot_y0 + plot_h + 24, label, size=10.5, anchor="middle", stem=f"xlabel_{tick}")
        a.text("labels", plot_x0 - 11, y + 4, label, size=10.5, anchor="end", stem=f"ylabel_{tick}")
    categories = [
        ("orders", "expected_orders_n", "actual_orders_n", BLUE, "circle"),
        ("strict", "expected_strict_n", "actual_strict_n", ORANGE, "square"),
        ("same class/window", "expected_broad_n", "actual_broad_n", TEAL, "diamond"),
    ]
    for category, expected_key, actual_key, color, shape in categories:
        for row in parity:
            x = scale_x(float(row[expected_key]))
            y = scale_y(float(row[actual_key]))
            stem = f"{category}_{row['drug_class']}"
            if shape == "circle":
                a.circle("data", x, y, 5.2, fill=color, stroke=WHITE, stroke_width=1.2, stem=stem)
            elif shape == "square":
                a.rect("data", x - 5, y - 5, 10, 10, fill=color, stroke=WHITE, stroke_width=1.2, stem=stem)
            else:
                a.polygon("data", [(x, y - 6), (x + 6, y), (x, y + 6), (x - 6, y)], fill=color, stroke=WHITE, stroke_width=1.2, stem=stem)
    a.text("labels", plot_x0 + plot_w / 2, 492, "Frozen expected count (log scale)", size=12, anchor="middle", stem="x_title")
    a.text("labels", 16, 250, "medprov count", size=12, stem="y_title")
    lx = 106
    for i, (label, _, _, color, shape) in enumerate(categories):
        x = lx + i * 126
        if shape == "circle":
            a.circle("legend", x, 522, 5, fill=color, stroke=color, stem=f"legend_{i}")
        elif shape == "square":
            a.rect("legend", x - 5, 517, 10, 10, fill=color, stroke=color, stem=f"legend_{i}")
        else:
            a.polygon("legend", [(x, 516), (x + 6, 522), (x, 528), (x - 6, 522)], fill=color, stroke=color, stem=f"legend_{i}")
        a.text("legend", x + 10, 526, label, size=9.5, stem=f"legend_label_{i}")
    a.text("annotations", 468, 106, "19/19 parity checks passed", size=11.5, weight="bold", fill=GREEN, anchor="end", stem="parity_note")

    b = Panel("B", 530, 540)
    add_panel_header(b, "Prespecified ablation isolates operator information", "Exposed proportion within each frozen anchor cohort")
    keep_labels = ["table-only", "source+class+window", "collapsed event semantics", "full exact-identity operator"]
    colors = [GRAY, BLUE, ORANGE, TEAL]
    rows = {(row["anchor"], row["operator_label"]): row for row in ablation if row["anchor"] in {"A1", "A2"}}
    x0, y0, w = 176, 92, 300
    for tick in (0, 25, 50, 75, 100):
        x = x0 + w * tick / 100
        b.line("axis", x, y0, x, 402, stroke=GRID, stroke_width=1, stem=f"grid_{tick}")
        b.text("labels", x, 424, f"{tick}%", size=9.5, fill=MUTED, anchor="middle", stem=f"tick_{tick}")
    b.line("axis", x0, 402, x0 + w, 402, stroke=INK, stem="x_axis")
    y_positions = {"A1": [108, 146, 184, 222], "A2": [264, 302, 340, 378]}
    for anchor, cohort_n in (("A1", 20248), ("A2", 2813)):
        b.text("labels", 18, y_positions[anchor][0] - 11, f"{anchor} (n={cohort_n:,})", size=12, weight="bold", stem=f"anchor_{anchor}")
        for i, label in enumerate(keep_labels):
            row = rows[(anchor, label)]
            exposed = int(row["exposed_n"])
            total = int(row["analysis_units_n"])
            pct = exposed / total * 100
            y = y_positions[anchor][i]
            b.text("labels", 24, y + 5, label.replace(" operator", ""), size=9.6, fill=INK, stem=f"{anchor}_{i}_label")
            b.rect("data", x0, y - 12, w * pct / 100, 20, fill=colors[i], stroke=colors[i], rx=3, stem=f"{anchor}_{i}_bar")
            b.text("annotations", x0 + w * pct / 100 + 6, y + 4, f"{pct:.1f}%", size=9.5, fill=INK, stem=f"{anchor}_{i}_pct")
    b.rect("data", 24, 441, 452, 54, fill="#F1F3F5", stroke=UNMEASURABLE, rx=8, stem="route_unmeasurable_box")
    b.text("annotations", 38, 463, "Route-required A1 administration: 20,248/20,248 units unmeasurable", size=10.8, weight="bold", fill=UNMEASURABLE, stem="route_unmeasurable_title")
    b.text("annotations", 38, 484, "Required eMAR route was absent; fail-closed output did not relabel units as unexposed.", size=9.5, fill=MUTED, stem="route_unmeasurable_note")
    for i, (label, color) in enumerate(zip(keep_labels, colors)):
        b.rect("legend", 22 + i * 125, 522, 12, 12, fill=color, stroke=color, stem=f"legend_{i}")
        b.text("legend", 39 + i * 125, 532, label.split()[0], size=9, stem=f"legend_label_{i}")
    return "Figure2_native_parity_and_ablation", [a, b], 1080, 540, [(a, 0, 0, 1), (b, 550, 0, 1)]


def figure3(repo: Path, data_dir: Path) -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    fhir = read_json(repo / "outputs/transport_evaluation_v0_1_0/fhir_transport_summary.json")
    fhir_composite = read_csv(repo / "outputs/transport_evaluation_v0_1_0/fhir_administration_composite_pairing.csv")
    omop = read_json(repo / "outputs/omop_evaluation_v0_1_0/omop_evaluation_summary.json")
    eicu = read_json(repo / "outputs/eicu_transport_v0_1_0/eicu_transport_summary.json")
    payload = {"fhir": fhir, "omop": omop, "eicu": eicu}
    (data_dir / "Figure3_transport_summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    a = Panel("A", 1040, 330)
    add_panel_header(a, "Representation capability is dimension-specific", "Green=supported; amber=partial or relocated; gray=structurally unavailable in the evaluated representation")
    cols = ["Source role", "Native identity", "Time", "Event semantics", "Route/dose", "Four-state output"]
    rows = [
        ("MIMIC-IV 3.1 native", ["supported", "supported", "supported", "supported", "partial", "supported"]),
        ("Matched native/FHIR demos", ["supported", "partial", "partial", "partial", "partial", "supported"]),
        ("MIMIC OMOP demo", ["partial", "partial", "supported", "unavailable", "partial", "supported"]),
        ("eICU 2.0", ["partial", "unavailable", "partial", "partial", "partial", "supported"]),
    ]
    x0, y0, cell_w, cell_h = 250, 85, 122, 48
    for j, col in enumerate(cols):
        a.text("labels", x0 + j * cell_w + cell_w / 2, 70, col, size=10, weight="bold", anchor="middle", stem=f"col_{j}")
    status_color = {"supported": GREEN, "partial": ORANGE, "unavailable": UNMEASURABLE}
    for i, (row_label, statuses) in enumerate(rows):
        y = y0 + i * cell_h
        a.text("labels", x0 - 14, y + 30, row_label, size=11, weight="bold" if i == 0 else "normal", anchor="end", stem=f"row_{i}")
        for j, status in enumerate(statuses):
            x = x0 + j * cell_w
            a.rect("axis", x, y, cell_w - 5, cell_h - 6, fill=WHITE, stroke=GRID, stem=f"grid_{i}_{j}")
            a.rect("data", x + 4, y + 4, cell_w - 13, cell_h - 14, fill=status_color[status], stroke=status_color[status], rx=5, stem=f"cell_{i}_{j}")
            a.text("annotations", x + (cell_w - 5) / 2, y + 27, status, size=9.2, fill=WHITE, weight="bold", anchor="middle", stem=f"status_{i}_{j}")
    for k, (status, color) in enumerate(status_color.items()):
        a.rect("legend", 256 + k * 155, 295, 13, 13, fill=color, stroke=color, stem=f"legend_{k}")
        a.text("legend", 275 + k * 155, 306, status, size=9.5, stem=f"legend_label_{k}")
    a.text("annotations", 1015, 306, "Capabilities are not a rank or superiority score", size=9.5, fill=MUTED, anchor="end", stem="boundary_note")

    b = Panel("B", 510, 390)
    add_panel_header(b, "Matched-demo FHIR identity and time concordance")
    native_linkable = sum(int(row["native_linkable_events_n"]) for row in fhir_composite)
    composite_pct = fhir["headline_findings"]["admin_composite_matches_n"] / native_linkable * 100
    metrics = [
        ("Dispense ID x class", 100.0, "3,870/3,870 exact"),
        ("Request authoredOn vs enter time", 100.0, "2,249/2,249 exact"),
        ("First administration time", 1347 / 1353 * 100, "1,347/1,353 exact"),
        ("Administration composite", composite_pct, f"5,220/{native_linkable:,} native-linkable"),
    ]
    x0, y0, w = 220, 84, 240
    for tick in (0, 25, 50, 75, 100):
        x = x0 + w * tick / 100
        b.line("axis", x, y0, x, 304, stroke=GRID, stem=f"grid_{tick}")
        b.text("labels", x, 326, f"{tick}%", size=9.5, fill=MUTED, anchor="middle", stem=f"tick_{tick}")
    for i, (label, pct, detail) in enumerate(metrics):
        y = 104 + i * 54
        b.text("labels", 18, y + 5, label, size=10.2, stem=f"metric_{i}_label")
        b.rect("data", x0, y - 12, w * pct / 100, 22, fill=BLUE if i < 3 else TEAL, stroke=WHITE, rx=4, stem=f"metric_{i}_bar")
        b.text("annotations", x0 + w * pct / 100 - 5, y + 5, f"{pct:.1f}%", size=9.7, weight="bold", fill=WHITE, anchor="end", stem=f"metric_{i}_pct")
        b.text("annotations", x0, y + 27, detail, size=8.8, fill=MUTED, stem=f"metric_{i}_detail")
    b.rect("legend", 20, 348, 14, 14, fill=ORANGE, stroke=ORANGE, stem="legend_caveat")
    b.text("legend", 42, 359, "Native eMAR identifiers were not retained in FHIR administration resources", size=9.5, fill=MUTED, stem="legend_text")
    b.text("annotations", 20, 381, "Functional cross-schema evaluation on matched public demos; not full-release validation", size=9.5, fill=MUTED, stem="claim_boundary")

    c = Panel("C", 510, 390)
    add_panel_header(c, "Fail-closed states reveal semantic loss")
    state_colors = {"exposed": TEAL, "unexposed": BLUE, "unresolved": ORANGE, "unmeasurable": UNMEASURABLE}
    bars = [
        ("OMOP demo: strict administration", {"exposed": 0, "unexposed": 0, "unresolved": 0, "unmeasurable": 37}),
        ("OMOP synthetic: extension present", {"exposed": 1, "unexposed": 1, "unresolved": 1, "unmeasurable": 1}),
        ("eICU full interface comparison", eicu["counts"]),
    ]
    x0, y0, w = 36, 96, 430
    for i, (label, counts) in enumerate(bars):
        y = y0 + i * 78
        total = sum(int(counts.get(state, 0)) for state in state_colors)
        c.text("labels", x0, y - 10, label, size=10.5, weight="bold", stem=f"bar_{i}_label")
        cursor = x0
        for state, color in state_colors.items():
            value = int(counts.get(state, 0))
            if value == 0:
                continue
            bw = w * value / total
            c.rect("data", cursor, y, bw, 32, fill=color, stroke=WHITE, stroke_width=0.8, stem=f"bar_{i}_{state}")
            if bw > 48:
                c.text("annotations", cursor + bw / 2, y + 21, f"{value / total * 100:.1f}%", size=9.5, weight="bold", fill=WHITE, anchor="middle", stem=f"bar_{i}_{state}_pct")
            cursor += bw
        c.line("axis", x0, y + 32, x0 + w, y + 32, stroke=INK, stroke_width=0.8, stem=f"bar_{i}_axis")
    for i, (state, color) in enumerate(state_colors.items()):
        x = 30 + i * 118
        c.rect("legend", x, 337, 12, 12, fill=color, stroke=color, stem=f"legend_{state}")
        c.text("legend", x + 17, 347, state, size=8.8, stem=f"legend_{state}_label")
    c.text("annotations", 25, 377, "eICU: 3/6 medication-class reconciliation gates passed; no native cross-source key", size=9.5, fill=MUTED, stem="eicu_boundary")
    return "Figure3_cross_representation_evaluation", [a, b, c], 1040, 740, [(a, 0, 0, 1), (b, 0, 350, 1), (c, 530, 350, 1)]


def figure4(repo: Path, data_dir: Path) -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    result = read_json(repo / "outputs/literature_validator_v0_1_0/literature_validator_result.json")
    summary = read_tsv(repo / "outputs/literature_validator_v0_1_0/tables/reporting_dimension_summary.tsv")
    with (data_dir / "Figure4_reporting_dimensions.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(summary[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    distribution = Counter(int(row["reported_dimensions_n"]) for row in result["records"])
    with (data_dir / "Figure4_reported_dimension_distribution.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["reported_dimensions_n", "studies_n"])
        for key in range(6):
            writer.writerow([key, distribution.get(key, 0)])

    a = Panel("A", 610, 500)
    add_panel_header(a, "Published exposure reports omit executable provenance", "Structured validator over 40 human-coded MIMIC medication studies")
    labels = {
        "source_layer": "Named native source",
        "identity_rule": "Executable identity rule",
        "time_origin_window": "Time origin/window",
        "event_semantics_map": "Native event semantics",
        "required_metadata": "Dose/route requirement",
    }
    x0, y0, w = 210, 94, 330
    for tick in (0, 25, 50, 75, 100):
        x = x0 + w * tick / 100
        a.line("axis", x, y0, x, 372, stroke=GRID, stem=f"grid_{tick}")
        a.text("labels", x, 397, f"{tick}%", size=9.5, fill=MUTED, anchor="middle", stem=f"tick_{tick}")
    for i, row in enumerate(summary):
        y = 112 + i * 54
        pct = int(row["reported_n"]) / int(row["sample_n"]) * 100
        color = TEAL if pct >= 50 else (ORANGE if pct > 0 else RED)
        a.text("labels", x0 - 14, y + 5, labels[row["dimension"]], size=10.8, anchor="end", stem=f"label_{i}")
        if pct > 0:
            a.rect("data", x0, y - 12, w * pct / 100, 24, fill=color, stroke=color, rx=4, stem=f"bar_{i}")
        else:
            a.circle("data", x0, y, 4.5, fill=color, stroke=color, stem=f"bar_{i}_zero")
        a.text("annotations", x0 + w * pct / 100 + 8, y + 5, f"{row['reported_n']}/40", size=10.5, weight="bold", stem=f"count_{i}")
    a.line("legend", 25, 437, 53, 437, stroke=NAVY, stroke_width=2, stem="scope_line")
    a.text("legend", 62, 442, "Main texts, 55/56 linked supplements, and 3 article-specific repositories were searched", size=9.7, fill=MUTED, stem="scope_text")
    a.text("annotations", 25, 477, "Input was single-coded; the validator reproduces coding deterministically but does not replace human review.", size=9.7, fill=MUTED, stem="coder_boundary")

    b = Panel("B", 430, 500)
    add_panel_header(b, "Executability narrows at reporting gates")
    steps = [
        ("Studies encoded", 40, NAVY),
        ("Named native source", 7, BLUE),
        ("Executable identity", 2, ORANGE),
        ("Native event semantics", 0, RED),
        ("Complete operator", 0, UNMEASURABLE),
    ]
    max_w = 350
    for i, (label, value, color) in enumerate(steps):
        y = 78 + i * 66
        width = max(10, max_w * value / 40)
        x = 35 + (max_w - width) / 2
        b.rect("data", x, y, width, 42, fill=color, stroke=color, rx=7, stem=f"funnel_{i}")
        b.text("labels", 35, y - 9, label, size=10.5, weight="bold", stem=f"funnel_{i}_label")
        b.text("annotations", 395, y + 27, f"{value}/40", size=12, weight="bold", anchor="end", stem=f"funnel_{i}_value")
        if i < len(steps) - 1:
            b.arrow("axis", 210, y + 45, 210, y + 61, stroke=GRAY, stroke_width=1.4, stem=f"funnel_arrow_{i}")
    b.text("legend", 30, 390, "Reported dimensions per study", size=10.5, weight="bold", stem="distribution_title")
    max_count = max(distribution.values())
    for key in range(6):
        count = distribution.get(key, 0)
        x = 35 + key * 63
        h = 48 * count / max_count if max_count else 0
        b.rect("legend", x, 472 - h, 38, h, fill=PURPLE, stroke=PURPLE, rx=2, stem=f"dist_{key}")
        b.text("labels", x + 19, 487, str(key), size=9.5, anchor="middle", stem=f"dist_{key}_label")
        b.text("annotations", x + 19, 465 - h, str(count), size=8.8, anchor="middle", stem=f"dist_{key}_count")
    return "Figure4_literature_validator", [a, b], 1060, 500, [(a, 0, 0, 1), (b, 630, 0, 1)]


def figure5(repo: Path, data_dir: Path) -> tuple[str, list[Panel], float, float, list[tuple[Panel, float, float, float]]]:
    reclass = read_tsv(repo / "outputs/method_evaluation_v0_1_0/tables/operator_reclassification_metrics.tsv")
    reclass = [row for row in reclass if row["comparison"] == "exact_identity_vs_same_class"]
    effects = read_csv(repo / "figures/data/Figure4C_operator_effects.csv")
    with (data_dir / "Figure5_reclassification.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(reclass[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(reclass)
    selected_keys = [
        ("A1", "original_strict", "A1 exact identity"),
        ("A1", "original_broad", "A1 same class/window"),
        ("A2", "original_strict", "A2 original exact identity"),
        ("A2", "original_broad", "A2 original same class/window"),
        ("A2", "hospital_overlap_strict", "A2 hospital-overlap exact identity"),
        ("A2", "hospital_overlap_broad", "A2 hospital-overlap same class/window"),
    ]
    selected_effects: list[dict[str, str]] = []
    for anchor, operator, _ in selected_keys:
        selected_effects.extend(
            row
            for row in effects
            if row["anchor_id"] == anchor
            and row["operator"] == operator
            and row["model_variant"] == "published_style_minimal"
        )
    with (data_dir / "Figure5_effects.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(selected_effects[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected_effects)

    a = Panel("A", 420, 570)
    add_panel_header(a, "Identity simplification reclassified exposure", "Full exact identity versus same-class/window administration")
    colors = [("both positive", TEAL), ("same-class only", ORANGE), ("both negative", GRAY)]
    x0, y0, w = 34, 112, 350
    for i, row in enumerate(reclass):
        anchor = row["anchor"]
        total = int(row["analysis_units_n"])
        counts = [int(row["both_positive_n"]), int(row["right_only_n"]), int(row["both_negative_n"])]
        y = y0 + i * 118
        a.text("labels", x0, y - 18, f"{anchor} (n={total:,})", size=12, weight="bold", stem=f"anchor_{anchor}")
        cursor = x0
        for (label, color), count in zip(colors, counts):
            bw = w * count / total
            a.rect("data", cursor, y, bw, 42, fill=color, stroke=WHITE, stem=f"{anchor}_{label}")
            if bw > 44:
                a.text("annotations", cursor + bw / 2, y + 26, f"{count / total * 100:.1f}%", size=10, weight="bold", fill=WHITE, anchor="middle", stem=f"{anchor}_{label}_pct")
            cursor += bw
        a.line("axis", x0, y + 42, x0 + w, y + 42, stroke=INK, stroke_width=0.8, stem=f"axis_{anchor}")
        a.text("annotations", x0, y + 68, f"Positive Jaccard = {float(row['positive_jaccard']):.3f}", size=10, fill=MUTED, stem=f"jaccard_{anchor}")
    for i, (label, color) in enumerate(colors):
        y = 374 + i * 28
        a.rect("legend", 35, y, 14, 14, fill=color, stroke=color, stem=f"legend_{i}")
        a.text("legend", 57, y + 12, label, size=9.8, stem=f"legend_label_{i}")
    a.rect("data", 28, 468, 360, 65, fill="#F1F3F5", stroke=UNMEASURABLE, rx=8, stem="construct_note_box")
    a.text("annotations", 42, 491, "Construct measurability is independent of reclassification", size=10.2, weight="bold", fill=UNMEASURABLE, stem="construct_note_title")
    a.text("annotations", 42, 512, "A1 route: order 9,940/9,940 available; eMAR 0/87,569.", size=9.8, fill=MUTED, stem="construct_note")
    a.text("annotations", 210, 559, "Same-class/window is an ablation, not a replacement definition", size=9.4, fill=MUTED, anchor="middle", stem="boundary")

    b = Panel("B", 690, 570)
    add_panel_header(b, "Operator changes propagated selectively to paired estimates", "Published-style minimal models; identical cohort/outcome/covariates within each pair")
    x0, y0, w = 270, 92, 360
    xmin, xmax = math.log(0.75), math.log(2.4)
    def sx(value: float) -> float:
        return x0 + (math.log(value) - xmin) / (xmax - xmin) * w
    for tick in (0.75, 1.0, 1.5, 2.0):
        x = sx(tick)
        b.line("axis", x, y0, x, 450, stroke=INK if tick == 1.0 else GRID, stroke_width=1.4 if tick == 1.0 else 1, stem=f"grid_{tick}")
        b.text("labels", x, 475, f"{tick:g}", size=9.5, fill=MUTED, anchor="middle", stem=f"tick_{tick}")
    by_key = {(row["anchor_id"], row["operator"], row["exposure_source"]): row for row in selected_effects}
    for i, (anchor, operator, label) in enumerate(selected_keys):
        y = 110 + i * 55
        b.text("labels", x0 - 14, y + 5, label, size=9.7, anchor="end", stem=f"row_{i}_label")
        order = by_key[(anchor, operator, "order")]
        admin = by_key[(anchor, operator, "administration")]
        ox, ax = sx(float(order["effect"])), sx(float(admin["effect"]))
        b.line("data", ox, y, ax, y, stroke=GRAY, stroke_width=2.2, stem=f"pair_{i}")
        for source, row, color, yy in (("order", order, BLUE, y - 5), ("administration", admin, ORANGE, y + 5)):
            low, high, effect = float(row["ci_low"]), float(row["ci_high"]), float(row["effect"])
            b.line("data", sx(low), yy, sx(high), yy, stroke=color, stroke_width=1.8, stem=f"ci_{i}_{source}")
            b.line("data", sx(low), yy - 4, sx(low), yy + 4, stroke=color, stroke_width=1.2, stem=f"ci_low_{i}_{source}")
            b.line("data", sx(high), yy - 4, sx(high), yy + 4, stroke=color, stroke_width=1.2, stem=f"ci_high_{i}_{source}")
            b.circle("data", sx(effect), yy, 5.2, fill=color, stroke=WHITE, stem=f"point_{i}_{source}")
        delta = abs(math.log(float(admin["effect"])) - math.log(float(order["effect"])))
        b.text("annotations", 675, y + 5, f"|delta log|={delta:.3f}", size=8.8, fill=MUTED, anchor="end", stem=f"delta_{i}")
    b.text("labels", x0 + w / 2, 505, "Paired OR or HR (log scale)", size=11.5, anchor="middle", stem="x_title")
    b.circle("legend", 315, 532, 5, fill=BLUE, stroke=BLUE, stem="legend_order")
    b.text("legend", 328, 536, "order-defined", size=9.5, stem="legend_order_label")
    b.circle("legend", 440, 532, 5, fill=ORANGE, stroke=ORANGE, stem="legend_admin")
    b.text("legend", 453, 536, "administration-defined", size=9.5, stem="legend_admin_label")
    b.text("annotations", 345, 559, "Measurement stress tests only; estimates are not causal drug effects", size=9.5, fill=MUTED, anchor="middle", stem="claim_boundary")
    return "Figure5_reclassification_and_effect_drift", [a, b], 1130, 570, [(a, 0, 0, 1), (b, 440, 0, 1)]


def svg_qc(path: Path, expected_panels: list[str]) -> dict[str, Any]:
    tree = ET.parse(path)
    root = tree.getroot()
    ids: list[str] = []
    text_n = 0
    image_n = 0
    path_n = 0
    for element in root.iter():
        if "id" in element.attrib:
            ids.append(element.attrib["id"])
        tag = element.tag.split("}")[-1]
        text_n += tag == "text"
        image_n += tag == "image"
        path_n += tag == "path"
    id_counts = Counter(ids)
    duplicate_ids = sorted(key for key, value in id_counts.items() if value > 1)
    required = []
    for panel in expected_panels:
        required.append(f"panel_{panel}")
        required.extend(f"panel_{panel}_{group}" for group in ("axis", "data", "labels", "legend", "annotations"))
    missing_groups = [item for item in required if item not in id_counts]
    return {
        "file": path.name,
        "live_text_n": text_n,
        "image_elements_n": image_n,
        "path_elements_n": path_n,
        "duplicate_ids": duplicate_ids,
        "missing_semantic_groups": missing_groups,
        "clip_paths_n": sum(element.tag.split("}")[-1] == "clipPath" for element in root.iter()),
        "status": "PASS" if text_n > 0 and image_n == 0 and not duplicate_ids and not missing_groups else "FAIL",
    }


def pdf_qc(path: Path) -> dict[str, Any]:
    reader = PdfReader(str(path))
    fonts: set[str] = set()
    image_xobjects = 0
    for page in reader.pages:
        resources = page.get("/Resources", {})
        font_dict = resources.get("/Font", {}) if resources else {}
        for font_ref in font_dict.values():
            font = font_ref.get_object()
            fonts.add(str(font.get("/Subtype", "unknown")))
        xobjects = resources.get("/XObject", {}) if resources else {}
        for xref in xobjects.values():
            obj = xref.get_object()
            if obj.get("/Subtype") == "/Image":
                image_xobjects += 1
    return {
        "file": path.name,
        "pages_n": len(reader.pages),
        "font_subtypes": sorted(fonts),
        "image_xobjects_n": image_xobjects,
        "type3_fonts_present": "/Type3" in fonts,
        "status": "PASS" if image_xobjects == 0 and "/Type3" not in fonts else "FAIL",
    }


def render_preview(pdf_path: Path, png_path: Path, tiff_path: Path) -> None:
    executable = shutil.which("pdftoppm") or shutil.which("pdftoppm.cmd")
    if executable and Path(executable).suffix.lower() == ".cmd":
        bundled_exe = Path(executable).resolve().parents[2] / "native/poppler/Library/bin/pdftoppm.exe"
        if bundled_exe.exists():
            executable = str(bundled_exe)
    if not executable:
        raise RuntimeError("pdftoppm is required to render publication previews")
    prefix = png_path.with_suffix("")
    completed = subprocess.run(
        [executable, "-png", "-r", "300", "-singlefile", str(pdf_path), str(prefix)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not png_path.exists():
        raise RuntimeError(f"pdftoppm failed for {pdf_path}: {completed.stderr}")
    with Image.open(png_path) as image:
        image.convert("RGB").save(tiff_path, format="TIFF", compression="tiff_lzw", dpi=(300, 300))


def write_alt_text(out_dir: Path) -> None:
    content = """# Figure legends and alt text\n\n## Figure 1. Machine-executable medication-exposure provenance architecture\nPanel A shows four evaluated EHR representations passing through version-gated adapters into a canonical medication-event representation while retaining clinical role, native identity, time, event state, and required metadata. Panel B shows the five-dimensional operator, validation states, four deterministic terminal classifications, aggregate comparison, and downstream stress testing.\n\nAlt text: Two-panel architecture diagram. Native EHR, FHIR, OMOP, and eICU sources feed adapters and a canonical event representation. Five operator dimensions labeled source, identity, time, event semantics, and metadata pass through validation gates and produce exposed, unexposed, unresolved, or unmeasurable states.\n\n## Figure 2. Native parity and prespecified operator ablation\nPanel A compares frozen expected and medprov-generated class counts on identical log scales; all points fall on the identity line and 19 of 19 parity checks passed. Panel B shows exposed proportions for table-only, source/class/window, collapsed-semantics, and full exact-identity operators in A1 and A2, plus the fail-closed route-required A1 result.\n\nAlt text: A parity scatterplot places order, strict-administration, and same-class counts exactly on the identity line. Grouped horizontal bars show decreasing exposed proportions as identity and semantics constraints are added; a separate gray callout identifies all route-required A1 units as unmeasurable.\n\n## Figure 3. Bounded cross-representation and cross-database evaluation\nPanel A summarizes supported, partial or relocated, and unavailable provenance capabilities in native MIMIC-IV, matched native/FHIR demonstrations, an OMOP demonstration, and eICU. Panel B reports quantitative matched-demo FHIR identity and time concordance. Panel C shows fail-closed state distributions in OMOP and eICU evaluations.\n\nAlt text: A capability matrix shows that no representation carries every provenance dimension identically. FHIR bars show exact dispense identity and nearly exact first-administration time. Stacked bars show strict OMOP administration becoming unmeasurable when literal state is absent and eICU producing a majority unmeasurable classification.\n\n## Figure 4. Structured reporting validator results\nPanel A reports how often 40 coded MIMIC medication studies supplied each provenance dimension. Panel B shows the narrowing from 40 encoded studies to 7 with a named native source, 2 with executable identity, and none with native event semantics or a complete executable operator.\n\nAlt text: Horizontal bars show 7 of 40 studies naming a native source, 2 specifying executable identity, 35 specifying time, none reporting native event semantics, and 30 reporting dose or route requirements. A funnel ends at zero complete operators.\n\n## Figure 5. Downstream reclassification and effect-estimate stress tests\nPanel A compares full exact-identity with same-class/window administration and reports positive Jaccard agreement, while separately identifying structural route non-measurability. Panel B connects paired order- and administration-defined association estimates under exact-identity, same-class/window, and alternate time-window operators.\n\nAlt text: Stacked bars show class-only exposure added beyond exact identity in both anchors. A connected forest plot shows little drift for some exact-identity pairs but large movement for broad same-class pairs; the plot is explicitly labeled as a measurement stress test rather than a causal drug-effect analysis.\n"""
    (out_dir / "FIGURE_LEGENDS_AND_ALT_TEXT.md").write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    out_dir = (args.output_dir or repo / "manuscript/jbi/figures").resolve()
    data_dir = out_dir / "data"
    qc_dir = out_dir / "qc"
    data_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    builders = [
        figure1(),
        figure2(repo, data_dir),
        figure3(repo, data_dir),
        figure4(repo, data_dir),
        figure5(repo, data_dir),
    ]
    manifest: list[dict[str, Any]] = []
    for stem, panels, width, height, placements in builders:
        save_figure(out_dir, stem, panels, width, height, placements)
        render_preview(out_dir / f"{stem}.pdf", out_dir / f"{stem}.png", out_dir / f"{stem}.tiff")
        svg_result = svg_qc(out_dir / f"{stem}.svg", [panel.letter for panel in panels])
        pdf_result = pdf_qc(out_dir / f"{stem}.pdf")
        result = {"figure": stem, "svg": svg_result, "pdf": pdf_result}
        manifest.append(result)
        (qc_dir / f"{stem}_qc.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        if svg_result["status"] != "PASS" or pdf_result["status"] != "PASS":
            raise RuntimeError(f"QC failed for {stem}: {result}")
        for panel in panels:
            p_stem = f"{stem}_panel_{panel.letter}"
            p_svg = svg_qc(out_dir / "panels" / f"{p_stem}.svg", [panel.letter])
            p_pdf = pdf_qc(out_dir / "panels" / f"{p_stem}.pdf")
            if p_svg["status"] != "PASS" or p_pdf["status"] != "PASS":
                raise RuntimeError(f"Panel QC failed for {p_stem}")

    (qc_dir / "JBI_FIGURE_QC.json").write_text(json.dumps({"figures": manifest}, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["# JBI figure QC", ""]
    for item in manifest:
        lines.append(
            f"- {item['figure']}: SVG {item['svg']['status']} "
            f"({item['svg']['live_text_n']} live text, {item['svg']['image_elements_n']} images); "
            f"PDF {item['pdf']['status']} ({item['pdf']['image_xobjects_n']} image XObjects; "
            f"fonts {', '.join(item['pdf']['font_subtypes'])})."
        )
    (qc_dir / "JBI_FIGURE_QC.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_alt_text(out_dir)
    print(json.dumps({"status": "PASS", "figures_n": len(manifest), "output_dir": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
