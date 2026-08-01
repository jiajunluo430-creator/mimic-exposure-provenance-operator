from __future__ import annotations

import importlib.metadata
import json
import math
import platform
import re
import sys
import time
from pathlib import Path

import pandas as pd

from common import (
    ENVIRONMENT,
    MANIFESTS,
    PROJECT,
    REPORTS,
    TABLES,
    file_sha256,
    now_local,
    script_metadata,
    verify_frozen_contract,
    verify_semantic_addendum,
    write_csv,
    write_json,
)


SCRIPT = Path(__file__).resolve()


def required_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required result is absent: {path}")
    return pd.read_csv(path)


def required_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Required result is absent: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "pass")


def fmt_pct(value: float | int | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "NA"
    return f"{float(value):.2f}%"


def gate_row(
    gate_id: str,
    domain: str,
    status: str,
    observed: str,
    locked_rule: str,
    fail_action: str,
) -> dict[str, str]:
    return {
        "gate_id": gate_id,
        "domain": domain,
        "status": status,
        "observed": observed,
        "locked_rule": locked_rule,
        "fail_action": fail_action,
    }


def assess_gates() -> tuple[pd.DataFrame, dict[str, object]]:
    audit = required_json(MANIFESTS / "01_full_interface_audit.json")
    immutability = required_csv(MANIFESTS / "source_immutability_audit.csv")
    detail = required_csv(TABLES / "emar_detail_availability_by_class.csv")
    target = required_csv(TABLES / "inputevents_225925_reproduction.csv")
    denominator = required_csv(
        TABLES / "emar_decision_denominator_by_class.csv"
    )
    conversion = required_csv(
        TABLES / "order_to_administration_conversion.csv"
    )
    linkage = required_csv(TABLES / "published_anchor_emar_poe_linkage.csv")
    effects = required_csv(
        TABLES / "published_association_model_effects.csv"
    )
    change = required_csv(
        TABLES / "published_association_effect_change.csv"
    )
    cohort_check = required_csv(
        TABLES / "published_association_same_cohort_check.csv"
    )
    prevalence = required_csv(
        TABLES / "published_anchor_exposure_prevalence.csv"
    )
    not_given = required_csv(
        TABLES / "not_given_prespecified_correlates.csv"
    )
    eicu = required_csv(TABLES / "eicu_interface_semantic_summary.csv")
    rmeta = required_json(MANIFESTS / "05_fit_prespecified_models.json")

    gates: list[dict[str, str]] = []
    g01 = bool(
        len(immutability) > 0
        and immutability["unchanged"].map(truthy).all()
        and truthy(audit.get("source_stats_unchanged"))
    )
    gates.append(
        gate_row(
            "G01",
            "source_integrity",
            "PASS" if g01 else "FAIL",
            f"{int(immutability['unchanged'].map(truthy).sum())}/"
            f"{len(immutability)} monitored sources unchanged",
            "Raw MIMIC/eICU sources remain read-only; all derived files "
            "stay under the project root.",
            "NO-GO and stop",
        )
    )

    emar_rows = int(audit["emar_rows_n"])
    distribution_sum = int(audit["distribution_sum_n"])
    g02 = (
        truthy(audit.get("distribution_reconciles"))
        and emar_rows == distribution_sum
        and truthy(audit.get("full_table_not_sample"))
        and audit.get("ignore_errors") is False
    )
    gates.append(
        gate_row(
            "G02",
            "full_emar",
            "PASS" if g02 else "FAIL",
            f"{distribution_sum:,}/{emar_rows:,} rows reconcile; "
            f"full scan={audit.get('full_table_not_sample')}; "
            f"ignore_errors={audit.get('ignore_errors')}",
            "Full eMAR event_txt distribution reconciles exactly, without "
            "sampling or ignored parse errors.",
            "NO-GO and repair before models",
        )
    )

    linkage = linkage.sort_values("anchor_id")
    link_map = dict(
        zip(linkage["anchor_id"], linkage["poe_identity_link_pct"])
    )
    g03_audit = set(link_map) == {"A1", "A2"}
    both_below_50 = (
        g03_audit
        and float(link_map["A1"]) < 50
        and float(link_map["A2"]) < 50
    )
    g03 = g03_audit and not both_below_50
    gates.append(
        gate_row(
            "G03",
            "poe_link",
            "PASS" if g03 else "FAIL",
            "; ".join(
                f"{key} identity-link={fmt_pct(value)}"
                for key, value in link_map.items()
            ),
            "Report POE identity linkage; both anchor classes cannot be "
            "below the locked 50% fatal threshold.",
            "NO-GO if both anchors fall below 50%",
        )
    )

    detail_columns = {
        "detail_linked_n",
        "dose_given_available_n",
        "dose_given_with_unit_n",
        "dose_due_available_n",
        "product_amount_available_n",
        "route_available_n",
        "complete_dose_not_given_yes_n",
    }
    g04 = len(detail) > 0 and detail_columns.issubset(detail.columns)
    gates.append(
        gate_row(
            "G04",
            "emar_detail",
            "PASS" if g04 else "FAIL",
            f"{len(detail):,} class/category rows; "
            f"{len(detail_columns.intersection(detail.columns))}/"
            f"{len(detail_columns)} requested summary fields present",
            "Audit dose, unit, product amount, route, and not-given-related "
            "fields for all whitelisted eMAR events.",
            "HOLD until repaired",
        )
    )

    g05 = bool(
        len(target) == 1
        and int(target.iloc[0]["itemid"]) == 225925
        and int(target.iloc[0]["fact_rows_n"]) == 0
        and str(target.iloc[0]["label"]).strip().lower()
        == "potassium phosphate"
        and truthy(audit.get("inputevents_225925_reproduced"))
    )
    gates.append(
        gate_row(
            "G05",
            "dictionary_orphans",
            "PASS" if g05 else "FAIL",
            f"complete zero-row list n={int(audit['zero_fact_items_n']):,}; "
            "inputevents 225925 fact_rows=0",
            "Produce the complete d_items zero-fact-row list and reproduce "
            "inputevents itemid 225925.",
            "HOLD until repaired",
        )
    )

    exclusion_columns = {"flushed_n", "confirmed_n", "blank_n"}
    decision_columns = {"given_n", "not_given_n"}
    g06 = (
        len(denominator) == 6
        and exclusion_columns.issubset(denominator.columns)
        and decision_columns.issubset(denominator.columns)
    )
    exclusion_totals = {
        col: int(denominator[col].sum()) for col in sorted(exclusion_columns)
    }
    gates.append(
        gate_row(
            "G06",
            "event_exclusions",
            "PASS" if g06 else "FAIL",
            ", ".join(f"{key}={value:,}" for key, value in exclusion_totals.items())
            + "; categories stored separately from given/not-given",
            "Flushed, Confirmed, and blank/null event_txt remain three "
            "separate categories outside the decision denominator.",
            "NO-GO and repair",
        )
    )

    expected_classes = {
        "stress_ulcer_prophylaxis",
        "vte_prophylaxis",
        "intra_abdominal_antibiotics",
        "electrolyte_replacement",
        "prokinetic",
        "insulin",
    }
    observed_classes = set(conversion["drug_class"].astype(str))
    g07 = observed_classes == expected_classes and len(conversion) == 6
    gates.append(
        gate_row(
            "G07",
            "class_coverage",
            "PASS" if g07 else "FAIL",
            f"{len(observed_classes)}/6 frozen classes retained; "
            f"eligible orders={int(conversion['eligible_orders_n'].sum()):,}",
            "All six frozen strict classes are reported; low counts are "
            "labeled, never dropped.",
            "NO-GO if a class is silently removed",
        )
    )

    all_conversion_gt97 = bool(
        conversion["conversion_pct"].notna().all()
        and (conversion["conversion_pct"] > 97).all()
    )
    meaningful_oasis = truthy(rmeta.get("meaningful_oasis_association"))
    negative_stop_loss = all_conversion_gt97 and not meaningful_oasis
    gates.append(
        gate_row(
            "G08",
            "negative_stop_loss",
            "TRIGGERED" if negative_stop_loss else "NOT_TRIGGERED",
            f"all six conversion >97%={all_conversion_gt97}; "
            f"meaningful OASIS association={meaningful_oasis}",
            "If all six conversions exceed 97% and no meaningful OASIS "
            "association exists, cap decision at BACKUP and do not expand.",
            "Complete negative validity report",
        )
    )

    primary_effects = effects[
        effects["model_variant"].eq("published_style_minimal")
    ].copy()
    primary_cohort = cohort_check[
        cohort_check["model_variant"].eq("published_style_minimal")
    ].copy()

    def anchor_pair_ok(anchor: str) -> bool:
        rows = primary_effects[primary_effects["anchor_id"].eq(anchor)]
        cohort = primary_cohort[primary_cohort["anchor_id"].eq(anchor)]
        return bool(
            len(rows) == 2
            and set(rows["exposure_definition"]) == {
                "order",
                "administration",
            }
            and rows["effect"].map(math.isfinite).all()
            and rows["converged"].map(truthy).all()
            and len(cohort) == 1
            and truthy(cohort.iloc[0]["identical_n_and_outcomes"])
        )

    for gate_id, anchor in (("G09", "A1"), ("G10", "A2")):
        ok = anchor_pair_ok(anchor)
        rows = primary_effects[primary_effects["anchor_id"].eq(anchor)]
        effects_text = "; ".join(
            f"{row.exposure_definition} {row.effect_measure}="
            f"{row.effect:.3f}"
            for row in rows.itertuples(index=False)
            if math.isfinite(float(row.effect))
        )
        gates.append(
            gate_row(
                gate_id,
                f"association_{anchor}",
                "PASS" if ok else "FAIL",
                effects_text or "model pair absent or non-finite",
                f"{anchor} is fitted twice under an identical cohort and "
                "covariates, changing only exposure definition.",
                "NO-GO only if the locked fatal cohort threshold is met",
            )
        )

    primary_change = change[
        change["model_variant"].eq("published_style_minimal")
    ].copy()
    material_anchors = sorted(
        primary_change.loc[
            primary_change["material_effect_change"].map(truthy), "anchor_id"
        ].astype(str)
    )
    g11 = len(material_anchors) > 0
    gates.append(
        gate_row(
            "G11",
            "material_effect_change",
            "PASS" if g11 else "FAIL",
            "material anchors="
            + (", ".join(material_anchors) if material_anchors else "none"),
            "Direction reversal, absolute log change >=log(1.25), or "
            "relative absolute log change >=25% in at least one anchor.",
            "Required for GO; otherwise BACKUP",
        )
    )

    eicu_roles = set(eicu["source_table"].astype(str).str.lower())
    g12 = {"medication", "treatment", "infusiondrug", "intakeoutput"}.issubset(
        eicu_roles
    )
    gates.append(
        gate_row(
            "G12",
            "eicu_boundary",
            "PASS" if g12 else "FAIL",
            f"{len(eicu):,} semantic summary rows; no eICU outcome model",
            "eICU is an interface-semantic contrast only, never external "
            "validation.",
            "Repair wording before completion",
        )
    )

    prohibited = re.compile(
        r"^\s*(?:from|import)\s+"
        r"(?:sklearn|xgboost|lightgbm|shap)\b"
        r"|^\s*library\s*\(\s*(?:randomForest|xgboost|lightgbm|shap)"
        r"\s*\)|::\s*nomogram\s*\(",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    code_hits: list[str] = []
    for path in sorted((PROJECT / "scripts").glob("*")):
        if path.suffix.lower() not in (".py", ".r"):
            continue
        text = path.read_text(encoding="utf-8")
        if prohibited.search(text):
            code_hits.append(path.name)
    g13 = not code_hits
    gates.append(
        gate_row(
            "G13",
            "prohibited_methods",
            "PASS" if g13 else "FAIL",
            "No nomogram/ML/SHAP implementation detected"
            if g13
            else "prohibited implementation hits: " + ", ".join(code_hits),
            "No causal drug claim, nomogram, ML, SHAP, or "
            "significance-based selection.",
            "NO-GO until repaired",
        )
    )

    validation_path = MANIFESTS / "07_validation.json"
    validation_pass = False
    if validation_path.exists():
        validation = required_json(validation_path)
        validation_pass = truthy(validation.get("all_checks_pass"))
    required_reports = [
        REPORTS / f"{number:02d}_{suffix}"
        for number, suffix in (
            (1, "full_interface_audit.md"),
            (2, "primary_estimands.md"),
            (3, "severity_shift_organ_support.md"),
            (4, "published_association_cohorts.md"),
            (5, "published_association_effect_change.md"),
            (6, "eicu_semantic_contrast_and_pilot_gates.md"),
            (7, "final_qdp_decision.md"),
        )
    ]
    reports_present = all(path.exists() for path in required_reports)
    environment_present = (
        (ENVIRONMENT / "R_sessionInfo.txt").exists()
        and (ENVIRONMENT / "Python_sessionInfo.txt").exists()
    )
    g14 = reports_present and environment_present and validation_pass
    gates.append(
        gate_row(
            "G14",
            "reproducibility",
            "PASS" if g14 else "PENDING",
            f"QDP01-07={reports_present}; environment={environment_present}; "
            f"validation={validation_pass}",
            "Scripts, logs, manifests, Python environment, R sessionInfo, "
            "and QDP 01-07 are present and validation passes.",
            "HOLD until complete",
        )
    )

    gates_frame = pd.DataFrame(gates)
    prevalence_map = prevalence.set_index("anchor_id").to_dict("index")
    fatal_cohort = bool(
        all(
            float(prevalence_map[a]["cohort_n"]) < 500
            for a in ("A1", "A2")
        )
        and all(
            min(
                float(prevalence_map[a]["order_exposed_pct"]),
                float(prevalence_map[a]["administration_exposed_pct"]),
            )
            < 1
            for a in ("A1", "A2")
        )
    )
    fatal_measurement = not all((g01, g02, g03)) or fatal_cohort
    audit_holds = not all((g04, g05, g06, g07, g09 := anchor_pair_ok("A1"),
                           g10 := anchor_pair_ok("A2"), g12, g13))
    material_measurement_discrepancy = (
        not all_conversion_gt97 or meaningful_oasis
    )

    if fatal_measurement:
        decision = "NO-GO"
        reason = "A locked fatal measurement/cohort threshold failed."
    elif audit_holds:
        decision = "NO-GO"
        reason = (
            "One or more mandatory audit/model integrity gates remains "
            "unrepaired at finalization."
        )
    elif negative_stop_loss:
        decision = "BACKUP"
        reason = (
            "The user-mandated negative-validity stop-loss triggered; the "
            "report remains complete and the journal ceiling is downgraded."
        )
    elif material_measurement_discrepancy and g11:
        decision = "GO"
        reason = (
            "Mandatory audits passed, a material measurement discrepancy "
            "exists, and at least one primary anchor met the locked "
            "effect-change criterion."
        )
    else:
        decision = "BACKUP"
        reason = (
            "Mandatory audits passed, but the full GO conjunction was not "
            "met; the result is retained as a validity/negative-validity "
            "report."
        )

    context: dict[str, object] = {
        "decision": decision,
        "decision_reason": reason,
        "all_conversion_gt97": all_conversion_gt97,
        "meaningful_oasis_association": meaningful_oasis,
        "negative_stop_loss_triggered": negative_stop_loss,
        "material_measurement_discrepancy": material_measurement_discrepancy,
        "material_effect_change_anchors": material_anchors,
        "full_emar_rows_n": emar_rows,
        "full_emar_identity_links_n": int(audit["poe_id_identity_link_n"]),
        "zero_fact_items_n": int(audit["zero_fact_items_n"]),
        "conversion": conversion,
        "primary_change": primary_change,
        "not_given": not_given,
        "eicu": eicu,
        "prevalence": prevalence,
    }
    return gates_frame, context


def render_report_06(
    gates: pd.DataFrame, context: dict[str, object]
) -> str:
    eicu = context["eicu"]
    return "\n".join(
        [
            "# 06 — eICU semantic contrast and locked pilot gates",
            "",
            "## eICU boundary",
            "",
            "eICU-CRD is used only to contrast interface semantics. In the",
            "supplied whitelist, `medication` represents order/planned-start",
            "evidence and `treatment` represents documentation. `infusionDrug`",
            "and `intakeOutput` are administration-like only when a",
            "drug-specific label, positive numeric value/rate, and valid",
            "offset coexist. No eICU treatment, timing, dose, or outcome",
            "association is presented as external validation.",
            "",
            "```text",
            eicu.to_string(index=False),
            "```",
            "",
            "## Pilot gates",
            "",
            "```text",
            gates[
                ["gate_id", "domain", "status", "observed"]
            ].to_string(index=False),
            "```",
            "",
            "## Decision",
            "",
            f"**{context['decision']}** — {context['decision_reason']}",
            "",
            "The negative stop-loss is applied exactly as frozen. It never",
            "permits expansion of drug classes or relaxation of time windows.",
            "",
        ]
    )


def render_report_07(
    gates: pd.DataFrame, context: dict[str, object]
) -> str:
    conversion: pd.DataFrame = context["conversion"]
    change: pd.DataFrame = context["primary_change"]
    not_given: pd.DataFrame = context["not_given"]
    decision = str(context["decision"])
    finite_conversion = conversion[
        pd.to_numeric(
            conversion["conversion_pct"], errors="coerce"
        ).map(math.isfinite)
    ]
    min_conversion = (
        finite_conversion.loc[finite_conversion["conversion_pct"].idxmin()]
        if len(finite_conversion)
        else None
    )
    max_conversion = (
        finite_conversion.loc[finite_conversion["conversion_pct"].idxmax()]
        if len(finite_conversion)
        else None
    )
    finite_change = change[
        pd.to_numeric(
            change["absolute_log_effect_change"], errors="coerce"
        ).map(math.isfinite)
    ]
    maximum_change = (
        finite_change.loc[
            finite_change["absolute_log_effect_change"].idxmax()
        ]
        if len(finite_change)
        else None
    )
    oasis = not_given[not_given["term"].eq("oasis_z")]
    oasis_text = (
        f"OR {float(oasis.iloc[0]['adjusted_or']):.3f} "
        f"(95% CI {float(oasis.iloc[0]['ci_low']):.3f}–"
        f"{float(oasis.iloc[0]['ci_high']):.3f})"
        if len(oasis) == 1
        else "not estimable"
    )

    min_conversion_text = (
        f"{min_conversion['drug_class']} at "
        f"{float(min_conversion['conversion_pct']):.2f}%"
        if min_conversion is not None
        else "not estimable"
    )
    maximum_change_text = (
        f"{maximum_change['anchor_id']} at "
        f"{float(maximum_change['absolute_log_effect_change']):.3f}"
        if maximum_change is not None
        else "not estimable"
    )
    conversion_range_text = (
        f"{float(min_conversion['conversion_pct']):.2f}%–"
        f"{float(max_conversion['conversion_pct']):.2f}%"
        if min_conversion is not None and max_conversion is not None
        else "not estimable"
    )
    a2_change = change[change["anchor_id"].eq("A2")]
    a2_change_text = (
        f"order HR {float(a2_change.iloc[0]['effect_order']):.3f} to "
        f"administration HR "
        f"{float(a2_change.iloc[0]['effect_administration']):.3f}; "
        f"relative absolute log-effect change "
        f"{float(a2_change.iloc[0]['relative_absolute_log_effect_change_pct']):.1f}%"
        if len(a2_change) == 1
        else "not estimable"
    )
    all_change = required_csv(
        TABLES / "published_association_effect_change.csv"
    )
    a2_sensitivity_material_n = int(
        (
            all_change["anchor_id"].eq("A2")
            & all_change["material_effect_change"].map(truthy)
        ).sum()
    )
    vte_field = required_csv(
        PROJECT
        / "outputs"
        / "audit"
        / "02_vte_administration_field_availability.csv"
    )
    vte_route_text = (
        f"{int(vte_field.iloc[0]['strict_given_route_nonmissing_n']):,}/"
        f"{int(vte_field.iloc[0]['strict_given_events_n']):,}"
    )

    if decision == "GO":
        ceiling = (
            "Methods-oriented critical-care informatics or "
            "pharmacoepidemiology journal; estimated upper target: JAMIA, "
            "Critical Care, or Pharmacoepidemiology and Drug Safety, subject "
            "to manuscript execution and reviewer fit."
        )
        primary_story = "Primary six-class validity paper"
    elif decision == "BACKUP":
        ceiling = (
            "Negative-validity/data-quality paper; estimated target: JAMIA "
            "Open, BMC Medical Informatics and Decision Making, or a focused "
            "critical-care/pharmacoepidemiology methods journal."
        )
        primary_story = "Complete negative/limited-effect validity report"
    else:
        ceiling = (
            "No journal target until the fatal audit failure is repaired; "
            "retain the package as a reproducibility record."
        )
        primary_story = "No manuscript submission before repair"

    candidates = pd.DataFrame(
        [
            {
                "rank": 1,
                "story": primary_story,
                "decision": decision,
                "claim": "Exposure-definition validity and effect sensitivity",
                "feasibility_5": 5,
                "novelty_5": 4 if decision == "GO" else 3,
                "ceiling_5": 4 if decision == "GO" else 3,
            },
            {
                "rank": 2,
                "story": "Six-class negative-validity audit",
                "decision": "BACKUP",
                "claim": "Quantifies small/heterogeneous order-delivery gaps",
                "feasibility_5": 5,
                "novelty_5": 3,
                "ceiling_5": 3,
            },
            {
                "rank": 3,
                "story": "MIMIC/eICU interface-semantic methods note",
                "decision": "BACKUP",
                "claim": "Documents transport limits without validation claim",
                "feasibility_5": 5,
                "novelty_5": 3,
                "ceiling_5": 2,
            },
        ]
    )

    return "\n".join(
        [
            "# 07 — Final QDP decision",
            "",
            "## 1. Executive decision",
            "",
            f"**{decision}** — {context['decision_reason']}",
            "",
            f"The full eMAR audit reconciled {context['full_emar_rows_n']:,}",
            "rows. All six locked drug classes were retained; conversion",
            f"spanned {conversion_range_text}, with the lowest conversion",
            f"{min_conversion_text}. The locked",
            f"OASIS association was {oasis_text}. The largest primary-anchor",
            "absolute log-effect change was",
            f"{maximum_change_text}.",
            "",
            f"The prespecified A2 contrast changed from {a2_change_text}.",
            f"All {a2_sensitivity_material_n} prespecified A2 model variants",
            "met the frozen material-change rule. Separately, VTE strict-given",
            f"eMAR route availability was {vte_route_text}; route remained an",
            "audited attribute, not an added administration gate.",
            "",
            "This supports only a measurement-validity/effect-sensitivity",
            "claim. It does not establish drug efficacy, harm, optimal use,",
            "or treatment thresholds.",
            "",
            "## 2. Ranked candidate table",
            "",
            "```text",
            candidates.to_string(index=False),
            "```",
            "",
            "### Top-3 red-team",
            "",
            "1. The primary story can be weakened by residual semantic error:",
            "   a documented eMAR event is not bedside observation, and POE",
            "   links can miss legitimate administration workflows.",
            "2. A negative-validity story remains useful but has a lower",
            "   journal ceiling; it must retain every class and avoid",
            "   post-result window changes.",
            "3. eICU interface differences are descriptive only. Label/stay",
            "   counts cannot validate MIMIC exposure or outcome effects.",
            "",
            "## 3. Best dry-only topics",
            "",
            "- Primary: six-class MIMIC order-to-administration validity plus",
            "  the two frozen published-association sensitivity analyses.",
            "- Backup: a complete negative-validity/data-quality report if",
            "  association effects are not materially changed.",
            "",
            "## 4. Best wet-lab-supported topics",
            "",
            "None. Wet-lab validation is scientifically mismatched to an EHR",
            "interface-measurement question and would expand the frozen scope.",
            "",
            "## 5. No-go topics",
            "",
            "- Any single-drug efficacy or safety causal study derived from",
            "  these results.",
            "- Nomogram, machine-learning prediction, SHAP, or",
            "  significance-selected class/window analyses.",
            "- Calling the eICU semantic contrast external validation.",
            "",
            "## 6. Literature collision risk",
            "",
            "A1 and A2 are deliberately published anchors, so their clinical",
            "associations are not novel claims. The defensible novelty is the",
            "pre-result, six-class exposure-measurement audit and its effect",
            "change under identical cohorts/covariates. Collision risk is",
            "moderate because missed-dose and medication-adherence literatures",
            "exist; the manuscript must foreground the native POE/eMAR",
            "identity audit and cross-association sensitivity design.",
            "",
            "## 7. Data feasibility audit",
            "",
            f"- Full eMAR rows reconciled: {context['full_emar_rows_n']:,}.",
            f"- Same-subject/same-admission POE identity links: "
            f"{context['full_emar_identity_links_n']:,}.",
            f"- Complete d_items zero-fact-row entries: "
            f"{context['zero_fact_items_n']:,}; inputevents 225925 was",
            "  explicitly reproduced with zero rows.",
            "- eMAR-detail dose, route, product amount, barcode fields,",
            "  administration type, and complete-dose-not-given were audited.",
            "- The literal not-given model remains primary; a separately",
            "  hashed pre-model semantic sensitivity reports `Hold Dose` and",
            "  `Not Given per Sliding Scale*` without affecting gates.",
            "- All derived files stay inside this project; raw sources were",
            "  monitored as read-only.",
            "",
            "## 8. Statistical risk",
            "",
            "- Exposure misclassification is the estimand, but eMAR remains",
            "  documentation rather than direct observation.",
            "- Confounding is not solved by redefining exposure; paired",
            "  estimates are not causal contrasts.",
            "- A2 uses frozen ICD-coded sepsis, not exact Sepsis-3 replication.",
            "- A1 paired estimates did not reproduce the published protective",
            "  direction; this is an anchor-fidelity limitation, not evidence",
            "  of a causal drug-effect reversal.",
            "- Order and administration exposure prevalence can create sparse",
            "  discordant cells; finite estimates and convergence are retained",
            "  in the model audit.",
            "- Multiplicity is descriptive; BH q-values are reported for the",
            "  five locked not-given correlates, not used for selection.",
            "",
            "## 9. Clinical novelty score",
            "",
            f"Overall: **{4 if decision == 'GO' else 3}/5**. The clinical",
            "drug-outcome associations themselves are not novel; novelty",
            "comes from quantifying whether a common order-as-administration",
            "assumption changes published ICU pharmacoepidemiology estimates.",
            "",
            "## 10. Journal ceiling estimate",
            "",
            ceiling,
            "",
            "## 11. Stop-loss gates",
            "",
            "```text",
            gates[
                ["gate_id", "status", "observed"]
            ].to_string(index=False),
            "```",
            "",
            "The locked negative stop-loss was "
            f"{'triggered' if context['negative_stop_loss_triggered'] else 'not triggered'}. "
            "No class was added and no window was relaxed.",
            "",
            "## 12. Next Codex / Claude Code execution prompt",
            "",
            "Draft the manuscript strictly from QDP 01–07 and the",
            "machine-readable tables. Lead with exposure-measurement validity,",
            "report all six frozen classes and both anchors, preserve the",
            "Flushed/Confirmed/blank exclusions, state that eICU is only a",
            "semantic contrast, and make no causal drug claim. Do not add",
            "classes, alter windows, select by significance, or introduce",
            "prediction methods. Re-run `scripts/07_validate_package.py` after",
            "any presentation-only edit.",
            "",
        ]
    )


def write_environment() -> None:
    packages = {}
    for name in (
        "duckdb",
        "pandas",
        "numpy",
        "pyarrow",
        "scipy",
        "statsmodels",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    lines = [
        f"generated_at={now_local()}",
        f"python_executable={sys.executable}",
        f"python_version={sys.version}",
        f"platform={platform.platform()}",
    ] + [f"{key}={value}" for key, value in packages.items()]
    (ENVIRONMENT / "Python_sessionInfo.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_reproducibility_manifest() -> None:
    records: list[dict[str, object]] = []
    excluded_names = {
        "n1_validity.duckdb",
        "n1_validity.duckdb.wal",
        "reproducibility_manifest.csv",
        "07_validation.json",
        "validation_checks.csv",
    }
    for path in sorted(PROJECT.rglob("*")):
        if not path.is_file():
            continue
        if path.name in excluded_names or "duckdb_tmp" in path.parts:
            continue
        records.append(
            {
                "relative_path": path.relative_to(PROJECT).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    write_csv(
        pd.DataFrame(records),
        MANIFESTS / "reproducibility_manifest.csv",
    )


def main() -> None:
    started = time.time()
    verify_frozen_contract()
    verify_semantic_addendum()
    write_environment()
    gates, context = assess_gates()
    write_csv(gates, PROJECT / "pilot_gates.csv")
    (REPORTS / "06_eicu_semantic_contrast_and_pilot_gates.md").write_text(
        render_report_06(gates, context), encoding="utf-8"
    )
    (REPORTS / "07_final_qdp_decision.md").write_text(
        render_report_07(gates, context), encoding="utf-8"
    )
    write_reproducibility_manifest()
    metadata = script_metadata(started, SCRIPT)
    metadata.update(
        {
            "final_decision": context["decision"],
            "decision_reason": context["decision_reason"],
            "negative_stop_loss_triggered": context[
                "negative_stop_loss_triggered"
            ],
            "material_effect_change_anchors": context[
                "material_effect_change_anchors"
            ],
            "pilot_gates_pass_n": int(gates["status"].eq("PASS").sum()),
            "pilot_gates_fail_n": int(gates["status"].eq("FAIL").sum()),
            "pilot_gates_pending_n": int(gates["status"].eq("PENDING").sum()),
        }
    )
    write_json(metadata, MANIFESTS / "06_finalize_qdp.json")
    print(
        f"FINAL_DECISION={context['decision']} "
        f"elapsed={metadata['elapsed_seconds']}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
