from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "outputs" / "jamia_prereview_upgrade_v1_0"
TABLES = OUTPUT / "tables"
LOGS = OUTPUT / "logs"
MANIFESTS = OUTPUT / "manifests"
CANDIDATES = TABLES / "published_operator_randomized_open_fulltext_candidates.csv"
CONTRACT = PROJECT / "contracts" / "jamia_prereview_upgrade_addendum_v1.0_2026-07-31.md"
EXPECTED_CONTRACT_SHA256 = "0a851a99c9176c16deda2cde9e30fded7f2b5131a5a3f64ac7f050ebd8f81d9d"
TARGET_N = 40
LAST_SCREENED_RANK = 149


def rec(
    construct: str,
    source_layer: str,
    source_evidence: str,
    named_native_table: bool,
    identity_rule: bool,
    identity_evidence: str,
    time_rule: bool,
    time_evidence: str,
    event_semantics: bool,
    dose_route: bool,
    dose_route_evidence: str,
) -> dict[str, object]:
    return {
        "medication_construct": construct,
        "source_layer": source_layer,
        "source_evidence": source_evidence,
        "named_native_table_reported": named_native_table,
        "database_identity_rule_reported": identity_rule,
        "identity_evidence": identity_evidence,
        "time_origin_and_window_reported": time_rule,
        "time_evidence": time_evidence,
        "event_semantics_reported": event_semantics,
        "dose_or_route_reported": dose_route,
        "dose_route_evidence": dose_route_evidence,
    }


