from __future__ import annotations

import json
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import matplotlib as mpl

mpl.rcParams["svg.fonttype"] = "none"
mpl.rcParams["pdf.fonttype"] = 42
mpl.rcParams["ps.fonttype"] = 42
mpl.rcParams["text.usetex"] = False

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lxml import etree
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle


PROJECT = Path(__file__).resolve().parents[1]
SOURCE_TABLES = (
    PROJECT / "outputs" / "jamia_observability_v1_1" / "tables"
)
PRE_TABLES = PROJECT / "outputs" / "jamia_pre_submission_v1_0" / "tables"
UPGRADE_TABLES = PROJECT / "outputs" / "jamia_prereview_upgrade_v1_0" / "tables"
RESIDUAL_TABLES = (
    PROJECT / "outputs" / "jamia_residual_provenance_v1_0" / "tables"
)
RW_ROOT = (
    PROJECT
    / "outputs"
    / "researchwrite"
    / "mimic_order_administration_validity_jamia"
)
EXPORTS = RW_ROOT / "exports"
FIGURES = EXPORTS / "figures"
PANELS = FIGURES / "panels"
FIGURE_DATA = EXPORTS / "figure_data"
QA = RW_ROOT / "qa_logs" / "vector_figures"
LOG_PATH = (
    PROJECT
    / "outputs"
    / "jamia_observability_v1_1"
    / "logs"
    / "19_make_jamia_figures.log"
)
MANIFEST_PATH = (
    PROJECT
    / "outputs"
    / "jamia_observability_v1_1"
    / "manifests"
    / "19_make_jamia_figures.json"
)

for directory in (FIGURES, PANELS, FIGURE_DATA, QA, LOG_PATH.parent):
    directory.mkdir(parents=True, exist_ok=True)


NAVY = "#173F5F"
BLUE = "#2878B5"
TEAL = "#2A9D8F"
ORANGE = "#E76F51"
GOLD = "#E9C46A"
SLATE = "#5B6573"
LIGHT_BLUE = "#D7E8F5"
LIGHT_TEAL = "#D7F0EB"
LIGHT_ORANGE = "#F8DED7"
LIGHT_GREY = "#E8EBEF"
GRID = "#D4D9DE"
TEXT = "#1E2933"
WHITE = "#FFFFFF"

CLASS_LABELS = {
    "stress_ulcer_prophylaxis": "Stress-ulcer\nprophylaxis",
    "vte_prophylaxis": "VTE\nprophylaxis",
    "intra_abdominal_antibiotics": "Intra-abdominal\nantibiotic agents",
    "electrolyte_replacement": "Electrolyte\nreplacement",
    "prokinetic": "Prokinetic\nagents",
    "insulin": "Insulin",
}

CORRELATE_LABELS = {
    "OASIS per SD": "OASIS per SD",
    "Night versus day shift": "Night vs day",
    "Active invasive ventilation": "Invasive ventilation",
    "Active vasopressor": "Vasopressor support",
    "Active RRT": "RRT",
}

SVG_NS = "http://www.w3.org/2000/svg"
NS = {"svg": SVG_NS}


def log(message: str) -> None:
    line = f"{datetime.now().astimezone().isoformat()}\t{message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans"],
            "font.size": 9.5,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 9.5,
            "axes.labelcolor": TEXT,
            "axes.edgecolor": SLATE,
            "axes.linewidth": 0.8,
            "xtick.color": SLATE,
            "ytick.color": SLATE,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.5,
            "text.color": TEXT,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
        }
    )


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def set_gid(artist, gid: str):
    artist.set_gid(safe_id(gid))
    return artist


def add_text(
    ax: plt.Axes,
    x: float,
    y: float,
    text: str,
    panel: str,
    name: str,
    category: str = "labels",
    **kwargs,
):
    artist = ax.text(x, y, text, **kwargs)
    return set_gid(artist, f"{category}__{panel}_{name}")


def panel_tag(ax: plt.Axes, panel: str) -> None:
    add_text(
        ax,
        -0.09,
        1.05,
        panel,
        panel,
        "panel_tag",
        category="annotations",
        transform=ax.transAxes,
        fontsize=13,
        fontweight="bold",
        ha="left",
        va="bottom",
        clip_on=False,
    )


def style_axes(ax: plt.Axes, grid_axis: str | None = "x") -> None:
    ax.patch.set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if grid_axis:
        ax.grid(
            axis=grid_axis,
            color=GRID,
            linewidth=0.7,
            linestyle="-",
            alpha=0.8,
            zorder=0,
        )


def load_sources() -> dict[str, pd.DataFrame]:
    names = {
        "coverage": "emar_observability_by_deployment_era.csv",
        "conversion": "order_conversion_by_observability_scope.csv",
        "lag": "first_dose_lag_by_observability_scope.csv",
        "semantics": "not_given_by_observability_scope.csv",
        "correlates": "not_given_corrected_prespecified_correlates.csv",
        "reclassification": "anchor_reclassification_by_scope.csv",
        "effects": "anchor_model_effects_by_population.csv",
        "effect_change": "anchor_effect_change_by_population.csv",
    }
    frames: dict[str, pd.DataFrame] = {}
    for key, name in names.items():
        path = SOURCE_TABLES / name
        if not path.exists():
            raise FileNotFoundError(path)
        frames[key] = pd.read_csv(path)
    pre_names = {
        "operator_conversion": "conversion_strict_vs_class_window_cluster_bootstrap.csv",
        "insulin_states": "insulin_three_state_semantics.csv",
        "class_correlates": "not_given_class_specific_prespecified_correlates.csv",
        "operator_cells": "anchor_operator_outcome_cells.csv",
        "operator_effects": "anchor_operator_model_effects.csv",
        "time_varying_effects": "a2_time_varying_effects.csv",
        "participant_flow": "participant_flow_complete.csv",
    }
    for key, name in pre_names.items():
        path = PRE_TABLES / name
        if not path.exists():
            raise FileNotFoundError(path)
        frames[key] = pd.read_csv(path)
    upgrade_names = {
        "upgrade_cells": "prereview_operator_outcome_cells.csv",
        "a1_provenance": "a1_broad_admin_only_provenance_summary.csv",
        "a2_provenance": "a2_order_window_provenance_summary.csv",
        "upgrade_static": "prereview_static_model_effects.csv",
        "upgrade_concordant": "prereview_concordant_subset_effects.csv",
        "upgrade_bootstrap": "prereview_paired_bootstrap_summary.csv",
        "literature_source": "published_operator_landscape_source_summary.csv",
    }
    for key, name in upgrade_names.items():
        path = UPGRADE_TABLES / name
        if not path.exists():
            raise FileNotFoundError(path)
        frames[key] = pd.read_csv(path)
    residual_names = {
        "literature_reporting": "published_operator_landscape_expanded_reporting_summary.csv",
        "a2_residual_trace": "a2_residual_patient_trace_summary.csv",
    }
    for key, name in residual_names.items():
        path = RESIDUAL_TABLES / name
        if not path.exists():
            raise FileNotFoundError(path)
        frames[key] = pd.read_csv(path)
    return frames


def write_panel_data(frames: dict[str, pd.DataFrame]) -> None:
    coverage = frames["coverage"].copy()
    conversion = frames["conversion"].query(
        "analysis_scope == 'post_implementation'"
    ).copy()
    lag = frames["lag"].query(
        "analysis_scope == 'post_implementation'"
    ).copy()
    fidelity = conversion.merge(
        lag,
        on=["analysis_scope", "drug_class"],
        validate="one_to_one",
    )
    semantics = frames["semantics"].query(
        "analysis_scope == 'post_implementation'"
    ).copy()
    correlates = frames["correlates"].query(
        "analysis_population == 'post_implementation'"
    ).copy()
    reclassification = frames["reclassification"].query(
        "analysis_scope == 'post_implementation'"
    ).copy()
    effects = frames["effects"].query(
        "analysis_population == 'post_implementation'"
    ).copy()
    effect_change = frames["effect_change"].query(
        "analysis_population == 'post_implementation'"
    ).copy()

    figure1_spec = pd.DataFrame(
        [
            ("source", 1, "Treatment intent", "Clinical intention"),
            ("source", 2, "Provider order", "POE + prescription"),
            ("source", 3, "Pharmacy workflow", "Verification and dispensing workflow"),
            ("source", 4, "Documented administration", "eMAR + eMAR detail"),
            ("operator", 1, "Source", "Observability"),
            ("operator", 2, "Identity", "Drug + record"),
            ("operator", 3, "Time", "Origin + window"),
            ("operator", 4, "Semantics", "Event state"),
            ("operator", 5, "Metadata", "Dose + route"),
            ("propagation", 1, "Operator choice", "Alternative admissible rules"),
            ("propagation", 2, "Patient reclassification", "Discordant cells"),
            ("propagation", 3, "Cohort composition", "Different exposed groups"),
            ("propagation", 4, "Effect-estimate drift", "Same outcome model"),
        ],
        columns=["component_type", "display_order", "label", "definition"],
    )

    output = {
        "Figure1_joint_provenance_operator_spec.csv": figure1_spec,
        "Figure2A_observability.csv": coverage,
        "Figure2B_operator_conversion.csv": frames["operator_conversion"],
        "Figure3A_insulin_three_state.csv": frames["insulin_states"],
        "Figure3B_class_workflow.csv": frames["class_correlates"],
        "Figure3B_published_operator_reporting.csv": frames["literature_reporting"],
        "Figure4A_operator_cells.csv": frames["upgrade_cells"],
        "Figure4B_a1_provenance.csv": frames["a1_provenance"],
        "Figure4B_a2_provenance.csv": frames["a2_provenance"],
        "Figure4B_a2_residual_native_key_trace.csv": frames["a2_residual_trace"],
        "Figure4C_operator_effects.csv": frames["upgrade_static"],
        "Figure4C_concordant_effects.csv": frames["upgrade_concordant"],
        "FigureS4_participant_flow.csv": frames["participant_flow"],
        "FigureS5_complete_workflow_estimates.csv": frames["class_correlates"],
    }
    for name, frame in output.items():
        frame.to_csv(FIGURE_DATA / name, index=False)


