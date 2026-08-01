from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

import pandas as pd

from common import (
    CACHE,
    ENVIRONMENT,
    MANIFESTS,
    PROJECT,
    REPORTS,
    TABLES,
    now_local,
    verify_frozen_contract,
    verify_semantic_addendum,
    write_csv,
    write_json,
)


SCRIPT = Path(__file__).resolve()


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "pass")


def check(
    records: list[dict[str, object]],
    check_id: str,
    passed: bool,
    evidence: str,
) -> None:
    records.append(
        {
            "check_id": check_id,
            "passed": bool(passed),
            "evidence": evidence,
        }
    )


def main() -> None:
    started = time.time()
    records: list[dict[str, object]] = []

    try:
        frozen = verify_frozen_contract()
        check(
            records,
            "frozen_contract_hashes",
            bool(frozen["match"].all() and len(frozen) == 5),
            f"{int(frozen['match'].sum())}/5 frozen files match SHA256",
        )
    except Exception as exc:
        check(records, "frozen_contract_hashes", False, repr(exc))

    try:
        addendum = verify_semantic_addendum()
        check(
            records,
            "semantic_addendum_hashes",
            bool(addendum["match"].all() and len(addendum) == 2),
            f"{int(addendum['match'].sum())}/2 addendum files match SHA256",
        )
    except Exception as exc:
        check(records, "semantic_addendum_hashes", False, repr(exc))

    required_reports = [
        REPORTS / "01_full_interface_audit.md",
        REPORTS / "02_primary_estimands.md",
        REPORTS / "03_severity_shift_organ_support.md",
        REPORTS / "04_published_association_cohorts.md",
        REPORTS / "05_published_association_effect_change.md",
        REPORTS / "06_eicu_semantic_contrast_and_pilot_gates.md",
        REPORTS / "07_final_qdp_decision.md",
    ]
    check(
        records,
        "qdp_01_07_present",
        all(path.exists() and path.stat().st_size > 0 for path in required_reports),
        "; ".join(
            f"{path.name}={'yes' if path.exists() else 'no'}"
            for path in required_reports
        ),
    )

    required_scripts = [
        PROJECT / "scripts" / name
        for name in (
            "common.py",
            "01_full_interface_audit.py",
            "02_build_primary_estimands.py",
            "03_build_severity_notgiven.py",
            "04_build_published_association_cohorts.py",
            "05_fit_prespecified_models.R",
            "06_finalize_qdp.py",
            "07_validate_package.py",
            "run_all.ps1",
        )
    ]
    check(
        records,
        "reproducible_scripts_present",
        all(path.exists() for path in required_scripts),
        f"{sum(path.exists() for path in required_scripts)}/"
        f"{len(required_scripts)} scripts present",
    )

    required_tables = [
        "emar_full_event_txt_distribution.csv",
        "emar_full_poe_link_summary.csv",
        "emar_detail_availability_by_class.csv",
        "emar_not_given_reason_fields.csv",
        "d_items_zero_fact_rows_complete.csv",
        "inputevents_225925_reproduction.csv",
        "order_to_administration_conversion.csv",
        "first_dose_lag_distribution.csv",
        "first_dose_lag_audit.csv",
        "not_given_proportion_by_class_unadjusted.csv",
        "oasis_component_coverage.csv",
        "not_given_prespecified_correlates.csv",
        "not_given_audit_semantic_sensitivity_class_rates.csv",
        "not_given_audit_semantic_sensitivity_correlates.csv",
        "published_anchor_exposure_crossclassification.csv",
        "published_association_model_effects.csv",
        "published_association_effect_change.csv",
        "published_association_same_cohort_check.csv",
        "eicu_interface_semantic_summary.csv",
    ]
    missing_tables = [
        name for name in required_tables if not (TABLES / name).exists()
    ]
    check(
        records,
        "machine_readable_tables_present",
        not missing_tables,
        "all required tables present"
        if not missing_tables
        else "missing: " + ", ".join(missing_tables),
    )

    required_cache = [
        CACHE / "not_given_model_aggregated.csv",
        CACHE / "not_given_audit_semantic_sensitivity_aggregated.csv",
        CACHE / "anchor_a1_cohort.csv",
        CACHE / "anchor_a2_cohort.csv",
    ]
    check(
        records,
        "model_input_caches_present",
        all(path.exists() and path.stat().st_size > 0 for path in required_cache),
        f"{sum(path.exists() for path in required_cache)}/4 model caches present",
    )

    audit_path = MANIFESTS / "01_full_interface_audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        full_ok = bool(
            int(audit["emar_rows_n"]) == int(audit["distribution_sum_n"])
            and truthy(audit["distribution_reconciles"])
            and truthy(audit["full_table_not_sample"])
            and audit["ignore_errors"] is False
        )
        evidence = (
            f"rows={int(audit['emar_rows_n']):,}; "
            f"sum={int(audit['distribution_sum_n']):,}; "
            f"ignore_errors={audit['ignore_errors']}"
        )
    else:
        full_ok = False
        evidence = "01 audit manifest absent"
    check(records, "full_emar_reconciliation", full_ok, evidence)

    source_path = MANIFESTS / "source_immutability_audit.csv"
    if source_path.exists():
        source = pd.read_csv(source_path)
        source_ok = len(source) > 0 and source["unchanged"].map(truthy).all()
        evidence = f"{int(source['unchanged'].map(truthy).sum())}/{len(source)} unchanged"
    else:
        source_ok = False
        evidence = "source immutability audit absent"
    check(records, "source_immutability", bool(source_ok), evidence)

    conversion_path = TABLES / "order_to_administration_conversion.csv"
    if conversion_path.exists():
        conversion = pd.read_csv(conversion_path)
        expected = {
            "stress_ulcer_prophylaxis",
            "vte_prophylaxis",
            "intra_abdominal_antibiotics",
            "electrolyte_replacement",
            "prokinetic",
            "insulin",
        }
        class_ok = (
            len(conversion) == 6
            and set(conversion["drug_class"].astype(str)) == expected
        )
        evidence = f"{len(conversion)}/6 classes; eligible={int(conversion['eligible_orders_n'].sum()):,}"
    else:
        class_ok = False
        evidence = "conversion table absent"
    check(records, "six_frozen_classes", class_ok, evidence)

    denominator_path = TABLES / "emar_decision_denominator_by_class.csv"
    if denominator_path.exists():
        denominator = pd.read_csv(denominator_path)
        needed = {
            "given_n",
            "not_given_n",
            "flushed_n",
            "confirmed_n",
            "blank_n",
            "other_excluded_n",
        }
        exclusion_ok = needed.issubset(denominator.columns) and len(denominator) == 6
        evidence = (
            f"columns={sorted(needed.intersection(denominator.columns))}; "
            f"rows={len(denominator)}"
        )
    else:
        exclusion_ok = False
        evidence = "decision denominator table absent"
    check(records, "event_exclusions_separate", exclusion_ok, evidence)

    target_path = TABLES / "inputevents_225925_reproduction.csv"
    if target_path.exists():
        target = pd.read_csv(target_path)
        target_ok = bool(
            len(target) == 1
            and int(target.iloc[0]["itemid"]) == 225925
            and int(target.iloc[0]["fact_rows_n"]) == 0
            and str(target.iloc[0]["label"]).strip().lower()
            == "potassium phosphate"
        )
        evidence = target.to_dict("records").__repr__()
    else:
        target_ok = False
        evidence = "225925 reproduction table absent"
    check(records, "inputevents_225925", target_ok, evidence)

    same_path = TABLES / "published_association_same_cohort_check.csv"
    effects_path = TABLES / "published_association_model_effects.csv"
    if same_path.exists() and effects_path.exists():
        same = pd.read_csv(same_path)
        effects = pd.read_csv(effects_path)
        primary_same = same[
            same["model_variant"].eq("published_style_minimal")
        ]
        primary_effects = effects[
            effects["model_variant"].eq("published_style_minimal")
        ]
        pairs_ok = bool(
            set(primary_same["anchor_id"]) == {"A1", "A2"}
            and primary_same["identical_n_and_outcomes"].map(truthy).all()
            and len(primary_effects) == 4
            and primary_effects["effect"].map(math.isfinite).all()
            and primary_effects["converged"].map(truthy).all()
        )
        evidence = (
            f"primary pairs={len(primary_effects)}/4; "
            f"same-cohort anchors={int(primary_same['identical_n_and_outcomes'].map(truthy).sum())}/2"
        )
    else:
        pairs_ok = False
        evidence = "association model audit tables absent"
    check(records, "published_anchor_model_pairs", pairs_ok, evidence)

    pilot_path = PROJECT / "pilot_gates.csv"
    if pilot_path.exists():
        pilot = pd.read_csv(pilot_path)
        non_g14 = pilot[~pilot["gate_id"].eq("G14")]
        gate_ok = not non_g14["status"].eq("PENDING").any()
        evidence = (
            f"rows={len(pilot)}; fail={int(pilot['status'].eq('FAIL').sum())}; "
            f"pending_non_G14={int(non_g14['status'].eq('PENDING').sum())}"
        )
    else:
        gate_ok = False
        evidence = "pilot_gates.csv absent"
    check(records, "pilot_gate_table_complete", gate_ok, evidence)

    report06 = REPORTS / "06_eicu_semantic_contrast_and_pilot_gates.md"
    report07 = REPORTS / "07_final_qdp_decision.md"
    boundary_ok = False
    claim_ok = False
    if report06.exists() and report07.exists():
        text06 = report06.read_text(encoding="utf-8").lower()
        text07 = report07.read_text(encoding="utf-8").lower()
        boundary_ok = (
            "interface-semantic contrast" in text06
            or "interface semantics" in text06
        ) and "no eicu treatment, timing, dose, or outcome" in text06
        claim_ok = (
            "does not establish drug efficacy" in text07
            and "no causal drug claim" in text07
        )
    check(
        records,
        "eicu_semantic_boundary",
        boundary_ok,
        "required no-external-validation wording present"
        if boundary_ok
        else "required eICU boundary wording absent",
    )
    check(
        records,
        "noncausal_claim_boundary",
        claim_ok,
        "required noncausal wording present"
        if claim_ok
        else "required noncausal wording absent",
    )

    prohibited = re.compile(
        r"^\s*(?:from|import)\s+"
        r"(?:sklearn|xgboost|lightgbm|shap)\b"
        r"|^\s*library\s*\(\s*(?:randomForest|xgboost|lightgbm|shap)"
        r"\s*\)|::\s*nomogram\s*\(",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    hits = []
    for path in sorted((PROJECT / "scripts").glob("*")):
        if path.suffix.lower() not in (".py", ".r"):
            continue
        if prohibited.search(path.read_text(encoding="utf-8")):
            hits.append(path.name)
    check(
        records,
        "no_prohibited_methods",
        not hits,
        "no ML/SHAP/nomogram implementation"
        if not hits
        else "hits: " + ", ".join(hits),
    )

    environment_files = [
        ENVIRONMENT / "Python_sessionInfo.txt",
        ENVIRONMENT / "R_sessionInfo.txt",
    ]
    check(
        records,
        "session_information",
        all(path.exists() and path.stat().st_size > 0 for path in environment_files),
        "; ".join(
            f"{path.name}={'yes' if path.exists() else 'no'}"
            for path in environment_files
        ),
    )

    manifest_path = MANIFESTS / "reproducibility_manifest.csv"
    if manifest_path.exists():
        manifest = pd.read_csv(manifest_path)
        manifest_ok = (
            len(manifest) > 0
            and {"relative_path", "size_bytes", "sha256"}.issubset(
                manifest.columns
            )
            and manifest["sha256"].astype(str).str.fullmatch(
                r"[0-9a-fA-F]{64}"
            ).all()
        )
        evidence = f"{len(manifest):,} files hashed"
    else:
        manifest_ok = False
        evidence = "reproducibility manifest absent"
    check(records, "reproducibility_manifest", manifest_ok, evidence)

    frame = pd.DataFrame(records)
    all_pass = bool(frame["passed"].all())
    write_csv(frame, TABLES / "validation_checks.csv")
    result = {
        "generated_at": now_local(),
        "script": str(SCRIPT),
        "elapsed_seconds": round(time.time() - started, 3),
        "checks_n": len(frame),
        "checks_pass_n": int(frame["passed"].sum()),
        "checks_fail_n": int((~frame["passed"]).sum()),
        "all_checks_pass": all_pass,
        "failed_checks": frame.loc[
            ~frame["passed"], "check_id"
        ].astype(str).tolist(),
    }
    write_json(result, MANIFESTS / "07_validation.json")
    print(
        f"VALIDATION={'PASS' if all_pass else 'FAIL'} "
        f"{result['checks_pass_n']}/{result['checks_n']}",
        flush=True,
    )
    if not all_pass:
        print(
            frame.loc[~frame["passed"]].to_string(index=False),
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
