from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

import pandas as pd

from common import (
    ENVIRONMENT,
    PROJECT,
    REPORTS,
    TABLES,
    now_local,
    write_csv,
    write_json,
)


SCRIPT = Path(__file__).resolve()
EXTENSION_VERSION = (
    "v1_1"
    if "--extension-version=v1_1" in sys.argv[1:]
    else "v1_0"
)
EXTENSION = (
    PROJECT / "outputs" / "jamia_observability_v1_1"
    if EXTENSION_VERSION == "v1_1"
    else PROJECT / "outputs" / "jamia_observability"
)
EXT_TABLES = EXTENSION / "tables"
EXT_LOGS = EXTENSION / "logs"
EXT_MANIFESTS = EXTENSION / "manifests"


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "pass"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(
    rows: list[dict[str, object]],
    check_id: str,
    passed: bool,
    evidence: str,
) -> None:
    rows.append(
        {
            "check_id": check_id,
            "passed": bool(passed),
            "evidence": evidence,
        }
    )


def verify_extension_contract() -> pd.DataFrame:
    manifest_path = (
        PROJECT
        / "contracts"
        / (
            "jamia_observability_sha256_v1.1_2026-07-30.txt"
            if EXTENSION_VERSION == "v1_1"
            else "jamia_observability_sha256_2026-07-30.txt"
        )
    )
    records: list[dict[str, object]] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = re.split(r"\s+", line.strip(), maxsplit=1)
        path = (
            PROJECT / name
            if name == "analysis_decision_log.md"
            else PROJECT / "contracts" / name
        )
        actual = sha256(path)
        records.append(
            {
                "file": name,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "match": expected.lower() == actual.lower(),
            }
        )
    return pd.DataFrame(records)


def format_markdown_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["(no rows)"]
    headers = [str(column) for column in frame.columns]
    values = [
        [str(value) for value in row]
        for row in frame.itertuples(index=False, name=None)
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in values))
        for index in range(len(headers))
    ]
    lines = [
        "| "
        + " | ".join(
            headers[index].ljust(widths[index])
            for index in range(len(headers))
        )
        + " |",
        "| "
        + " | ".join("-" * widths[index] for index in range(len(headers)))
        + " |",
    ]
    lines.extend(
        "| "
        + " | ".join(
            row[index].ljust(widths[index])
            for index in range(len(headers))
        )
        + " |"
        for row in values
    )
    return lines