def draw_framework(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.patch.set_visible(False)

    def tagged_patch(patch, name: str, category: str = "data"):
        ax.add_patch(patch)
        return set_gid(patch, f"{category}__{panel}_{name}")

    def tagged_arrow(
        start: tuple[float, float],
        end: tuple[float, float],
        name: str,
        *,
        color: str = SLATE,
        linewidth: float = 1.2,
        mutation_scale: float = 12,
        category: str = "data",
    ):
        arrow = FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=mutation_scale,
            linewidth=linewidth,
            color=color,
            shrinkA=0,
            shrinkB=0,
        )
        return tagged_patch(arrow, name, category)

    def tagged_line(
        xs: list[float],
        ys: list[float],
        name: str,
        *,
        color: str = SLATE,
        linewidth: float = 1.0,
        linestyle: str = "-",
        category: str = "data",
        zorder: float = 2,
    ):
        line = ax.plot(
            xs,
            ys,
            color=color,
            linewidth=linewidth,
            linestyle=linestyle,
            zorder=zorder,
        )[0]
        return set_gid(line, f"{category}__{panel}_{name}")

    def stage_heading(
        number: str,
        label: str,
        x0: float,
        x1: float,
        color: str,
        name: str,
    ) -> None:
        tagged_patch(
            Circle((x0 + 0.014, 0.850), 0.014, facecolor=color, edgecolor=color),
            f"stage_circle_{name}",
            "annotations",
        )
        add_text(
            ax,
            x0 + 0.014,
            0.850,
            number,
            panel,
            f"stage_number_{name}",
            category="annotations",
            fontsize=8.2,
            fontweight="bold",
            color=WHITE,
            ha="center",
            va="center",
        )
        add_text(
            ax,
            x0 + 0.034,
            0.850,
            label,
            panel,
            f"stage_label_{name}",
            fontsize=9.1,
            fontweight="bold",
            color=color,
            ha="left",
            va="center",
        )
        tagged_line(
            [x0, x1],
            [0.824, 0.824],
            f"stage_rule_{name}",
            color=color,
            linewidth=1.0,
            category="annotations",
        )

    def patient_tile(
        x: float,
        y: float,
        name: str,
        *,
        color: str,
        edge: str,
        fill: str = WHITE,
        width: float = 0.025,
        height: float = 0.050,
    ) -> None:
        tagged_patch(
            FancyBboxPatch(
                (x, y),
                width,
                height,
                boxstyle="round,pad=0.002,rounding_size=0.004",
                facecolor=fill,
                edgecolor=edge,
                linewidth=0.85,
            ),
            f"{name}_tile",
        )
        tagged_patch(
            Circle(
                (x + width / 2, y + height * 0.68),
                height * 0.105,
                facecolor=color,
                edgecolor=color,
                linewidth=0.6,
            ),
            f"{name}_head",
        )
        tagged_patch(
            FancyBboxPatch(
                (x + width * 0.27, y + height * 0.18),
                width * 0.46,
                height * 0.30,
                boxstyle="round,pad=0.001,rounding_size=0.004",
                facecolor=color,
                edgecolor=color,
                linewidth=0.5,
            ),
            f"{name}_body",
        )

    add_text(
        ax,
        0.02,
        0.965,
        "Medication exposure is a resolved joint provenance operator—not a table",
        panel,
        "title",
        fontsize=14.2,
        fontweight="bold",
        ha="left",
        va="top",
    )
    add_text(
        ax,
        0.02,
        0.914,
        "Distinct record layers become analytic exposure only after all five operator dimensions are resolved",
        panel,
        "subtitle",
        fontsize=9.4,
        color=SLATE,
        ha="left",
        va="top",
    )

    stage_heading("1", "CLINICAL DATA GENERATION", 0.025, 0.285, NAVY, "sources")
    stage_heading("2", "RESOLVE THE JOINT OPERATOR", 0.335, 0.715, TEAL, "operator")
    stage_heading("3", "CLASSIFY ANALYTIC EXPOSURE", 0.760, 0.975, NAVY, "classification")

    source_cards = [
        (0.752, "Treatment intent", "clinical intention", LIGHT_GREY, SLATE),
        (0.677, "Provider order", "POE + prescription", LIGHT_BLUE, NAVY),
        (0.602, "Pharmacy workflow", "verification / dispensing", "#F3EAC9", "#8A6A12"),
        (0.527, "Documented administration", "eMAR + eMAR detail", LIGHT_TEAL, TEAL),
    ]
    tagged_line(
        [0.037, 0.037],
        [0.782, 0.548],
        "source_sequence_line",
        color=SLATE,
        linewidth=1.0,
    )
    tagged_arrow(
        (0.037, 0.566),
        (0.037, 0.542),
        "source_sequence_arrow",
        color=SLATE,
        mutation_scale=9,
    )
    for index, (y, heading, subheading, fill, edge) in enumerate(source_cards, start=1):
        tagged_patch(
            Circle((0.037, y + 0.026), 0.012, facecolor=NAVY, edgecolor=NAVY),
            f"source_number_circle_{index}",
        )
        add_text(
            ax,
            0.037,
            y + 0.026,
            str(index),
            panel,
            f"source_number_{index}",
            fontsize=7.3,
            fontweight="bold",
            color=WHITE,
            ha="center",
            va="center",
        )
        tagged_patch(
            FancyBboxPatch(
                (0.055, y),
                0.218,
                0.052,
                boxstyle="round,pad=0.005,rounding_size=0.007",
                facecolor=fill,
                edgecolor=edge,
                linewidth=1.0,
            ),
            f"source_card_{index}",
        )
        tagged_patch(
            Rectangle(
                (0.055, y),
                0.006,
                0.052,
                facecolor=edge,
                edgecolor=edge,
                linewidth=0,
            ),
            f"source_card_accent_{index}",
        )
        add_text(
            ax,
            0.069,
            y + 0.033,
            heading,
            panel,
            f"source_heading_{index}",
            fontsize=8.2,
            fontweight="bold",
            ha="left",
            va="center",
        )
        add_text(
            ax,
            0.069,
            y + 0.015,
            subheading,
            panel,
            f"source_subheading_{index}",
            fontsize=6.8,
            color=SLATE,
            ha="left",
            va="center",
        )
    tagged_patch(
        FancyBboxPatch(
            (0.055, 0.430),
            0.218,
            0.057,
            boxstyle="round,pad=0.004,rounding_size=0.006",
            facecolor=WHITE,
            edgecolor=SLATE,
            linewidth=0.9,
            linestyle="--",
        ),
        "source_boundary_note_box",
        "annotations",
    )
    add_text(
        ax,
        0.164,
        0.458,
        "Distinct provenance layers\nnot interchangeable records",
        panel,
        "source_boundary_note",
        category="annotations",
        fontsize=6.8,
        fontweight="bold",
        color=SLATE,
        ha="center",
        va="center",
        linespacing=1.15,
    )
    tagged_arrow(
        (0.281, 0.635),
        (0.326, 0.635),
        "sources_to_operator",
        color=NAVY,
        linewidth=1.8,
        mutation_scale=15,
    )

    lens_x0, lens_y0, lens_w, lens_h = 0.340, 0.500, 0.375, 0.286
    outer_lens = tagged_patch(
        FancyBboxPatch(
            (lens_x0, lens_y0),
            lens_w,
            lens_h,
            boxstyle="round,pad=0.004,rounding_size=0.045",
            facecolor=WHITE,
            edgecolor="#147A6D",
            linewidth=1.4,
        ),
        "operator_lens_outer",
    )
    operator_dims = [
        ("SOURCE", "observability", LIGHT_TEAL, TEAL),
        ("IDENTITY", "drug + record", "#E3EEF7", NAVY),
        ("TIME", "origin + window", "#F7EBC9", "#8A6A12"),
        ("SEMANTICS", "event state", "#EEE8F6", "#5B3C88"),
        ("METADATA", "dose + route", "#E5EDF7", NAVY),
    ]
    dim_w = lens_w / 5
    for index, (heading, subheading, fill, edge) in enumerate(operator_dims):
        x = lens_x0 + index * dim_w
        segment = Rectangle(
            (x, lens_y0),
            dim_w,
            lens_h,
            facecolor=fill,
            edgecolor="none",
            linewidth=0,
        )
        segment.set_clip_path(outer_lens)
        tagged_patch(segment, f"operator_segment_{index + 1}")
        if index:
            tagged_line(
                [x, x],
                [lens_y0 + 0.010, lens_y0 + lens_h - 0.010],
                f"operator_separator_{index}",
                color=edge,
                linewidth=0.7,
            )
        center_x = x + dim_w / 2
        if index == 0:
            tagged_patch(
                Ellipse(
                    (center_x, 0.693),
                    0.044,
                    0.029,
                    facecolor="none",
                    edgecolor=edge,
                    linewidth=1.1,
                ),
                "operator_icon_source_eye",
            )
            tagged_patch(
                Circle((center_x, 0.693), 0.006, facecolor=edge, edgecolor=edge),
                "operator_icon_source_pupil",
            )
        elif index == 1:
            tagged_patch(
                Circle(
                    (center_x, 0.707), 0.010,
                    facecolor="none", edgecolor=edge, linewidth=1.0,
                ),
                "operator_icon_identity_head",
            )
            tagged_patch(
                FancyBboxPatch(
                    (center_x - 0.020, 0.671),
                    0.040,
                    0.022,
                    boxstyle="round,pad=0.002,rounding_size=0.010",
                    facecolor="none",
                    edgecolor=edge,
                    linewidth=1.0,
                ),
                "operator_icon_identity_body",
            )
        elif index == 2:
            tagged_patch(
                Circle(
                    (center_x, 0.693), 0.023,
                    facecolor="none", edgecolor=edge, linewidth=1.0,
                ),
                "operator_icon_time_clock",
            )
            tagged_line(
                [center_x, center_x],
                [0.693, 0.710],
                "operator_icon_time_hour",
                color=edge,
                linewidth=1.1,
            )
            tagged_line(
                [center_x, center_x + 0.012],
                [0.693, 0.684],
                "operator_icon_time_minute",
                color=edge,
                linewidth=1.1,
            )
        elif index == 3:
            for row_index, yy in enumerate((0.710, 0.693, 0.676)):
                tagged_patch(
                    Circle(
                        (center_x - 0.015, yy), 0.0035,
                        facecolor="none", edgecolor=edge, linewidth=0.9,
                    ),
                    f"operator_icon_semantics_bullet_{row_index}",
                )
                tagged_line(
                    [center_x - 0.006, center_x + 0.019],
                    [yy, yy],
                    f"operator_icon_semantics_line_{row_index}",
                    color=edge,
                    linewidth=1.0,
                )
        else:
            tagged_patch(
                Rectangle(
                    (center_x - 0.017, 0.669),
                    0.034,
                    0.050,
                    facecolor="none",
                    edgecolor=edge,
                    linewidth=1.0,
                ),
                "operator_icon_metadata_document",
            )
            for row_index, yy in enumerate((0.704, 0.692, 0.680)):
                tagged_line(
                    [center_x - 0.010, center_x + 0.010],
                    [yy, yy],
                    f"operator_icon_metadata_line_{row_index}",
                    color=edge,
                    linewidth=0.8,
                )
        add_text(
            ax,
            center_x,
            0.631,
            heading,
            panel,
            f"operator_heading_{index + 1}",
            fontsize=7.4,
            fontweight="bold",
            color=edge,
            ha="center",
            va="center",
        )
        add_text(
            ax,
            center_x,
            0.602,
            subheading,
            panel,
            f"operator_subheading_{index + 1}",
            fontsize=6.5,
            color=TEXT,
            ha="center",
            va="center",
        )
    add_text(
        ax,
        lens_x0 + lens_w / 2,
        0.761,
        "ALL FIVE DIMENSIONS REQUIRED",
        panel,
        "operator_all_required",
        category="annotations",
        fontsize=7.1,
        fontweight="bold",
        color="#147A6D",
        ha="center",
        va="center",
    )
    add_text(
        ax,
        lens_x0 + lens_w / 2,
        0.472,
        "Exposure = source × identity × time × semantics × metadata",
        panel,
        "operator_equation",
        fontsize=7.5,
        fontweight="bold",
        color=NAVY,
        ha="center",
        va="center",
    )
    tagged_patch(
        FancyBboxPatch(
            (0.392, 0.417),
            0.272,
            0.038,
            boxstyle="round,pad=0.004,rounding_size=0.006",
            facecolor=WHITE,
            edgecolor=TEAL,
            linewidth=0.9,
            linestyle="--",
        ),
        "biological_boundary_box",
        "annotations",
    )
    add_text(
        ax,
        0.528,
        0.436,
        "Documented administration ≠ biological exposure",
        panel,
        "biological_boundary",
        category="annotations",
        fontsize=7.1,
        fontweight="bold",
        color="#147A6D",
        ha="center",
        va="center",
    )
    tagged_arrow(
        (0.720, 0.635),
        (0.750, 0.635),
        "operator_to_classification",
        color=TEAL,
        linewidth=1.8,
        mutation_scale=15,
    )

    classification_rows = [
        (0.704, "Exposed", TEAL, [TEAL, TEAL, TEAL, TEAL]),
        (0.616, "Unexposed", NAVY, [NAVY, NAVY, NAVY, NAVY]),
        (0.528, "Discordant\nacross operators", ORANGE, [SLATE, ORANGE, SLATE, ORANGE]),
    ]
    for row_index, (y, label, label_color, people_colors) in enumerate(classification_rows):
        add_text(
            ax,
            0.765,
            y + 0.025,
            label,
            panel,
            f"classification_label_{row_index}",
            fontsize=7.0,
            fontweight="bold",
            color=label_color,
            ha="left",
            va="center",
            linespacing=1.1,
        )
        for tile_index, person_color in enumerate(people_colors):
            patient_tile(
                0.864 + tile_index * 0.029,
                y,
                f"classification_{row_index}_{tile_index}",
                color=person_color,
                edge=person_color,
                fill=WHITE,
            )
    add_text(
        ax,
        0.868,
        0.450,
        "Same records; admissible operators can disagree",
        panel,
        "classification_note",
        category="annotations",
        fontsize=6.8,
        color=SLATE,
        ha="center",
        va="center",
    )

    tagged_patch(
        FancyBboxPatch(
            (0.025, 0.060),
            0.950,
            0.305,
            boxstyle="round,pad=0.006,rounding_size=0.010",
            facecolor="#FFF9F7",
            edgecolor=ORANGE,
            linewidth=1.0,
        ),
        "propagation_lane",
        "annotations",
    )
    add_text(
        ax,
        0.500,
        0.348,
        "4   PROPAGATION THROUGH DISCORDANT PATIENT CELLS",
        panel,
        "propagation_heading",
        category="annotations",
        fontsize=9.2,
        fontweight="bold",
        color=ORANGE,
        ha="center",
        va="center",
    )
    module_centers = [0.145, 0.385, 0.625, 0.860]
    module_labels = [
        "Operator choice",
        "Patient reclassification",
        "Cohort composition",
        "Effect-estimate drift",
    ]
    for index, (center, label) in enumerate(zip(module_centers, module_labels)):
        add_text(
            ax,
            center,
            0.305,
            label,
            panel,
            f"propagation_label_{index + 1}",
            fontsize=8.0,
            fontweight="bold",
            color=ORANGE if index else NAVY,
            ha="center",
            va="center",
        )

    mini_x0, mini_y0, mini_w, mini_h = 0.087, 0.142, 0.116, 0.098
    mini_outer = tagged_patch(
        FancyBboxPatch(
            (mini_x0, mini_y0),
            mini_w,
            mini_h,
            boxstyle="round,pad=0.003,rounding_size=0.020",
            facecolor=WHITE,
            edgecolor=NAVY,
            linewidth=1.0,
        ),
        "propagation_operator_outer",
    )
    for index, fill in enumerate((LIGHT_TEAL, "#E3EEF7", "#F7EBC9", "#EEE8F6", "#E5EDF7")):
        segment = Rectangle(
            (mini_x0 + index * mini_w / 5, mini_y0),
            mini_w / 5,
            mini_h,
            facecolor=fill,
            edgecolor=SLATE,
            linewidth=0.35,
        )
        segment.set_clip_path(mini_outer)
        tagged_patch(segment, f"propagation_operator_segment_{index + 1}")
    add_text(
        ax,
        0.145,
        0.115,
        "change one or more rules",
        panel,
        "propagation_operator_note",
        category="annotations",
        fontsize=6.5,
        color=SLATE,
        ha="center",
        va="center",
    )

    reclass_colors = [SLATE, SLATE, ORANGE, NAVY, SLATE, ORANGE, NAVY, NAVY]
    for index, person_color in enumerate(reclass_colors):
        row, col = divmod(index, 4)
        patient_tile(
            0.329 + col * 0.030,
            0.177 - row * 0.062,
            f"propagation_reclass_{index}",
            color=person_color,
            edge=ORANGE if person_color == ORANGE else SLATE,
            fill=WHITE,
            width=0.025,
            height=0.048,
        )
    tagged_arrow(
        (0.365, 0.176),
        (0.414, 0.145),
        "propagation_reclass_move_1",
        color=ORANGE,
        linewidth=0.9,
        mutation_scale=8,
        category="annotations",
    )
    tagged_arrow(
        (0.395, 0.114),
        (0.444, 0.145),
        "propagation_reclass_move_2",
        color=ORANGE,
        linewidth=0.9,
        mutation_scale=8,
        category="annotations",
    )

    for index, color in enumerate((TEAL, TEAL, TEAL, NAVY, NAVY, NAVY)):
        x = 0.565 + (index % 3) * 0.030
        y = 0.176 if index < 3 else 0.118
        patient_tile(
            x,
            y,
            f"propagation_cohort_{index}",
            color=color,
            edge=color,
            fill=WHITE,
            width=0.025,
            height=0.048,
        )
    for index in range(2):
        patient_tile(
            0.660 + index * 0.030,
            0.118,
            f"propagation_discordant_cohort_{index}",
            color=ORANGE,
            edge=ORANGE,
            fill="#FFF1ED",
            width=0.025,
            height=0.048,
        )

    tagged_line(
        [0.790, 0.943],
        [0.132, 0.132],
        "effect_axis",
        color=SLATE,
        linewidth=0.9,
    )
    tagged_line(
        [0.858, 0.858],
        [0.102, 0.236],
        "effect_null",
        color=SLATE,
        linewidth=0.8,
        linestyle="--",
        category="annotations",
    )
    for index, (y, low, point, high, color) in enumerate(
        (
            (0.198, 0.814, 0.846, 0.878, NAVY),
            (0.158, 0.872, 0.904, 0.936, ORANGE),
        )
    ):
        tagged_line(
            [low, high],
            [y, y],
            f"effect_interval_{index}",
            color=color,
            linewidth=1.6,
        )
        tagged_line(
            [low, low],
            [y - 0.009, y + 0.009],
            f"effect_interval_left_{index}",
            color=color,
            linewidth=1.0,
        )
        tagged_line(
            [high, high],
            [y - 0.009, y + 0.009],
            f"effect_interval_right_{index}",
            color=color,
            linewidth=1.0,
        )
        tagged_patch(
            Circle((point, y), 0.006, facecolor=color, edgecolor=WHITE, linewidth=0.7),
            f"effect_point_{index}",
        )
    add_text(
        ax,
        0.865,
        0.106,
        "same outcome model",
        panel,
        "effect_model_note",
        category="annotations",
        fontsize=6.5,
        color=SLATE,
        ha="center",
        va="center",
    )
    for index, (start, end) in enumerate(
        (
            ((0.224, 0.190), (0.292, 0.190)),
            ((0.468, 0.190), (0.525, 0.190)),
            ((0.718, 0.190), (0.768, 0.190)),
        )
    ):
        tagged_arrow(
            start,
            end,
            f"propagation_arrow_{index + 1}",
            color=ORANGE,
            linewidth=1.5,
            mutation_scale=13,
        )
    add_text(
        ax,
        0.500,
        0.079,
        "Discordant cells carry provenance choices into cohort composition and estimates",
        panel,
        "propagation_note",
        category="annotations",
        fontsize=7.2,
        fontweight="bold",
        color=ORANGE,
        ha="center",
        va="center",
    )