# Manual full-text coding, in the prespecified randomized sequence. Evidence is
# paraphrased to avoid redistributing article text. "Database identity rule"
# means an executable database field/code/list/identifier, not a clinical drug
# name alone. "Event semantics" means an explicit administered/held/not-given
# state predicate or equivalent native-event rule.
MANUAL: dict[int, dict[str, object]] = {
    3: rec("early prophylactic unfractionated heparin", "administration", "receipt within the ICU window", False, False, "clinical name only", True, "within 24 h after ICU admission", False, True, "5000 U/mL, 1 mL, subcutaneous"),
    4: rec("early unfractionated heparin", "administration", "receipt of subcutaneous UFH", False, False, "clinical name only", True, "first 24 h after ICU admission", False, True, "subcutaneous route"),
    6: rec("vancomycin TDM strategy", "administration", "intravenous vancomycin receipt plus TDM", False, False, "clinical name only", True, "after ICU admission/during ICU treatment", False, True, "intravenous route"),
    10: rec("acetaminophen use", "administration", "at least one hospitalization administration record", False, False, "clinical name only", True, "during the hospitalization", False, True, "dose and treatment duration analysed"),
    11: rec("antibiotic use", "administration", "antibiotic administration", False, False, "drug class only", True, "24 h before to 48 h after ICU admission", False, False, "not specified"),
    13: rec("cephalosporin/antibiotic exposure", "administration", "detailed antibiotic administration records", False, False, "drug-category labels only", True, "during hospitalization", False, True, "cumulative defined daily dose"),
    16: rec("ramelteon exposure", "hybrid", "prescription plus documented administration", False, False, "clinical name only", True, "during ICU/hospital stay", False, True, "cumulative dose, standard dose, enteral route"),
    18: rec("aspirin exposure", "order", "oral aspirin prescription", False, False, "clinical name only", True, "first 72 h after ICU admission", False, True, "oral route"),
    20: rec("prophylactic PPI exposure", "order", "prescription start/end records", False, False, "clinical PPI class only", True, "6 h before to 48 h after ICU admission", False, True, "route and dosage recorded"),
    23: rec("intravenous magnesium sulfate", "order", "prescriptions table", True, False, "clinical name only", True, "after ICU admission without a tighter limit", False, True, "intravenous route"),
    26: rec("PPI versus H2RA", "unspecified", "medication use without a named source", False, False, "drug classes only", True, "during ICU admission", False, False, "not specified"),
    32: rec("heparin treatment duration", "administration", "first heparin administration", False, False, "clinical name only", True, "hospital stay; typically within 24 h", False, False, "duration reported, not dose/route"),
    34: rec("amlodipine dose", "administration", "eMAR-derived tables", True, False, "clinical name only", True, "first 24 h after hospital admission", False, True, "aggregate 5 mg versus 10 mg"),
    41: rec("vasopressor/inotrope use", "administration", "use during ICU admission", False, False, "five clinical drug names", True, "during ICU admission", False, False, "not specified"),
    46: rec("early prophylactic heparin", "hybrid", "eMAR and pharmacy records", True, False, "clinical name plus route, no join rule", True, "first 72 h after hospital admission", False, True, "subcutaneous route and total dose"),
    50: rec("total vasoactive-agent exposure", "administration", "medication administration records", False, False, "drug class only", False, "septic-shock origin named but exposure window incomplete", False, True, "cumulative dose analysed"),
    53: rec("initial antibiotic type and timing", "administration", "first administered antibiotic", False, False, "clinical antibiotic list", True, "within 48 h of sepsis diagnosis with hourly strata", False, False, "not specified"),
    58: rec("antibiotic use", "administration", "receipt of any antibiotic", False, False, "drug class only", True, "during first ICU admission", False, False, "not specified"),
    63: rec("norepinephrine dose", "administration", "dose stream/pump-derived administrations", False, False, "clinical name only", True, "first 24 h after septic-shock diagnosis", False, True, "peak and diagnosis doses with salt conversion"),
    64: rec("unfractionated heparin", "order", "medication management/pharmacy record", False, True, "single pharmacy_id explicitly reported", False, "no complete exposure window reported", False, True, "injection formulation"),
    65: rec("early versus delayed anticoagulation", "administration", "medication administration records", False, False, "agent types named, no field/code rule", True, "48-h ICU landmark", False, True, "IV/SC routes and anticoagulant type"),
    66: rec("5% versus 25% albumin", "administration", "documented HSA receipt", False, False, "clinical concentration labels", True, "during ICU admission", False, True, "5% versus 25% concentration"),
    70: rec("pravastatin use", "order", "prescriptions table", True, False, "clinical name only", True, "first 24 h after ICU admission", False, False, "not specified"),
    79: rec("aspirin exposure", "order", "oral aspirin prescription described as administered", False, False, "clinical name only", True, "first 3 days after ICU admission", False, True, "oral route"),
    86: rec("oral anticoagulation", "administration", "OAC administration", False, False, "clinical class only", False, "complete exposure window not reported", False, True, "oral route"),
    87: rec("intravenous glucocorticoids", "administration", "receipt of IV glucocorticoid therapy", False, False, "clinical class only", True, "within one week of admission", False, True, "IV route, timing, duration, daily dose"),
    88: rec("vancomycin TDM strategy", "administration", "vancomycin administration plus TDM", False, False, "clinical name only", True, "during ICU hospitalization", False, True, "intravenous route"),
    95: rec("early prophylactic UFH", "administration", "UFH receipt", False, False, "clinical name only", True, "early ICU treatment, analysed time-dependently", False, True, "subcutaneous route and daily dose"),
    97: rec("early acetaminophen", "order", "prescriptions table", True, False, "clinical name only", True, "first 48 h after ICU admission", False, True, "any form/route required"),
    104: rec("vancomycin TDM strategy", "administration", "documented IV vancomycin plus TDM", False, False, "clinical name only", True, "during ICU stay", False, True, "IV route and cumulative dose"),
    109: rec("enoxaparin duration", "hybrid", "inputevents and prescriptions tables", True, False, "clinical name only; no reconciliation rule", True, "index hospitalization from first administration", False, True, "days, cumulative dose, frequency, daily dose"),
    116: rec("early prophylactic heparin", "administration", "initial administration and subsequent doses", False, False, "clinical name only", True, "first 72 h after ICU admission", False, True, "time to first dose and cumulative doses"),
    117: rec("laxative type", "administration", "receipt of one of four laxatives", False, False, "four clinical names only", True, "during ICU stay", False, False, "not specified"),
    127: rec("empirical antifungal therapy", "unspecified", "treatment status without a named medication source", False, False, "antifungal names described but no executable rule", False, "empirical timing not operationalized in the report", False, False, "not specified"),
    133: rec("heparin dose group", "administration", "subcutaneous heparin administrations", False, False, "clinical name only", False, "complete exposure window not reported", False, True, "subcutaneous route and daily-dose groups"),
    134: rec("vasoactive dose-time trajectory", "administration", "hourly vasoactive dose stream", False, False, "norepinephrine-equivalent construct, no field/code rule", True, "0 to 72 h from initial vasoactive use", False, True, "hourly norepinephrine-equivalent dose"),
    135: rec("early prophylactic heparin", "administration", "subcutaneous heparin receipt", False, False, "clinical name only", True, "first 24 h after ICU admission", False, True, "subcutaneous prophylactic dose"),
    138: rec("early prophylactic heparin", "order", "medical order system", False, False, "clinical name/indication only", True, "within 48 h after ICU admission", False, True, "5000 U subcutaneous, order start/end"),
    145: rec("early prophylactic anticoagulation", "hybrid", "administration verified against medical orders", False, False, "clinical name/dose only", True, "first 24 h after ICU admission", False, True, "5000 U subcutaneous heparin"),
    149: rec("DOAC versus warfarin", "order", "prescription records", False, False, "clinical drug list only", True, "more than 10 days during ICU stay", False, False, "dose and route not specified"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    for directory in (TABLES, LOGS, MANIFESTS):
        directory.mkdir(parents=True, exist_ok=True)
    if sha256(CONTRACT) != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError("Frozen prereview addendum hash mismatch")
    if len(MANUAL) != TARGET_N:
        raise RuntimeError(f"Expected {TARGET_N} coded studies, found {len(MANUAL)}")

    candidates = pd.read_csv(CANDIDATES, dtype=str)
    candidates["random_rank"] = pd.to_numeric(candidates["random_rank"], errors="raise").astype(int)
    screened = candidates.loc[candidates["random_rank"] <= LAST_SCREENED_RANK].copy()
    selected = candidates.loc[candidates["random_rank"].isin(MANUAL)].copy()
    selected = selected.sort_values("random_rank").reset_index(drop=True)
    if selected.shape[0] != TARGET_N:
        raise RuntimeError("One or more manually selected ranks are absent")

    rows: list[dict[str, object]] = []
    for sample_order, (_, article) in enumerate(selected.iterrows(), start=1):
        rank = int(article["random_rank"])
        coded = MANUAL[rank]
        row = {
            "sample_order": sample_order,
            "random_rank": rank,
            "pmid": article["pmid"],
            "pmcid": article["pmcid"],
            "doi": article["doi"],
            "publication_year": article["publication_year"],
            "title": article["title"],
            **coded,
        }
        row["fully_executable_exposure_operator"] = bool(
            row["named_native_table_reported"]
            and row["database_identity_rule_reported"]
            and row["time_origin_and_window_reported"]
            and row["event_semantics_reported"]
        )
        rows.append(row)
    sample = pd.DataFrame(rows)

    screen = screened[
        ["random_rank", "pmid", "pmcid", "doi", "publication_year", "title"]
    ].copy()
    screen["eligibility"] = screen["random_rank"].map(
        lambda rank: "included" if int(rank) in MANUAL else "excluded"
    )
    screen["screen_reason"] = screen["eligibility"].map(
        {
            "included": "focal medication exposure associated with a clinical outcome",
            "excluded": "not a focal medication exposure-outcome study or prediction/algorithm-only study",
        }
    )

    dimensions = [
        ("Named native medication table/source", "named_native_table_reported"),
        ("Database-executable identity rule", "database_identity_rule_reported"),
        ("Time origin and exposure window", "time_origin_and_window_reported"),
        ("Native event-state semantics", "event_semantics_reported"),
        ("Dose or route constraint", "dose_or_route_reported"),
        ("Fully executable operator", "fully_executable_exposure_operator"),
    ]
    summary_rows: list[dict[str, object]] = []
    for label, column in dimensions:
        n = int(sample[column].astype(bool).sum())
        summary_rows.append(
            {
                "reporting_dimension": label,
                "reported_n": n,
                "sample_n": TARGET_N,
                "reported_percent": 100.0 * n / TARGET_N,
            }
        )
    reporting = pd.DataFrame(summary_rows)

    source_summary = (
        sample.groupby("source_layer", dropna=False)
        .size()
        .rename("n")
        .reset_index()
        .sort_values(["n", "source_layer"], ascending=[False, True])
    )
    source_summary["percent"] = 100.0 * source_summary["n"] / TARGET_N

    flow = pd.DataFrame(
        [
            {"stage": "PubMed records returned by frozen query", "n": 379},
            {"stage": "English, non-review records with open full text", "n": 293},
            {"stage": "Randomized full texts screened sequentially", "n": int(screened.shape[0])},
            {"stage": "Focal medication exposure-outcome studies included", "n": TARGET_N},
            {"stage": "Screened full texts excluded", "n": int(screened.shape[0] - TARGET_N)},
        ]
    )

    paths = {
        "sample": TABLES / "published_operator_landscape_sample.csv",
        "screen": TABLES / "published_operator_landscape_screening.csv",
        "reporting": TABLES / "published_operator_landscape_reporting_summary.csv",
        "source": TABLES / "published_operator_landscape_source_summary.csv",
        "flow": TABLES / "published_operator_landscape_flow.csv",
    }
    sample.to_csv(paths["sample"], index=False)
    screen.to_csv(paths["screen"], index=False)
    reporting.to_csv(paths["reporting"], index=False)
    source_summary.to_csv(paths["source"], index=False)
    flow.to_csv(paths["flow"], index=False)

    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "random_seed": 20260731,
        "target_n": TARGET_N,
        "last_screened_random_rank": LAST_SCREENED_RANK,
        "coding_definition": {
            "database_identity_rule": "executable database field, code, list, or identifier; a clinical name alone does not qualify",
            "event_semantics": "explicit native-event predicate distinguishing administered from held/not-given or equivalent states",
            "fully_executable": "named native table/source plus identity rule plus time rule plus event semantics",
        },
        "outputs": {
            name: {"path": str(path.relative_to(PROJECT)), "sha256": sha256(path)}
            for name, path in paths.items()
        },
    }
    manifest_path = MANIFESTS / "32_published_operator_landscape_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log_path = LOGS / "32_finalize_published_operator_landscape.log"
    log_path.write_text(
        "\n".join(
            [
                f"{datetime.now().astimezone().isoformat()}\tmanual_full_text_coding_complete",
                f"screened={screened.shape[0]}",
                f"included={sample.shape[0]}",
                f"fully_executable={int(sample['fully_executable_exposure_operator'].sum())}",
                f"manifest={manifest_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(reporting.to_string(index=False))
    print(source_summary.to_string(index=False))


if __name__ == "__main__":
    main()