def main() -> None:
    started = time.time()
    checks: list[dict[str, object]] = []

    try:
        contract = verify_extension_contract()
        contract_ok = len(contract) == 3 and contract["match"].map(truthy).all()
        evidence = f"{int(contract['match'].map(truthy).sum())}/3 files match"
        write_csv(
            contract,
            EXT_MANIFESTS / "15_contract_verification.csv",
        )
    except Exception as exc:
        contract_ok = False
        evidence = repr(exc)
    check(checks, "jamia_extension_contract_hashes", contract_ok, evidence)

    required = [
        EXT_TABLES / "stay_calendar_alignment_audit.csv",
        EXT_TABLES / "emar_observability_by_deployment_era.csv",
        EXT_TABLES / "order_conversion_by_observability_scope.csv",
        EXT_TABLES / "first_dose_lag_by_observability_scope.csv",
        EXT_TABLES / "not_given_by_observability_scope.csv",
        EXT_TABLES / "not_given_corrected_model_status.csv",
        EXT_TABLES / "not_given_corrected_prespecified_correlates.csv",
        EXT_TABLES / "anchor_reclassification_by_scope.csv",
        EXT_TABLES / "anchor_model_effects_by_population.csv",
        EXT_TABLES / "anchor_effect_change_by_population.csv",
        EXT_TABLES / "anchor_same_cohort_check_by_population.csv",
        EXT_TABLES / "pilot_gates_after_models.csv",
        REPORTS
        / (
            "16_jamia_observability_v1_1_pre_model_audit.md"
            if EXTENSION_VERSION == "v1_1"
            else "12_jamia_observability_pre_model_audit.md"
        ),
        REPORTS
        / (
            "17_jamia_observability_v1_1_model_results.md"
            if EXTENSION_VERSION == "v1_1"
            else "13_jamia_observability_model_results.md"
        ),
        ENVIRONMENT
        / (
            "R_sessionInfo_JAMIA_observability_v1_1.txt"
            if EXTENSION_VERSION == "v1_1"
            else "R_sessionInfo_JAMIA_observability.txt"
        ),
        EXT_MANIFESTS / "14_jamia_observability_models.json",
    ]
    missing = [
        path.relative_to(PROJECT).as_posix()
        for path in required
        if not path.exists() or path.stat().st_size == 0
    ]
    check(
        checks,
        "required_analytic_assets",
        not missing,
        "all required assets present"
        if not missing
        else "missing/empty: " + ", ".join(missing),
    )

    coverage = pd.read_csv(
        EXT_TABLES / "emar_observability_by_deployment_era.csv"
    )
    coverage_map = coverage.set_index("deployment_era")
    pre_coverage = float(
        coverage_map.loc[
            "pre_implementation", "adult_stays_with_any_emar_pct"
        ]
    )
    overlap_coverage = float(
        coverage_map.loc[
            "implementation_overlap", "adult_stays_with_any_emar_pct"
        ]
    )
    post_coverage = float(
        coverage_map.loc[
            "post_implementation", "adult_stays_with_any_emar_pct"
        ]
    )
    version_specific_coverage_ok = (
        (
            pre_coverage < 2
            and 50 <= overlap_coverage < 90
            and post_coverage >= 95
        )
        if EXTENSION_VERSION == "v1_1"
        else (
            pre_coverage == 0
            and overlap_coverage < 10
            and post_coverage >= 90
        )
    )
    coverage_ok = bool(
        set(coverage_map.index)
        == {
            "pre_implementation",
            "implementation_overlap",
            "post_implementation",
        }
        and int(coverage["adult_stays_n"].sum()) == 94444
        and version_specific_coverage_ok
    )
    check(
        checks,
        "deployment_observability_discontinuity",
        coverage_ok,
        f"pre={pre_coverage:.3f}%; "
        f"overlap={overlap_coverage:.3f}%; "
        f"post={post_coverage:.3f}%; "
        f"stays={int(coverage['adult_stays_n'].sum()):,}",
    )

    full_event = pd.read_csv(TABLES / "emar_full_event_txt_distribution.csv")
    full_rows = int(full_event["rows_n"].sum())
    full_ok = full_rows == 42808593
    check(
        checks,
        "full_emar_reconciliation_retained",
        full_ok,
        f"event_txt distribution sums to {full_rows:,} eMAR rows",
    )

    expected_classes = {
        "stress_ulcer_prophylaxis",
        "vte_prophylaxis",
        "intra_abdominal_antibiotics",
        "electrolyte_replacement",
        "prokinetic",
        "insulin",
    }
    conversion = pd.read_csv(
        EXT_TABLES / "order_conversion_by_observability_scope.csv"
    )
    post_conversion = conversion[
        conversion["analysis_scope"].eq("post_implementation")
    ].copy()
    conversion_ok = bool(
        len(post_conversion) == 6
        and set(post_conversion["drug_class"]) == expected_classes
        and post_conversion["eligible_orders_n"].gt(0).all()
        and post_conversion["conversion_pct"].between(0, 100).all()
    )
    check(
        checks,
        "six_class_post_implementation_conversion",
        conversion_ok,
        f"classes={len(post_conversion)}/6; range="
        f"{post_conversion['conversion_pct'].min():.3f}%–"
        f"{post_conversion['conversion_pct'].max():.3f}%; "
        f"orders={int(post_conversion['eligible_orders_n'].sum()):,}",
    )

    lag = pd.read_csv(
        EXT_TABLES / "first_dose_lag_by_observability_scope.csv"
    )
    post_lag = lag[lag["analysis_scope"].eq("post_implementation")].copy()
    lag_ok = bool(
        len(post_lag) == 6
        and set(post_lag["drug_class"]) == expected_classes
        and post_lag["inferential_lag_n"].gt(0).all()
        and post_lag["median_hours"].map(math.isfinite).all()
    )
    check(
        checks,
        "six_class_post_implementation_lag",
        lag_ok,
        f"classes={len(post_lag)}/6; median range="
        f"{post_lag['median_hours'].min():.3f}–"
        f"{post_lag['median_hours'].max():.3f} hours",
    )

    semantic = pd.read_csv(
        EXT_TABLES / "not_given_by_observability_scope.csv"
    )
    post_semantic = semantic[
        semantic["analysis_scope"].eq("post_implementation")
    ].copy()
    semantic_ok = bool(
        len(post_semantic) == 12
        and set(post_semantic["drug_class"]) == expected_classes
        and set(post_semantic["event_mapping"])
        == {"frozen_primary", "audit_semantic_sensitivity"}
    )
    insulin = post_semantic[post_semantic["drug_class"].eq("insulin")].set_index(
        "event_mapping"
    )
    insulin_primary = float(insulin.loc["frozen_primary", "not_given_pct"])
    insulin_semantic = float(
        insulin.loc["audit_semantic_sensitivity", "not_given_pct"]
    )
    check(
        checks,
        "semantic_sensitivity_complete",
        semantic_ok,
        "12 class-by-mapping cells; insulin not-given "
        f"{insulin_primary:.3f}% primary versus "
        f"{insulin_semantic:.3f}% semantic audit",
    )

    status = pd.read_csv(
        EXT_TABLES / "not_given_corrected_model_status.csv"
    )
    models_ok = bool(
        len(status) == 4
        and status["converged"].map(truthy).all()
        and status["decision_events_n"].gt(0).all()
    )
    check(
        checks,
        "not_given_models_converged",
        models_ok,
        f"{int(status['converged'].map(truthy).sum())}/4 converged",
    )

    same = pd.read_csv(
        EXT_TABLES / "anchor_same_cohort_check_by_population.csv"
    )
    same_ok = bool(
        len(same) == 12
        and same["identical_n_and_outcomes"].map(truthy).all()
    )
    check(
        checks,
        "anchor_same_cohort_pairs",
        same_ok,
        f"{int(same['identical_n_and_outcomes'].map(truthy).sum())}/12 "
        "paired variants have identical n/outcomes",
    )

    change = pd.read_csv(
        EXT_TABLES / "anchor_effect_change_by_population.csv"
    )
    post_change = change[
        change["analysis_population"].eq("post_implementation")
    ].copy()
    a1_primary = post_change[
        post_change["anchor_id"].eq("A1")
        & post_change["model_variant"].eq("published_style_minimal")
    ]
    a2_primary = post_change[
        post_change["anchor_id"].eq("A2")
        & post_change["model_variant"].eq("published_style_minimal")
    ]
    a2_variants = post_change[post_change["anchor_id"].eq("A2")]
    anchor_ok = bool(
        len(a1_primary) == 1
        and len(a2_primary) == 1
        and len(a2_variants) == 4
        and not truthy(a1_primary.iloc[0]["material_effect_change"])
        and truthy(a2_primary.iloc[0]["material_effect_change"])
        and a2_variants["material_effect_change"].map(truthy).all()
    )
    check(
        checks,
        "post_implementation_effect_sensitivity_pattern",
        anchor_ok,
        "A1 primary change="
        f"{float(a1_primary.iloc[0]['relative_absolute_log_effect_change_pct']):.3f}%; "
        "A2 primary change="
        f"{float(a2_primary.iloc[0]['relative_absolute_log_effect_change_pct']):.3f}%; "
        f"A2 material variants={int(a2_variants['material_effect_change'].map(truthy).sum())}/4",
    )

    model_manifest = json.loads(
        (
            EXT_MANIFESTS / "14_jamia_observability_models.json"
        ).read_text(encoding="utf-8")
    )
    any_emar_ok = model_manifest.get(
        "any_emar_used_for_outcome_selection"
    ) is False
    check(
        checks,
        "no_any_emar_outcome_selection",
        any_emar_ok,
        "model manifest records any_emar_used_for_outcome_selection=false",
    )

    gates = pd.read_csv(EXT_TABLES / "pilot_gates_after_models.csv")
    analytic_ids = {f"J{number:02d}" for number in range(1, 9)}
    analytic_gates = gates[gates["gate_id"].isin(analytic_ids)]
    gates_ok = bool(
        len(analytic_gates) == 8
        and analytic_gates["status"].eq("PASS").all()
    )
    check(
        checks,
        "analytic_pilot_gates",
        gates_ok,
        f"{int(analytic_gates['status'].eq('PASS').sum())}/8 PASS; "
        f"decision={model_manifest.get('decision')}",
    )

    failed_log = (
        PROJECT
        / "outputs"
        / "jamia_observability"
        / "logs"
        / "14_runner_stderr.log"
    )
    source_correction = (
        PROJECT
        / "contracts"
        / "jamia_observability_addendum_v1.1_2026-07-30.md"
    )
    failure_retained = bool(
        failed_log.exists()
        and "..gate_id" in failed_log.read_text(encoding="utf-8")
        and (
            EXTENSION_VERSION == "v1_0"
            or source_correction.exists()
        )
    )
    check(
        checks,
        "implementation_failure_audit_retained",
        failure_retained,
        (
            "v1.0 gate-writer and source-definition failures retained; "
            "v1.1 isolated"
            if EXTENSION_VERSION == "v1_1"
            else "first-run gate-writer error retained as implementation audit"
        )
        if failure_retained
        else "required implementation-failure audit missing",
    )

    scripts = [
        PROJECT / "scripts" / "13_build_jamia_observability_extension.py",
        PROJECT / "scripts" / "14_fit_jamia_observability_models.R",
        SCRIPT,
    ]
    prohibited = re.compile(
        r"^\s*(?:from|import)\s+(?:sklearn|xgboost|lightgbm|shap)\b"
        r"|^\s*library\s*\(\s*(?:randomForest|xgboost|lightgbm|shap)"
        r"\s*\)|::\s*nomogram\s*\(",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    hits = [
        path.name
        for path in scripts
        if prohibited.search(path.read_text(encoding="utf-8"))
    ]
    check(
        checks,
        "no_prohibited_methods_in_extension",
        not hits,
        "no ML/SHAP/nomogram implementation"
        if not hits
        else "hits: " + ", ".join(hits),
    )

    checks_frame = pd.DataFrame(checks)
    all_pass = bool(checks_frame["passed"].all())
    write_csv(checks_frame, EXT_TABLES / "analytic_validation_checks.csv")

    key_results = pd.DataFrame(
        [
            {
                "finding": "eMAR observability",
                "estimate": (
                    f"{pre_coverage:.3f}% pre; "
                    f"{overlap_coverage:.3f}% overlap; "
                    f"{post_coverage:.3f}% post implementation"
                ),
            },
            {
                "finding": "Order-to-administration conversion",
                "estimate": (
                    f"{post_conversion['conversion_pct'].min():.3f}%–"
                    f"{post_conversion['conversion_pct'].max():.3f}% "
                    "across six frozen classes"
                ),
            },
            {
                "finding": "Insulin semantic sensitivity",
                "estimate": (
                    f"{insulin_primary:.3f}% versus "
                    f"{insulin_semantic:.3f}% not-given"
                ),
            },
            {
                "finding": "A1 post-implementation drift",
                "estimate": (
                    f"{float(a1_primary.iloc[0]['effect_order']):.3f} to "
                    f"{float(a1_primary.iloc[0]['effect_administration']):.3f}; "
                    f"{float(a1_primary.iloc[0]['relative_absolute_log_effect_change_pct']):.3f}%"
                ),
            },
            {
                "finding": "A2 post-implementation drift",
                "estimate": (
                    f"{float(a2_primary.iloc[0]['effect_order']):.3f} to "
                    f"{float(a2_primary.iloc[0]['effect_administration']):.3f}; "
                    f"{float(a2_primary.iloc[0]['relative_absolute_log_effect_change_pct']):.3f}%"
                ),
            },
        ]
    )
    write_csv(key_results, EXT_TABLES / "jamia_key_results.csv")

    report_lines = [
        (
            "# 18 — JAMIA v1.1 analytic validation and story decision"
            if EXTENSION_VERSION == "v1_1"
            else "# 14 — JAMIA analytic validation and story decision"
        ),
        "",
        f"**Analytic validation: {'PASS' if all_pass else 'FAIL'}.**",
        "",
        "The extension supports a JAMIA-facing story built around a time-varying",
        "medication data-generating process. The evidence is not merely that orders",
        "and administrations differ: observability changes sharply across deployment",
        "eras, residual exposure discordance remains after implementation, and that",
        "discordance propagates differently across two prespecified published-style",
        "association anchors.",
        "",
        "## Key validated findings",
        "",
        *format_markdown_table(key_results),
        "",
        "## Validation checks",
        "",
        *format_markdown_table(checks_frame),
        "",
        "## Decision",
        "",
        (
            "**GO_JAMIA_ANALYTIC.** The post-implementation A2 anchor meets the"
            " frozen material-change rule in the primary model and all three"
            " prespecified robustness variants, whereas A1 remains comparatively"
            " exposure-definition robust. This contrast is the central positive"
            " result: susceptibility to exposure provenance is study-question"
            " specific."
            if all_pass
            else "**NO-GO until failed analytic checks are resolved.**"
        ),
        "",
        (
            "The v1.0 gate-writer and deployment-source errors are retained as"
            if EXTENSION_VERSION == "v1_1"
            else "The retained first-run gate-writer error is retained as"
        ),
        "implementation failures, not statistical failures. No eMAR-presence filter",
        "was used in outcome models, and no causal drug-effect conclusion is supported.",
        "",
    ]
    report_path = REPORTS / (
        "18_jamia_v1_1_analytic_validation_and_story.md"
        if EXTENSION_VERSION == "v1_1"
        else "14_jamia_analytic_validation_and_story.md"
    )
    report_path.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
        newline="\n",
    )

    manifest = {
        "generated_at": now_local(),
        "script": str(SCRIPT),
        "script_sha256": sha256(SCRIPT),
        "extension_version": EXTENSION_VERSION,
        "elapsed_seconds": round(time.time() - started, 3),
        "checks_n": len(checks_frame),
        "checks_pass_n": int(checks_frame["passed"].sum()),
        "checks_fail_n": int((~checks_frame["passed"]).sum()),
        "all_checks_pass": all_pass,
        "failed_checks": checks_frame.loc[
            ~checks_frame["passed"], "check_id"
        ].astype(str).tolist(),
        "decision": (
            "GO_JAMIA_ANALYTIC" if all_pass else "NO_GO_ANALYTIC_VALIDATION"
        ),
        "causal_claim": False,
        "any_emar_used_for_outcome_selection": False,
    }
    write_json(
        manifest,
        EXT_MANIFESTS
        / (
            "18_jamia_v1_1_analytic_validation.json"
            if EXTENSION_VERSION == "v1_1"
            else "15_jamia_analytic_validation.json"
        ),
    )
    print(
        f"JAMIA_ANALYTIC_VALIDATION={'PASS' if all_pass else 'FAIL'} "
        f"{manifest['checks_pass_n']}/{manifest['checks_n']}",
        flush=True,
    )
    if not all_pass:
        print(
            checks_frame.loc[~checks_frame["passed"]].to_string(index=False),
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