def draw_observability(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    style_axes(ax, "y")
    coverage = frames["coverage"].copy()
    order = [
        "pre_implementation",
        "implementation_overlap",
        "post_implementation",
    ]
    labels = ["Pre-\nimplementation", "Implementation\noverlap", "Post-\nimplementation"]
    coverage["deployment_era"] = pd.Categorical(
        coverage["deployment_era"], categories=order, ordered=True
    )
    coverage = coverage.sort_values("deployment_era")
    x = np.arange(3)
    y = coverage["adult_stays_with_any_emar_pct"].to_numpy()
    bars = ax.bar(
        x,
        y,
        width=0.62,
        color=[LIGHT_GREY, GOLD, TEAL],
        edgecolor=[SLATE, "#997C1D", "#147A6D"],
        linewidth=1.1,
        zorder=2,
    )
    for index, bar in enumerate(bars):
        set_gid(bar, f"data__{panel}_coverage_bar_{index}")
    line = ax.plot(x, y, color=NAVY, marker="o", linewidth=1.5, zorder=3)[0]
    set_gid(line, f"data__{panel}_coverage_line")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Adult ICU stays with any admission eMAR row, %")
    ax.set_title("Administration-layer observability")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.yaxis.label.set_gid(f"labels__{panel}_ylabel")
    for index, value in enumerate(y):
        add_text(
            ax,
            index,
            value + 3.1,
            f"{value:.2f}%",
            panel,
            f"coverage_value_{index}",
            category="annotations",
            fontsize=9.5,
            fontweight="bold",
            color=NAVY,
            ha="center",
            va="bottom",
        )
    add_text(
        ax,
        0.02,
        0.98,
        "2014–2016 source-corrected deployment interval",
        panel,
        "deployment_note",
        category="annotations",
        transform=ax.transAxes,
        fontsize=8.3,
        color=SLATE,
        ha="left",
        va="top",
    )
    panel_tag(ax, panel)


def draw_conversion(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    style_axes(ax, "x")
    data = frames["operator_conversion"].query(
        "drug_class != 'all_classes'"
    ).copy()
    data = data.sort_values("strict_identity_conversion_pct")
    y = np.arange(len(data))
    strict = data["strict_identity_conversion_pct"].to_numpy()
    broad = data["class_window_conversion_pct"].to_numpy()
    for index in range(len(data)):
        connector = ax.plot(
            [strict[index], broad[index]], [y[index], y[index]],
            color=GRID, linewidth=2.0, zorder=1,
        )[0]
        set_gid(connector, f"data__{panel}_operator_connector_{index}")
        for source_index, (value, low, high, offset, color, marker, label) in enumerate([
            (
                strict[index],
                data.iloc[index]["strict_cluster_boot_ci_low_pct"],
                data.iloc[index]["strict_cluster_boot_ci_high_pct"],
                -0.11, NAVY, "o", "Strict POE identity",
            ),
            (
                broad[index],
                data.iloc[index]["class_window_cluster_boot_ci_low_pct"],
                data.iloc[index]["class_window_cluster_boot_ci_high_pct"],
                0.11, ORANGE, "D", "Same class/window",
            ),
        ]):
            line = ax.plot(
                [low, high], [y[index] + offset, y[index] + offset],
                color=color, linewidth=1.6, zorder=2,
            )[0]
            set_gid(line, f"data__{panel}_conversion_ci_{index}_{source_index}")
            point = ax.scatter(
                value, y[index] + offset, s=46, marker=marker, color=color,
                edgecolor=WHITE, linewidth=0.7,
                label=label if index == 0 else None, zorder=3,
            )
            set_gid(point, f"data__{panel}_conversion_point_{index}_{source_index}")
        add_text(
            ax,
            98.5,
            y[index],
            f"+{data.iloc[index]['absolute_conversion_gain_pct_points']:.1f} pp",
            panel,
            f"conversion_gain_{index}",
            category="annotations",
            fontsize=8.0,
            fontweight="bold",
            color=ORANGE,
            ha="right",
            va="center",
        )
    ax.set_yticks(
        y,
        [CLASS_LABELS[value] for value in data["drug_class"]],
    )
    ax.set_xlim(45, 100)
    ax.set_xlabel("Order units reconciled to a strict-positive eMAR event, %")
    ax.set_title("Conversion depends on the identity operator")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.xaxis.label.set_gid(f"labels__{panel}_xlabel")
    add_text(
        ax,
        0.01,
        -0.16,
        "Labels show broad-minus-strict gain; 1,000 subject-cluster bootstraps",
        panel,
        "coverage_context",
        category="annotations",
        transform=ax.transAxes,
        fontsize=8.3,
        color=SLATE,
        ha="left",
        va="top",
        clip_on=False,
    )
    legend = ax.legend(loc="upper left", frameon=False)
    legend.set_gid(f"legend__{panel}_conversion_operator")
    panel_tag(ax, panel)


def draw_semantics(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    style_axes(ax, "x")
    data = frames["insulin_states"].copy()
    state_order = [
        "strict_documented_administration",
        "protocol_not_indicated_sliding_scale",
        "other_primary_not_given",
    ]
    colors = [TEAL, GOLD, ORANGE]
    labels = [
        "Strict administration",
        "Protocol nonindication",
        "Other not-given",
    ]
    subset = data.set_index("semantic_state").loc[state_order]
    left = 0.0
    for index, (state, color, label) in enumerate(zip(state_order, colors, labels)):
        value = float(subset.loc[state, "three_state_pct"])
        bar = ax.barh(
            [0], [value], left=[left], height=0.46, color=color,
            edgecolor=WHITE, linewidth=1.0, label=label,
        )[0]
        set_gid(bar, f"data__{panel}_insulin_state_{index}")
        add_text(
            ax, left + value / 2, 0, f"{value:.1f}%", panel,
            f"state_value_{index}", category="annotations", fontsize=10,
            fontweight="bold", color=WHITE if index != 1 else TEXT,
            ha="center", va="center",
        )
        label_x = left + value / 2
        label_y = 0.34
        label_ha = "center"
        label_size = 7.4
        if index == 1:
            label_x -= 1.8
        elif index == 2:
            label_x = 99.0
            label_y = 0.49
            label_ha = "right"
            label_size = 6.8
        add_text(
            ax, label_x, label_y, label, panel,
            f"state_label_{index}", category="labels", fontsize=label_size,
            fontweight="bold", color=color, ha=label_ha, va="center",
        )
        left += value
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.65, 0.75)
    ax.set_yticks([0], ["Insulin"])
    ax.set_xlabel("Events, %")
    ax.set_title("Protocol nonindication is not failed administration")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.xaxis.label.set_gid(f"labels__{panel}_xlabel")
    excluded = data[data["three_state_pct"].isna()]["events_n"].sum()
    add_text(
        ax,
        0.01,
        0.98,
        f"n={int(subset['events_n'].sum()):,}; {int(excluded):,} excluded-state events remain outside this denominator",
        panel,
        "insulin_denominator_note",
        category="annotations",
        transform=ax.transAxes,
        fontsize=8.0,
        color=SLATE,
        ha="left",
        va="top",
    )
    panel_tag(ax, panel)


def draw_correlates(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    data = frames["class_correlates"].query(
        "event_mapping == 'frozen_primary'"
    ).copy()
    classes = [
        "electrolyte_replacement", "insulin", "intra_abdominal_antibiotics",
        "prokinetic", "stress_ulcer_prophylaxis", "vte_prophylaxis",
    ]
    terms = [
        "oasis_z", "shiftnight_1900_0659", "invasive_ventilation_active",
        "vasopressor_active", "rrt_active",
    ]
    term_labels = ["OASIS\nper SD", "Night\nvs day", "Invasive\nventilation", "Vasopressor", "RRT"]
    indexed = data.set_index(["drug_class", "term"])
    matrix = np.array([
        [math.log2(float(indexed.loc[(drug_class, term), "adjusted_or"])) for term in terms]
        for drug_class in classes
    ])
    vmin, vmax = -0.9, 0.9
    color_norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
    color_map = mpl.colormaps["RdBu_r"]
    # Draw every heatmap cell and colorbar swatch as a vector rectangle.  This
    # avoids the embedded SVG/PDF images created by imshow/colorbar gradients.
    for row_index in range(matrix.shape[0]):
        for col_index in range(matrix.shape[1]):
            cell = Rectangle(
                (col_index - 0.5, row_index - 0.5),
                1,
                1,
                facecolor=color_map(color_norm(matrix[row_index, col_index])),
                edgecolor=WHITE,
                linewidth=0.35,
            )
            ax.add_patch(cell)
            set_gid(cell, f"data__{panel}_heatmap_cell_{row_index}_{col_index}")
    for row_index, drug_class in enumerate(classes):
        for col_index, term in enumerate(terms):
            row = indexed.loc[(drug_class, term)]
            estimate = float(row["adjusted_or"])
            significant = float(row["ci_low"]) > 1 or float(row["ci_high"]) < 1
            add_text(
                ax, col_index, row_index,
                f"{estimate:.2f}{'*' if significant else ''}", panel,
                f"heatmap_value_{row_index}_{col_index}",
                category="annotations", fontsize=7.7, fontweight="bold",
                color=WHITE if abs(matrix[row_index, col_index]) > 0.42 else TEXT,
                ha="center", va="center",
            )
    ax.set_xticks(np.arange(len(terms)), term_labels)
    ax.set_yticks(np.arange(len(classes)), [CLASS_LABELS[value] for value in classes])
    ax.set_xlim(-0.5, 5.75)
    ax.set_ylim(len(classes) - 0.5, -0.5)
    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Adjusted OR for primary not-given documentation (*95% CI excludes 1)")
    ax.set_title("Workflow associations are medication-class specific")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.xaxis.label.set_gid(f"labels__{panel}_xlabel")
    swatches = 36
    colorbar_x = 5.08
    colorbar_width = 0.18
    colorbar_height = len(classes) / swatches
    for index in range(swatches):
        value = vmax - (index + 0.5) * (vmax - vmin) / swatches
        swatch = Rectangle(
            (colorbar_x, -0.5 + index * colorbar_height),
            colorbar_width,
            colorbar_height,
            facecolor=color_map(color_norm(value)),
            edgecolor="none",
        )
        ax.add_patch(swatch)
        set_gid(swatch, f"legend__{panel}_colorbar_swatch_{index}")
    outline = Rectangle(
        (colorbar_x, -0.5), colorbar_width, len(classes),
        facecolor="none", edgecolor=SLATE, linewidth=0.7,
    )
    ax.add_patch(outline)
    set_gid(outline, f"legend__{panel}_colorbar_outline")
    for tick in (-0.8, -0.4, 0.0, 0.4, 0.8):
        tick_y = -0.5 + (vmax - tick) / (vmax - vmin) * len(classes)
        tick_line = ax.plot(
            [colorbar_x + colorbar_width, colorbar_x + colorbar_width + 0.06],
            [tick_y, tick_y], color=SLATE, linewidth=0.7,
        )[0]
        set_gid(tick_line, f"legend__{panel}_colorbar_tick_{tick}")
        add_text(
            ax, colorbar_x + colorbar_width + 0.10, tick_y, f"{tick:.1f}",
            panel, f"colorbar_tick_label_{tick}", category="legend",
            fontsize=7.2, color=SLATE, ha="left", va="center",
        )
    add_text(
        ax, 5.68, 2.5, "log2(OR)", panel, "colorbar_label",
        category="legend", fontsize=8.0, color=TEXT, ha="center",
        va="center", rotation=90,
    )
    add_text(
        ax, 0.01, -0.12,
        "Semantic audit changed insulin night-shift OR from 0.86 to 1.03",
        panel, "insulin_semantic_reversal", category="annotations",
        transform=ax.transAxes, fontsize=8.0, fontweight="bold", color=ORANGE,
        ha="left", va="top", clip_on=False,
    )
    panel_tag(ax, panel)


def draw_reclassification(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    style_axes(ax, "x")
    data = frames["operator_cells"].copy()
    rowspec = [
        ("A1", "strict_poe_identity", "A1 strict"),
        ("A1", "broad_class_window", "A1 broad"),
        ("A2", "strict_poe_identity", "A2 strict"),
        ("A2", "broad_class_window", "A2 broad"),
    ]
    categories = [
        ((1, 1), "Both positive", TEAL),
        ((1, 0), "Order only", NAVY),
        ((0, 1), "Administration only", ORANGE),
        ((0, 0), "Neither", LIGHT_GREY),
    ]
    y = np.arange(len(rowspec))
    left = np.zeros(len(rowspec))
    totals = []
    cell_counts: list[dict[tuple[int, int], int]] = []
    for anchor, operator, _ in rowspec:
        subset = data[(data["anchor_id"] == anchor) & (data["operator"] == operator)]
        counts = {
            (int(row.order_exposure), int(row.administration_exposure)): int(row.patients_n)
            for row in subset.itertuples()
        }
        cell_counts.append(counts)
        totals.append(sum(counts.values()))
    for category_index, (cell, label, color) in enumerate(categories):
        values = np.array([
            100 * counts.get(cell, 0) / total
            for counts, total in zip(cell_counts, totals)
        ])
        bars = ax.barh(
            y,
            values,
            left=left,
            height=0.52,
            color=color,
            edgecolor=WHITE,
            linewidth=0.8,
            label=label,
        )
        for row_index, bar in enumerate(bars):
            set_gid(
                bar,
                f"data__{panel}_reclassification_{category_index}_{row_index}",
            )
            if values[row_index] >= 5:
                add_text(
                    ax,
                    left[row_index] + values[row_index] / 2,
                    y[row_index],
                    f"{values[row_index]:.1f}%",
                    panel,
                    f"reclass_value_{category_index}_{row_index}",
                    category="annotations",
                    fontsize=8,
                    fontweight="bold",
                    color=WHITE if color != LIGHT_GREY else SLATE,
                    ha="center",
                    va="center",
                )
        left += values
    ax.set_xlim(0, 100)
    ax.set_yticks(y, [label for _, _, label in rowspec])
    ax.invert_yaxis()
    ax.set_xlabel("Post-implementation anchor cohort, %")
    ax.set_title("Removing POE identity changes the exposed population")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.xaxis.label.set_gid(f"labels__{panel}_xlabel")
    legend = ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.23),
        ncol=2,
        frameon=False,
    )
    legend.set_gid(f"legend__{panel}_classification")
    for index, counts in enumerate(cell_counts):
        discordant = counts.get((1, 0), 0) + counts.get((0, 1), 0)
        add_text(
            ax,
            99.5,
            y[index] + 0.18,
            f"Discordant {100 * discordant / totals[index]:.1f}%",
            panel,
            f"agreement_{index}",
            category="annotations",
            fontsize=7.6,
            color=SLATE,
            ha="right",
            va="center",
        )
    panel_tag(ax, panel)


def draw_effect_drift(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    style_axes(ax, "x")
    static = frames["operator_effects"].query(
        "model_variant == 'published_style_minimal'"
    ).copy()
    tv = frames["time_varying_effects"].query(
        "model_variant == 'time_varying_minimal'"
    ).copy()

    def static_row(anchor: str, operator: str, source: str) -> pd.Series:
        return static[
            static["anchor_id"].eq(anchor)
            & static["operator"].eq(operator)
            & static["exposure_source"].eq(source)
        ].iloc[0]

    rows = [
        (
            "A1  static minimal",
            [
                static_row("A1", "strict_poe_identity", "order"),
                static_row("A1", "strict_poe_identity", "administration"),
                static_row("A1", "broad_class_window", "administration"),
            ],
            "aligned Δlog CI crosses 0",
        ),
        (
            "A2  static minimal",
            [
                static_row("A2", "strict_poe_identity", "order"),
                static_row("A2", "strict_poe_identity", "administration"),
                static_row("A2", "broad_class_window", "administration"),
            ],
            "broad Δlog CI excludes 0",
        ),
        (
            "A2  time-varying minimal",
            [
                tv[tv["exposure_source"].eq("order")].iloc[0],
                tv[tv["exposure_source"].eq("strict_administration")].iloc[0],
                tv[tv["exposure_source"].eq("broad_administration")].iloc[0],
            ],
            "broad Δlog CI excludes 0",
        ),
    ]
    y = np.arange(len(rows))[::-1]
    definitions = [
        ("Order", NAVY, "s", -0.15),
        ("Strict administration", TEAL, "o", 0.0),
        ("Broad administration", ORANGE, "D", 0.15),
    ]
    for index, (label, effect_rows, annotation) in enumerate(rows):
        estimates = [float(row["effect"]) for row in effect_rows]
        connector = ax.plot(
            [min(estimates), max(estimates)], [y[index], y[index]],
            color=GRID, linewidth=1.8, zorder=1,
        )[0]
        set_gid(connector, f"data__{panel}_effect_connector_{index}")
        for definition_index, (row, (definition, color, marker, offset)) in enumerate(
            zip(effect_rows, definitions)
        ):
            line = ax.plot(
                [row["ci_low"], row["ci_high"]],
                [y[index] + offset, y[index] + offset],
                color=color, linewidth=1.5, zorder=2,
            )[0]
            set_gid(line, f"data__{panel}_effect_ci_{index}_{definition_index}")
            point = ax.scatter(
                row["effect"], y[index] + offset, s=46, marker=marker,
                color=color, edgecolor=WHITE, linewidth=0.7,
                label=definition if index == 0 else None, zorder=3,
            )
            set_gid(point, f"data__{panel}_effect_point_{index}_{definition_index}")
    null = ax.axvline(1, color=SLATE, linewidth=1, linestyle="--")
    set_gid(null, f"annotations__{panel}_null_line")
    ax.set_xscale("log")
    ax.set_xlim(0.82, 2.65)
    ax.set_xticks([0.85, 1.0, 1.25, 1.5, 2.0, 2.5])
    ax.get_xaxis().set_major_formatter(mpl.ticker.ScalarFormatter())
    ax.set_yticks(y, [label for label, _, _ in rows])
    ax.set_xlabel("Association estimate (OR for A1; HR for A2)")
    ax.set_title("Identity-aligned sources agree; broad operators diverge")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.xaxis.label.set_gid(f"labels__{panel}_xlabel")
    legend = ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=3,
        frameon=False,
    )
    legend.set_gid(f"legend__{panel}_exposure_source")
    panel_tag(ax, panel)


def draw_literature_reporting(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    style_axes(ax, "x")
    data = frames["literature_reporting"].copy()
    order = [
        "Time origin and exposure window",
        "Dose or route constraint",
        "Named native medication table/source",
        "Database-executable identity rule",
        "Native event-state semantics",
        "Fully executable operator",
    ]
    data = data.set_index("reporting_dimension").loc[order].reset_index()
    y = np.arange(len(data))[::-1]
    colors = [TEAL, TEAL, ORANGE, ORANGE, ORANGE, NAVY]
    bars = ax.barh(
        y,
        data["reported_percent"],
        height=0.58,
        color=colors,
        edgecolor=WHITE,
        linewidth=0.8,
        zorder=2,
    )
    for index, bar in enumerate(bars):
        set_gid(bar, f"data__{panel}_literature_reporting_bar_{index}")
        value = float(data.iloc[index]["reported_percent"])
        add_text(
            ax,
            min(value + 2.3, 97),
            y[index],
            f"{int(data.iloc[index]['reported_n'])}/40",
            panel,
            f"literature_reporting_value_{index}",
            category="annotations",
            fontsize=8.6,
            fontweight="bold",
            color=TEXT,
            ha="left" if value < 90 else "right",
            va="center",
        )
    labels = [
        "Time origin + window",
        "Dose or route",
        "Native source/table",
        "Executable identity",
        "Native event semantics",
        "Complete operator",
    ]
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Studies reporting the operator dimension, %")
    ax.set_title("Published exposures are rarely executable")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.xaxis.label.set_gid(f"labels__{panel}_xlabel")
    add_text(
        ax,
        0.01,
        -0.14,
        "First 40 eligible reports in a frozen randomized open-full-text sequence",
        panel,
        "literature_sample_note",
        category="annotations",
        transform=ax.transAxes,
        fontsize=8.0,
        color=SLATE,
        ha="left",
        va="top",
        clip_on=False,
    )
    panel_tag(ax, panel)


def draw_reclassification(ax: plt.Axes, panel: str, frames) -> None:
    """Outcome risk in the complete original broad 2x2 cells."""
    ax.set_gid(f"panel_{panel}")
    ax.set_xlim(-0.45, 2.35)
    ax.set_ylim(-0.35, 5.65)
    ax.axis("off")
    data = frames["upgrade_cells"].copy()
    cmap = mpl.colormaps["Blues"]
    norm = mpl.colors.Normalize(vmin=0, vmax=70)
    specs = [
        ("A1", "original_broad", 3.15, "A1 VTE  |  in-hospital mortality"),
        ("A2", "original_broad", 0.65, "A2 PPI  |  90-day mortality"),
    ]
    add_text(
        ax, 0.98, 5.48, "Outcome risk separates discordant cells", panel,
        "matrix_global_title", fontsize=10.2, fontweight="bold", color=TEXT,
        ha="center", va="center",
    )
    for group_index, (anchor, comparison, y0, title) in enumerate(specs):
        subset = data[
            data["anchor_id"].eq(anchor)
            & data["comparison"].eq(comparison)
        ]
        lookup = {
            (int(row.order_exposure), int(row.administration_exposure)): row
            for row in subset.itertuples()
        }
        add_text(
            ax,
            0.98,
            y0 + 1.78,
            title,
            panel,
            f"matrix_title_{group_index}",
            fontsize=9.3,
            fontweight="bold",
            color=NAVY,
            ha="center",
            va="center",
        )
        for order_value in (1, 0):
            for admin_value in (0, 1):
                row = lookup[(order_value, admin_value)]
                xpos = admin_value * 1.05
                ypos = y0 + (0.82 if order_value == 1 else 0.0)
                risk = float(row.outcome_pct)
                rect = Rectangle(
                    (xpos, ypos),
                    0.98,
                    0.76,
                    facecolor=cmap(norm(risk)),
                    edgecolor=WHITE,
                    linewidth=1.2,
                )
                ax.add_patch(rect)
                set_gid(
                    rect,
                    f"data__{panel}_cell_{anchor}_{order_value}_{admin_value}",
                )
                add_text(
                    ax,
                    xpos + 0.49,
                    ypos + 0.45,
                    f"n={int(row.patients_n):,}",
                    panel,
                    f"cell_n_{anchor}_{order_value}_{admin_value}",
                    category="annotations",
                    fontsize=8.0,
                    fontweight="bold",
                    color=WHITE if risk > 35 else TEXT,
                    ha="center",
                    va="center",
                )
                add_text(
                    ax,
                    xpos + 0.49,
                    ypos + 0.22,
                    f"{risk:.2f}%",
                    panel,
                    f"cell_risk_{anchor}_{order_value}_{admin_value}",
                    category="annotations",
                    fontsize=9.2,
                    fontweight="bold",
                    color=WHITE if risk > 35 else NAVY,
                    ha="center",
                    va="center",
                )
        for admin_value, label in ((0, "Broad administration −"), (1, "Broad administration +")):
            add_text(
                ax,
                admin_value * 1.05 + 0.49,
                y0 - 0.12,
                label,
                panel,
                f"admin_label_{group_index}_{admin_value}",
                fontsize=7.1,
                color=SLATE,
                ha="center",
                va="top",
            )
        add_text(
            ax,
            -0.05,
            y0 + 1.20,
            "Order +",
            panel,
            f"order_plus_{group_index}",
            fontsize=7.4,
            color=SLATE,
            ha="right",
            va="center",
        )
        add_text(
            ax,
            -0.05,
            y0 + 0.38,
            "Order −",
            panel,
            f"order_minus_{group_index}",
            fontsize=7.4,
            color=SLATE,
            ha="right",
            va="center",
        )
    add_text(
        ax,
        0.98,
        -0.18,
        "Cells show n and observed outcome risk",
        panel,
        "matrix_note",
        category="annotations",
        fontsize=7.3,
        color=SLATE,
        ha="center",
        va="bottom",
    )
    panel_tag(ax, panel)


def draw_provenance(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    style_axes(ax, "x")
    a1 = frames["a1_provenance"].copy()
    a2 = frames["a2_provenance"].copy()
    a1_labels = {
        "vte_prescription_elsewhere_in_admission": "A1: order elsewhere in admission",
        "same_poe_vte_prescription_outside_original_eligibility": "A1: same POE outside eligibility",
        "observed_metadata_inconsistent_with_prophylaxis": "A1: metadata inconsistent",
        "different_poe_vte_order_assigned_to_icu_stay": "A1: different ICU-assigned POE",
        "no_mapped_vte_prescription_in_admission": "A1: no mapped order",
    }
    a2_labels = {
        "different_poe_hospital_overlap_order_in_admission": "A2: different-POE order",
        "same_poe_hospital_overlap_order_outside_original_window": "A2: same POE outside window",
        "emar_poe_missing_or_not_identity_resolvable": "A2: eMAR identity unresolved",
    }
    rows: list[tuple[str, float, int, float, str]] = []
    a1_total = int(a1["patients_n"].sum())
    for row in a1.itertuples():
        rows.append((
            a1_labels[row.provenance_category],
            100 * int(row.patients_n) / a1_total,
            int(row.patients_n),
            float(row.hospital_death_pct),
            "A1",
        ))
    a2_total = int(a2["patients_n"].sum())
    for row in a2.itertuples():
        if row.provenance_category == "no_hospital_overlap_ppi_order_in_admission":
            continue
        rows.append((
            a2_labels[row.provenance_category],
            100 * int(row.patients_n) / a2_total,
            int(row.patients_n),
            float(row.death_90d_pct),
            "A2",
        ))
    residual_labels = {
        "direct_pharmacy_id_to_ppi_prescription": "A2: pharmacy-linked PPI Rx",
        "no_resolved_pharmacy_record_or_ppi_prescription": "A2: unresolved residual",
    }
    for row in frames["a2_residual_trace"].itertuples():
        rows.append((
            residual_labels[row.trace_category],
            100 * int(row.patients_n) / a2_total,
            int(row.patients_n),
            float(row.death_90d_pct),
            "A2",
        ))
    positions = list(range(5)) + list(range(6, 11))
    colors = [BLUE if item[4] == "A1" else ORANGE for item in rows]
    bars = ax.barh(
        positions,
        [item[1] for item in rows],
        height=0.58,
        color=colors,
        edgecolor=WHITE,
        linewidth=0.8,
        zorder=2,
    )
    for index, bar in enumerate(bars):
        set_gid(bar, f"data__{panel}_provenance_bar_{index}")
        pct = rows[index][1]
        add_text(
            ax,
            min(pct + 1.2, 76),
            positions[index],
            f"n={rows[index][2]:,}; outcome {rows[index][3]:.2f}%",
            panel,
            f"provenance_value_{index}",
            category="annotations",
            fontsize=7.1,
            color=TEXT,
            ha="left" if pct < 72 else "right",
            va="center",
        )
    ax.set_yticks(positions, [item[0] for item in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 80)
    ax.set_xlabel("Share of original broad administration-only cell, %")
    ax.set_title("Broad-only exposure resolves into distinct provenance cells")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.xaxis.label.set_gid(f"labels__{panel}_xlabel")
    separator = ax.axhline(5.45, color=GRID, linewidth=1.0)
    set_gid(separator, f"annotations__{panel}_group_separator")
    panel_tag(ax, panel)


def draw_effect_drift(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    style_axes(ax, "x")
    static = frames["upgrade_static"].query(
        "model_variant == 'published_style_minimal'"
    ).copy()
    concordant = frames["upgrade_concordant"].copy()
    specs = [
        ("A1 original | strict", "A1", "original_strict"),
        ("A1 original | broad", "A1", "original_broad"),
        ("A1 dose metadata | broad", "A1", "metadata_constrained_broad"),
        ("A2 original | strict", "A2", "original_strict"),
        ("A2 original | broad", "A2", "original_broad"),
        ("A2 hospital overlap | strict", "A2", "hospital_overlap_strict"),
        ("A2 hospital overlap | broad", "A2", "hospital_overlap_broad"),
    ]
    y = np.arange(len(specs))[::-1]
    for index, (label, anchor, operator) in enumerate(specs):
        subset = static[
            static["anchor_id"].eq(anchor)
            & static["operator"].eq(operator)
        ]
        order = subset[subset["exposure_source"].eq("order")].iloc[0]
        admin = subset[subset["exposure_source"].eq("administration")].iloc[0]
        common = concordant[
            concordant["anchor_id"].eq(anchor)
            & concordant["operator"].eq(operator)
        ].iloc[0]
        admin_label = "Strict administration" if "strict" in operator else "Broad administration"
        admin_color = TEAL if "strict" in operator else ORANGE
        series = [
            (order, "Order", NAVY, "s", -0.16),
            (admin, admin_label, admin_color, "o", 0.0),
            (common, "Concordant subset", GOLD, "D", 0.16),
        ]
        connector = ax.plot(
            [min(float(item[0]["effect"]) for item in series), max(float(item[0]["effect"]) for item in series)],
            [y[index], y[index]],
            color=GRID,
            linewidth=1.5,
            zorder=1,
        )[0]
        set_gid(connector, f"data__{panel}_effect_connector_{index}")
        for source_index, (row, source_label, color, marker, offset) in enumerate(series):
            line = ax.plot(
                [float(row["ci_low"]), float(row["ci_high"])],
                [y[index] + offset, y[index] + offset],
                color=color,
                linewidth=1.4,
                zorder=2,
            )[0]
            set_gid(line, f"data__{panel}_effect_ci_{index}_{source_index}")
            point = ax.scatter(
                float(row["effect"]),
                y[index] + offset,
                s=38,
                marker=marker,
                color=color,
                edgecolor=WHITE,
                linewidth=0.6,
                label=(
                    source_label
                    if (
                        (source_label in {"Order", "Strict administration", "Concordant subset"} and index == 0)
                        or (source_label == "Broad administration" and index == 1)
                    )
                    else None
                ),
                zorder=3,
            )
            set_gid(point, f"data__{panel}_effect_point_{index}_{source_index}")
    null = ax.axvline(1, color=SLATE, linewidth=1, linestyle="--")
    set_gid(null, f"annotations__{panel}_null_line")
    ax.set_xscale("log")
    ax.set_xlim(0.78, 2.55)
    ax.set_xticks([0.8, 1.0, 1.25, 1.5, 2.0, 2.5])
    ax.get_xaxis().set_major_formatter(mpl.ticker.ScalarFormatter())
    ax.set_yticks(y, [item[0] for item in specs])
    ax.set_xlabel("Association estimate (OR for A1; HR for A2)")
    ax.set_title("Discordant cells, not source labels, move estimates")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.xaxis.label.set_gid(f"labels__{panel}_xlabel")
    legend = ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.19),
        ncol=2,
        frameon=False,
    )
    legend.set_gid(f"legend__{panel}_effect_source")
    panel_tag(ax, panel)


def draw_workflow_forest(ax: plt.Axes, panel: str, frames) -> None:
    """Complete 6 classes x 5 correlates x 2 semantic maps forest."""
    ax.set_gid(f"panel_{panel}")
    style_axes(ax, "x")
    data = frames["class_correlates"].copy()
    classes = [
        "stress_ulcer_prophylaxis",
        "vte_prophylaxis",
        "intra_abdominal_antibiotics",
        "electrolyte_replacement",
        "prokinetic",
        "insulin",
    ]
    terms = [
        "oasis_z",
        "shiftnight_1900_0659",
        "invasive_ventilation_active",
        "vasopressor_active",
        "rrt_active",
    ]
    term_labels = {
        "oasis_z": "OASIS per SD",
        "shiftnight_1900_0659": "Night vs day",
        "invasive_ventilation_active": "Invasive ventilation",
        "vasopressor_active": "Vasopressor support",
        "rrt_active": "RRT",
    }
    class_short = {
        "stress_ulcer_prophylaxis": "Stress-ulcer prophylaxis",
        "vte_prophylaxis": "VTE prophylaxis",
        "intra_abdominal_antibiotics": "Intra-abdominal antibiotics",
        "electrolyte_replacement": "Electrolyte replacement",
        "prokinetic": "Prokinetics",
        "insulin": "Insulin",
    }
    indexed = data.set_index(["event_mapping", "drug_class", "term"])
    combinations = [(drug_class, term) for drug_class in classes for term in terms]
    y = np.arange(len(combinations))[::-1]
    mappings = [
        ("frozen_primary", "Primary semantics", NAVY, "o", -0.12),
        ("audit_semantic_sensitivity", "Semantic audit", ORANGE, "D", 0.12),
    ]
    for row_index, (drug_class, term) in enumerate(combinations):
        for mapping_index, (mapping, label, color, marker, offset) in enumerate(mappings):
            row = indexed.loc[(mapping, drug_class, term)]
            line = ax.plot(
                [float(row["ci_low"]), float(row["ci_high"])],
                [y[row_index] + offset, y[row_index] + offset],
                color=color,
                linewidth=1.0,
                zorder=2,
            )[0]
            set_gid(line, f"data__{panel}_workflow_ci_{row_index}_{mapping_index}")
            point = ax.scatter(
                float(row["adjusted_or"]),
                y[row_index] + offset,
                s=26,
                marker=marker,
                color=color,
                edgecolor=WHITE,
                linewidth=0.5,
                label=label if row_index == 0 else None,
                zorder=3,
            )
            set_gid(point, f"data__{panel}_workflow_point_{row_index}_{mapping_index}")
    null = ax.axvline(1, color=SLATE, linewidth=1, linestyle="--")
    set_gid(null, f"annotations__{panel}_null_line")
    for separator_index in range(1, len(classes)):
        separator_y = len(combinations) - separator_index * len(terms) - 0.5
        separator = ax.axhline(separator_y, color=GRID, linewidth=0.7)
        set_gid(separator, f"annotations__{panel}_class_separator_{separator_index}")
    ax.set_xscale("log")
    ax.set_xlim(0.33, 1.65)
    ax.set_xticks([0.4, 0.6, 0.8, 1.0, 1.2, 1.5])
    ax.get_xaxis().set_major_formatter(mpl.ticker.ScalarFormatter())
    ax.set_yticks(
        y,
        [f"{class_short[drug_class]}  |  {term_labels[term]}" for drug_class, term in combinations],
    )
    ax.tick_params(axis="y", labelsize=7.0)
    ax.set_xlabel("Adjusted odds ratio for not-given documentation (95% CI)")
    ax.set_title("Complete prespecified workflow audit: 60 estimates\nNo significance-based selection")
    ax.title.set_gid(f"labels__{panel}_title")
    ax.xaxis.label.set_gid(f"labels__{panel}_xlabel")
    legend = ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.055), ncol=2, frameon=False)
    legend.set_gid(f"legend__{panel}_semantic_mapping")
    panel_tag(ax, panel)


def draw_participant_flow(ax: plt.Axes, panel: str, frames) -> None:
    ax.set_gid(f"panel_{panel}")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    flow = frames["participant_flow"]
    lookup = {
        (row.cohort, row.step): int(row.rows_n)
        for row in flow.itertuples()
    }

    nodes = [
        (0.50, 0.91, 0.34, "Raw ICU stays", 94_458, LIGHT_GREY, SLATE),
        (0.50, 0.76, 0.38, "Valid adult ICU intervals", 94_444, LIGHT_BLUE, NAVY),
        (0.50, 0.61, 0.38, "Post-deployment adult stays", 37_222, LIGHT_TEAL, TEAL),
        (0.25, 0.40, 0.34, "A1: one ICU stay + outcome", 20_248, LIGHT_BLUE, NAVY),
        (0.75, 0.47, 0.34, "A2: adult first ICU stay", 25_410, "#F3EAC9", "#876A13"),
        (0.75, 0.31, 0.34, "Operational ICD-sepsis", 4_321, "#F3EAC9", "#876A13"),
        (0.75, 0.15, 0.34, "A2 final after exclusions", 2_813, LIGHT_ORANGE, ORANGE),
    ]
    for index, (x, y, width, label, count, fill, edge) in enumerate(nodes):
        patch = FancyBboxPatch(
            (x - width / 2, y - 0.055), width, 0.11,
            boxstyle="round,pad=0.01,rounding_size=0.012",
            facecolor=fill, edgecolor=edge, linewidth=1.2,
        )
        ax.add_patch(patch)
        set_gid(patch, f"data__{panel}_flow_node_{index}")
        add_text(
            ax, x, y, f"{label}\n{count:,}", panel, f"flow_label_{index}",
            fontsize=9, fontweight="bold", ha="center", va="center",
        )
    arrows = [
        ((0.50, 0.85), (0.50, 0.82)),
        ((0.50, 0.70), (0.50, 0.67)),
        ((0.45, 0.56), (0.28, 0.47)),
        ((0.55, 0.56), (0.72, 0.54)),
        ((0.75, 0.41), (0.75, 0.37)),
        ((0.75, 0.25), (0.75, 0.21)),
    ]
    for index, (start, end) in enumerate(arrows):
        arrow = FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=12,
            linewidth=1.1, color=SLATE,
        )
        ax.add_patch(arrow)
        set_gid(arrow, f"data__{panel}_flow_arrow_{index}")
    add_text(
        ax, 0.25, 0.28, "2,530 in-hospital deaths", panel,
        "a1_outcome", category="annotations", fontsize=8.5, color=SLATE,
        ha="center", va="center",
    )
    add_text(
        ax, 0.75, 0.055,
        "1,169 deaths by 90 days  |  2,544 landmark eligible",
        panel, "a2_outcome", category="annotations", fontsize=8.3,
        color=SLATE, ha="center", va="center",
    )
    add_text(
        ax, 0.02, 0.99, "Participant flow", panel, "flow_title",
        fontsize=14, fontweight="bold", ha="left", va="top",
    )
    panel_tag(ax, panel)


def deduplicate_clip_paths(root: etree._Element) -> None:
    clips = root.xpath(".//svg:clipPath", namespaces=NS)
    seen: dict[bytes, str] = {}
    replacements: dict[str, str] = {}
    for clip in clips:
        payload = b"".join(
            etree.tostring(child, with_tail=False) for child in clip
        )
        clip_id = clip.get("id")
        if payload in seen and clip_id:
            replacements[clip_id] = seen[payload]
            clip.getparent().remove(clip)
        elif clip_id:
            seen[payload] = clip_id
    if replacements:
        for element in root.iter():
            for attribute, value in list(element.attrib.items()):
                for old, new in replacements.items():
                    value = value.replace(f"#{old}", f"#{new}")
                element.set(attribute, value)


def postprocess_svg(path: Path, expected_panels: list[str]) -> None:
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()

    for rect in root.xpath(
        ".//svg:rect[not(ancestor::svg:clipPath)]", namespaces=NS
    ):
        style = rect.get("style", "").replace(" ", "").lower()
        if "fill-opacity:0" in style or "opacity:0" in style:
            rect.getparent().remove(rect)

    for panel_name in expected_panels:
        matches = root.xpath(
            f".//svg:g[@id='panel_{panel_name}']", namespaces=NS
        )
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected one panel_{panel_name} in {path}, found {len(matches)}"
            )
        panel = matches[0]
        children = list(panel)
        for child in children:
            panel.remove(child)

        groups = {}
        for category in ("axis", "data", "labels", "legend", "annotations"):
            group = etree.Element(f"{{{SVG_NS}}}g")
            group.set("id", f"panel_{panel_name}_{category}")
            desc = etree.SubElement(group, f"{{{SVG_NS}}}desc")
            desc.text = f"{category} objects for panel {panel_name}"
            groups[category] = group
            panel.append(group)

        for child in children:
            child_id = child.get("id", "")
            if child_id.startswith("labels__"):
                category = "labels"
            elif child_id.startswith("legend__") or child_id.startswith(
                "legend_"
            ):
                category = "legend"
            elif child_id.startswith("annotations__"):
                category = "annotations"
            elif child_id.startswith("data__"):
                category = "data"
            elif child_id.startswith("matplotlib.axis") or child_id.startswith(
                "patch_"
            ):
                category = "axis"
            else:
                category = "data"
            groups[category].append(child)

        parent = panel.getparent()
        if parent is not root:
            parent.remove(panel)
            root.append(panel)

    for figure_group in root.xpath(
        ".//svg:g[starts-with(@id, 'figure_')]", namespaces=NS
    ):
        if len(figure_group) == 0:
            figure_group.getparent().remove(figure_group)

    deduplicate_clip_paths(root)
    tree.write(
        str(path),
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=False,
    )


@dataclass
class FigureSpec:
    stem: str
    panels: list[tuple[str, Callable]]
    figsize: tuple[float, float]
    width_ratios: list[float] | None = None
    height_ratios: list[float] | None = None


def save_matplotlib_figure(
    fig: plt.Figure,
    stem: str,
    directory: Path,
    expected_panels: list[str],
    raster_exports: bool,
) -> list[Path]:
    svg_path = directory / f"{stem}.svg"
    pdf_path = directory / f"{stem}.pdf"
    fig.savefig(svg_path, format="svg", bbox_inches=None)
    fig.savefig(pdf_path, format="pdf", bbox_inches=None)
    postprocess_svg(svg_path, expected_panels)
    outputs = [svg_path, pdf_path]
    if raster_exports:
        preview_path = directory / f"{stem}_preview.png"
        tiff_path = directory / f"{stem}.tiff"
        fig.savefig(
            preview_path,
            format="png",
            dpi=180,
            facecolor=WHITE,
            bbox_inches=None,
        )
        fig.savefig(
            tiff_path,
            format="tiff",
            dpi=600,
            facecolor=WHITE,
            bbox_inches=None,
            pil_kwargs={"compression": "tiff_lzw"},
        )
        outputs.extend([preview_path, tiff_path])
    plt.close(fig)
    return outputs


def make_assembled(spec: FigureSpec, frames) -> list[Path]:
    panel_count = len(spec.panels)
    if panel_count == 1:
        fig, ax = plt.subplots(figsize=spec.figsize)
        axes = [ax]
    else:
        fig, axes_array = plt.subplots(
            1,
            panel_count,
            figsize=spec.figsize,
            gridspec_kw={
                "width_ratios": spec.width_ratios
                or [1] * panel_count,
                "wspace": 0.42,
            },
        )
        axes = list(np.atleast_1d(axes_array))
    fig.patch.set_visible(False)
    for ax, (panel, draw) in zip(axes, spec.panels):
        draw(ax, panel, frames)
    if spec.stem == "FigureS5_complete_workflow_forest":
        fig.subplots_adjust(left=0.34, right=0.98, top=0.96, bottom=0.07)
    elif spec.stem == "Figure4_reclassification_and_drift":
        fig.subplots_adjust(left=0.075, right=0.985, top=0.88, bottom=0.20)
    else:
        right_margin = 0.96 if spec.stem == "Figure3_semantics_and_workflow" else 0.98
        fig.subplots_adjust(
            left=0.09 if panel_count > 1 else 0.02,
            right=right_margin,
            top=0.88 if panel_count > 1 else 0.98,
            bottom=0.19 if panel_count > 1 else 0.03,
        )
    return save_matplotlib_figure(
        fig,
        spec.stem,
        FIGURES,
        [panel for panel, _ in spec.panels],
        raster_exports=True,
    )


def make_separate_panels(spec: FigureSpec, frames) -> list[Path]:
    outputs: list[Path] = []
    for panel, draw in spec.panels:
        if spec.stem == "FigureS5_complete_workflow_forest":
            width, height = 10.0, 13.2
        elif spec.stem == "Figure4_reclassification_and_drift":
            width, height = 7.0, 5.6
        else:
            width = 6.4
            height = 4.9 if spec.stem != "Figure1_provenance_audit" else 5.2
        fig, ax = plt.subplots(figsize=(width, height))
        fig.patch.set_visible(False)
        draw(ax, panel, frames)
        if spec.stem == "FigureS5_complete_workflow_forest":
            fig.subplots_adjust(left=0.34, right=0.98, top=0.95, bottom=0.07)
        else:
            fig.subplots_adjust(
                left=0.20 if spec.stem != "Figure1_provenance_audit" else 0.03,
                right=0.97,
                top=0.86 if spec.stem != "Figure1_provenance_audit" else 0.98,
                bottom=0.21 if spec.stem != "Figure1_provenance_audit" else 0.04,
            )
        outputs.extend(
            save_matplotlib_figure(
                fig,
                f"{spec.stem}_panel_{panel}",
                PANELS,
                [panel],
                raster_exports=False,
            )
        )
    return outputs


def main() -> None:
    started = time.time()
    configure_style()
    log("START load source-corrected v1.1 tables")
    frames = load_sources()
    write_panel_data(frames)
    log("PASS figure data written")

    specs = [
        FigureSpec(
            stem="Figure1_provenance_audit",
            panels=[("A", draw_framework)],
            figsize=(12.0, 6.4),
        ),
        FigureSpec(
            stem="Figure2_observability_and_delivery",
            panels=[("A", draw_observability), ("B", draw_conversion)],
            figsize=(12.0, 6.2),
            width_ratios=[0.92, 1.20],
        ),
        FigureSpec(
            stem="Figure3_semantics_and_workflow",
            panels=[("A", draw_semantics), ("B", draw_literature_reporting)],
            figsize=(12.0, 6.2),
            width_ratios=[1.0, 1.25],
        ),
        FigureSpec(
            stem="Figure4_reclassification_and_drift",
            panels=[("A", draw_reclassification), ("B", draw_provenance), ("C", draw_effect_drift)],
            figsize=(16.0, 6.5),
            width_ratios=[1.05, 1.20, 1.35],
        ),
        FigureSpec(
            stem="FigureS4_participant_flow",
            panels=[("A", draw_participant_flow)],
            figsize=(9.6, 6.2),
        ),
        FigureSpec(
            stem="FigureS5_complete_workflow_forest",
            panels=[("A", draw_workflow_forest)],
            figsize=(10.0, 13.2),
        ),
    ]

    outputs: list[Path] = []
    for spec in specs:
        log(f"START {spec.stem}")
        outputs.extend(make_assembled(spec, frames))
        outputs.extend(make_separate_panels(spec, frames))
        log(f"DONE {spec.stem}")

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "script": str(Path(__file__).resolve()),
        "elapsed_seconds": round(time.time() - started, 3),
        "source_root": [
            str(SOURCE_TABLES), str(PRE_TABLES), str(UPGRADE_TABLES),
            str(RESIDUAL_TABLES),
        ],
        "source_version": "jamia_observability_v1_1_plus_pre_submission_v1_0_plus_prereview_upgrade_v1_0",
        "figures_n": len(specs),
        "assembled_svg_n": len(
            [path for path in outputs if path.parent == FIGURES and path.suffix == ".svg"]
        ),
        "assembled_pdf_n": len(
            [path for path in outputs if path.parent == FIGURES and path.suffix == ".pdf"]
        ),
        "panel_svg_n": len(
            [path for path in outputs if path.parent == PANELS and path.suffix == ".svg"]
        ),
        "panel_pdf_n": len(
            [path for path in outputs if path.parent == PANELS and path.suffix == ".pdf"]
        ),
        "rasterized_vector_objects": False,
        "svg_fonttype": mpl.rcParams["svg.fonttype"],
        "pdf_fonttype": mpl.rcParams["pdf.fonttype"],
        "outputs": [str(path) for path in outputs],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log(
        "DONE JAMIA figures "
        f"outputs={len(outputs)} elapsed_seconds={manifest['elapsed_seconds']}"
    )


if __name__ == "__main__":
    main()
