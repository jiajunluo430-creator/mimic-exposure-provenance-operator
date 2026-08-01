from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from common import (
    CACHE,
    MANIFESTS,
    MIMIC_ROOT,
    REPORTS,
    TABLES,
    RunLogger,
    connect_duckdb,
    csv_scan,
    ensure_dirs,
    script_metadata,
    verify_frozen_contract,
    write_csv,
    write_json,
)


SCRIPT = Path(__file__).resolve()
LOG = RunLogger("04_build_published_association_cohorts")


def qdf(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def scalar(con, sql: str) -> int:
    value = con.execute(sql).fetchone()[0]
    return 0 if value is None else int(value)


def table_exists(con, table: str) -> bool:
    return bool(
        con.execute(
            """
            SELECT count(*) > 0
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = ?
            """,
            [table],
        ).fetchone()[0]
    )


def build_diagnosis_flags(con) -> None:
    if table_exists(con, "diagnosis_flags"):
        rows = scalar(con, "SELECT count(*) FROM diagnosis_flags")
        if rows > 0:
            LOG(f"RESUME diagnosis_flags hadm_rows={rows}")
            return
    LOG("START full diagnoses_icd scan for frozen A2 cohort")
    diagnoses = csv_scan(MIMIC_ROOT / "hosp" / "diagnoses_icd.csv.gz")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE diagnosis_flags AS
        WITH normalized AS (
          SELECT
            TRY_CAST(hadm_id AS BIGINT) AS hadm_id,
            upper(
              regexp_replace(coalesce(icd_code, ''), '[.]', '', 'g')
            ) AS code,
            TRY_CAST(icd_version AS INTEGER) AS icd_version
          FROM {diagnoses}
        )
        SELECT
          hadm_id,
          max(
            CASE
              WHEN icd_version = 10
               AND (
                 code LIKE 'A40%' OR code LIKE 'A41%'
                 OR code LIKE 'R652%'
               )
                THEN 1
              WHEN icd_version = 9
               AND (
                 code LIKE '038%' OR code IN ('99591', '99592', '78552')
               )
                THEN 1
              ELSE 0
            END
          ) AS sepsis_icd_flag,
          max(
            CASE
              WHEN icd_version = 10
               AND (
                 code LIKE 'K20%' OR code LIKE 'K21%'
                 OR code LIKE 'K25%' OR code LIKE 'K26%'
                 OR code LIKE 'K27%' OR code LIKE 'K28%'
                 OR code LIKE 'K29%' OR code LIKE 'K226%'
                 OR code LIKE 'K920%' OR code LIKE 'K921%'
                 OR code LIKE 'K922%' OR code LIKE 'I850%'
               )
                THEN 1
              WHEN icd_version = 9
               AND (
                 code LIKE '5301%' OR code = '53081'
                 OR code LIKE '531%' OR code LIKE '532%'
                 OR code LIKE '533%' OR code LIKE '534%'
                 OR code LIKE '535%' OR code LIKE '578%'
               )
                THEN 1
              ELSE 0
            END
          ) AS active_acid_indication_flag,
          count(*) AS diagnosis_rows_n
        FROM normalized
        WHERE hadm_id IS NOT NULL
        GROUP BY hadm_id
        """
    )
    LOG(
        "DONE frozen diagnosis flags "
        f"hadm_rows={scalar(con, 'SELECT count(*) FROM diagnosis_flags')} "
        "sepsis_hadms="
        f"{scalar(con, 'SELECT sum(sepsis_icd_flag) FROM diagnosis_flags')}"
    )


def build_anchor_a1(con) -> None:
    LOG("START A1 identical-cohort order/admin exposure build")
    con.execute(
        """
        CREATE OR REPLACE TABLE anchor_a1_exposure AS
        SELECT
          stay_id,
          1 AS order_exposure,
          max(converted::INTEGER) AS administration_exposure,
          count(*) AS eligible_order_clusters_n,
          sum(converted::INTEGER) AS converted_order_clusters_n
        FROM order_conversion_complete
        WHERE drug_class = 'vte_prophylaxis'
          AND ingredient IN ('heparin', 'enoxaparin')
          AND route_dose_eligible
        GROUP BY stay_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE anchor_a1_cohort AS
        SELECT
          'A1' AS anchor_id,
          s.subject_id, s.hadm_id, s.stay_id,
          s.age_at_icu AS age,
          s.gender,
          s.emergency_admission,
          s.anchor_era,
          s.first_careunit,
          s.intime, s.outtime,
          s.hospital_expire_flag AS outcome,
          coalesce(x.order_exposure, 0) AS order_exposure,
          coalesce(x.administration_exposure, 0)
            AS administration_exposure,
          coalesce(x.eligible_order_clusters_n, 0)
            AS eligible_order_clusters_n,
          coalesce(x.converted_order_clusters_n, 0)
            AS converted_order_clusters_n,
          o.oasis,
          o.oasis_missing_components_n,
          coalesce(o.mechvent, 0) AS first_day_mechvent,
          coalesce(o.first_day_vasopressor, 0)
            AS first_day_vasopressor,
          coalesce(o.first_day_rrt, 0) AS first_day_rrt
        FROM adult_stays s
        LEFT JOIN anchor_a1_exposure x USING (stay_id)
        LEFT JOIN oasis_scores o USING (subject_id, hadm_id, stay_id)
        WHERE s.subject_icu_stays_n = 1
          AND s.hospital_expire_flag IN (0, 1)
        """
    )
    rows = scalar(con, "SELECT count(*) FROM anchor_a1_cohort")
    order_n = scalar(
        con, "SELECT sum(order_exposure) FROM anchor_a1_cohort"
    )
    admin_n = scalar(
        con, "SELECT sum(administration_exposure) FROM anchor_a1_cohort"
    )
    LOG(
        "DONE A1 cohort "
        f"rows={rows} order_exposed={order_n} admin_exposed={admin_n}"
    )


def build_anchor_a2(con) -> None:
    LOG("START A2 identical-cohort first-48h PPI exposure build")
    con.execute(
        """
        CREATE OR REPLACE TABLE anchor_a2_order_exposure AS
        SELECT
          stay_id,
          1 AS order_exposure,
          count(*) AS eligible_order_clusters_n
        FROM eligible_order_clusters
        WHERE drug_class = 'stress_ulcer_prophylaxis'
          AND subclass = 'PPI'
          AND ordertime <= intime + INTERVAL 48 HOUR
          AND coalesce(prescription_stoptime, outtime) >= intime
        GROUP BY stay_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE anchor_a2_admin_exposure AS
        SELECT
          stay_id,
          1 AS administration_exposure,
          count(*) AS given_events_n
        FROM emar_stay_events
        WHERE drug_class = 'stress_ulcer_prophylaxis'
          AND subclass = 'PPI'
          AND event_category = 'given_strict'
          AND charttime BETWEEN intime AND intime + INTERVAL 48 HOUR
        GROUP BY stay_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE anchor_a2_cohort AS
        WITH base AS (
          SELECT
            s.*,
            coalesce(dx.sepsis_icd_flag, 0) AS sepsis_icd_flag,
            coalesce(dx.active_acid_indication_flag, 0)
              AS active_acid_indication_flag,
            coalesce(ox.order_exposure, 0) AS order_exposure,
            coalesce(ax.administration_exposure, 0)
              AS administration_exposure,
            coalesce(ox.eligible_order_clusters_n, 0)
              AS eligible_order_clusters_n,
            coalesce(ax.given_events_n, 0) AS given_events_n,
            CASE
              WHEN s.deathtime IS NOT NULL THEN s.deathtime
              WHEN s.dod IS NOT NULL
                THEN CAST(s.dod AS TIMESTAMP) + INTERVAL 12 HOUR
              ELSE NULL
            END AS death_time,
            o.oasis,
            o.oasis_missing_components_n,
            coalesce(o.mechvent, 0) AS first_day_mechvent,
            coalesce(o.first_day_vasopressor, 0)
              AS first_day_vasopressor,
            coalesce(o.first_day_rrt, 0) AS first_day_rrt
          FROM adult_stays s
          LEFT JOIN diagnosis_flags dx USING (hadm_id)
          LEFT JOIN anchor_a2_order_exposure ox USING (stay_id)
          LEFT JOIN anchor_a2_admin_exposure ax USING (stay_id)
          LEFT JOIN oasis_scores o USING (subject_id, hadm_id, stay_id)
          WHERE s.subject_stay_order = 1
            AND coalesce(dx.sepsis_icd_flag, 0) = 1
            AND coalesce(dx.active_acid_indication_flag, 0) = 0
        ),
        outcomes AS (
          SELECT
            *,
            CASE
              WHEN death_time IS NOT NULL
               AND CAST(death_time AS DATE) >= CAST(intime AS DATE)
               AND CAST(death_time AS DATE)
                   <= CAST(intime AS DATE) + INTERVAL 90 DAY
                THEN 1 ELSE 0
            END AS death_90d,
            CASE
              WHEN death_time IS NOT NULL
               AND CAST(death_time AS DATE) >= CAST(intime AS DATE)
               AND CAST(death_time AS DATE)
                   <= CAST(intime AS DATE) + INTERVAL 90 DAY
                THEN greatest(
                  1.0 / 24.0,
                  date_diff('second', intime, death_time) / 86400.0
                )
              ELSE 90.0
            END AS followup_days
          FROM base
        )
        SELECT
          'A2' AS anchor_id,
          subject_id, hadm_id, stay_id,
          age_at_icu AS age,
          gender,
          emergency_admission,
          anchor_era,
          first_careunit,
          intime, outtime, dischtime,
          order_exposure, administration_exposure,
          eligible_order_clusters_n, given_events_n,
          death_90d AS outcome,
          followup_days,
          CASE
            WHEN dischtime >= intime + INTERVAL 48 HOUR
             AND NOT (
               death_time IS NOT NULL
               AND death_time < intime + INTERVAL 48 HOUR
             )
              THEN 1 ELSE 0
          END AS landmark_48h_eligible,
          oasis,
          oasis_missing_components_n,
          first_day_mechvent,
          first_day_vasopressor,
          first_day_rrt
        FROM outcomes
        """
    )
    rows = scalar(con, "SELECT count(*) FROM anchor_a2_cohort")
    order_n = scalar(
        con, "SELECT sum(order_exposure) FROM anchor_a2_cohort"
    )
    admin_n = scalar(
        con, "SELECT sum(administration_exposure) FROM anchor_a2_cohort"
    )
    LOG(
        "DONE A2 cohort "
        f"rows={rows} order_exposed={order_n} admin_exposed={admin_n}"
    )


def build_anchor_linkage_audit(con) -> None:
    LOG("START anchor-class eMAR POE identity-link audit")
    con.execute(
        """
        CREATE OR REPLACE TABLE anchor_class_emar_linkage AS
        SELECT
          anchor_id,
          count(*) AS strict_given_events_n,
          sum((
            poe_id IS NOT NULL AND trim(poe_id) <> ''
          )::INTEGER) AS poe_nonmissing_n,
          sum(poe_id_any_link::INTEGER) AS poe_any_link_n,
          sum(poe_id_identity_link::INTEGER) AS poe_identity_link_n,
          100.0 * avg(poe_id_identity_link::INTEGER)
            AS poe_identity_link_pct
        FROM (
          SELECT 'A1' AS anchor_id, *
          FROM emar_stay_events
          WHERE drug_class = 'vte_prophylaxis'
            AND ingredient IN ('heparin', 'enoxaparin')
            AND event_category = 'given_strict'
          UNION ALL BY NAME
          SELECT 'A2' AS anchor_id, *
          FROM emar_stay_events
          WHERE drug_class = 'stress_ulcer_prophylaxis'
            AND subclass = 'PPI'
            AND event_category = 'given_strict'
        )
        GROUP BY anchor_id
        ORDER BY anchor_id
        """
    )
    LOG("DONE anchor-class eMAR POE identity-link audit")


def export_and_summarize(con) -> dict[str, object]:
    LOG("START anchor cohort exports and frozen descriptive summaries")
    a1 = qdf(con, "SELECT * FROM anchor_a1_cohort ORDER BY stay_id")
    a2 = qdf(con, "SELECT * FROM anchor_a2_cohort ORDER BY stay_id")
    write_csv(a1, CACHE / "anchor_a1_cohort.csv")
    write_csv(a2, CACHE / "anchor_a2_cohort.csv")

    flow = qdf(
        con,
        """
        SELECT
          'A1' AS anchor_id,
          'adult ICU stays' AS step,
          count(*) AS rows_n
        FROM adult_stays
        UNION ALL
        SELECT 'A1', 'exactly one ICU stay per subject',
               count(*)
        FROM adult_stays
        WHERE subject_icu_stays_n = 1
        UNION ALL
        SELECT 'A1', 'valid hospital outcome; final cohort',
               count(*)
        FROM anchor_a1_cohort
        UNION ALL
        SELECT 'A2', 'adult first ICU stay per subject',
               count(*)
        FROM adult_stays
        WHERE subject_stay_order = 1
        UNION ALL
        SELECT 'A2', 'ICD-coded sepsis',
               count(*)
        FROM adult_stays s
        JOIN diagnosis_flags dx USING (hadm_id)
        WHERE s.subject_stay_order = 1
          AND dx.sepsis_icd_flag = 1
        UNION ALL
        SELECT 'A2', 'after active acid-indication exclusions; final cohort',
               count(*)
        FROM anchor_a2_cohort
        UNION ALL
        SELECT 'A2', '48-hour landmark cohort',
               sum(landmark_48h_eligible)
        FROM anchor_a2_cohort
        """
    )
    write_csv(flow, TABLES / "published_anchor_cohort_flow.csv")

    cross = qdf(
        con,
        """
        SELECT
          anchor_id, order_exposure, administration_exposure,
          count(*) AS patients_n,
          sum(outcome) AS outcomes_n,
          100.0 * avg(outcome) AS outcome_pct
        FROM (
          SELECT anchor_id, order_exposure,
                 administration_exposure, outcome
          FROM anchor_a1_cohort
          UNION ALL
          SELECT anchor_id, order_exposure,
                 administration_exposure, outcome
          FROM anchor_a2_cohort
        )
        GROUP BY ALL
        ORDER BY anchor_id, order_exposure, administration_exposure
        """
    )
    write_csv(cross, TABLES / "published_anchor_exposure_crossclassification.csv")

    prevalence = qdf(
        con,
        """
        SELECT
          anchor_id,
          count(*) AS cohort_n,
          sum(order_exposure) AS order_exposed_n,
          100.0 * avg(order_exposure) AS order_exposed_pct,
          sum(administration_exposure) AS administration_exposed_n,
          100.0 * avg(administration_exposure)
            AS administration_exposed_pct,
          100.0 * avg(
            (order_exposure <> administration_exposure)::INTEGER
          ) AS discordant_pct,
          sum(outcome) AS outcomes_n
        FROM (
          SELECT anchor_id, order_exposure,
                 administration_exposure, outcome
          FROM anchor_a1_cohort
          UNION ALL
          SELECT anchor_id, order_exposure,
                 administration_exposure, outcome
          FROM anchor_a2_cohort
        )
        GROUP BY anchor_id
        ORDER BY anchor_id
        """
    )
    write_csv(prevalence, TABLES / "published_anchor_exposure_prevalence.csv")

    linkage = qdf(
        con,
        "SELECT * FROM anchor_class_emar_linkage ORDER BY anchor_id",
    )
    write_csv(linkage, TABLES / "published_anchor_emar_poe_linkage.csv")

    summary: dict[str, object] = {
        "A1_cohort_n": len(a1),
        "A2_cohort_n": len(a2),
        "A1_order_exposed_n": int(a1["order_exposure"].sum()),
        "A1_administration_exposed_n": int(
            a1["administration_exposure"].sum()
        ),
        "A2_order_exposed_n": int(a2["order_exposure"].sum()),
        "A2_administration_exposed_n": int(
            a2["administration_exposure"].sum()
        ),
        "A2_landmark_48h_n": int(a2["landmark_48h_eligible"].sum()),
    }
    LOG(f"DONE anchor cohort exports {summary}")
    return summary


def render_report(summary: dict[str, object]) -> str:
    flow = pd.read_csv(TABLES / "published_anchor_cohort_flow.csv")
    prevalence = pd.read_csv(
        TABLES / "published_anchor_exposure_prevalence.csv"
    )
    cross = pd.read_csv(
        TABLES / "published_anchor_exposure_crossclassification.csv"
    )
    linkage = pd.read_csv(TABLES / "published_anchor_emar_poe_linkage.csv")
    return "\n".join(
        [
            "# 04 — Prespecified published-association cohorts",
            "",
            "Both anchors were frozen before these cohorts were extracted.",
            "Within each anchor, order-defined and administration-defined",
            "exposures use exactly the same cohort, outcome, and covariates.",
            "This is an exposure-definition sensitivity analysis, not a new",
            "causal efficacy or safety study.",
            "",
            "## Frozen anchors",
            "",
            "- A1: Muchintala R, et al. *Cureus*. 2025;17:e86370.",
            "  PMID 40688991; PMCID PMC12276787;",
            "  DOI 10.7759/cureus.86370.",
            "- A2: Ma C, et al. *Front Pharmacol*. 2025;16:1545533.",
            "  PMID 40612738; PMCID PMC12223537;",
            "  DOI 10.3389/fphar.2025.1545533.",
            "",
            "## Cohort flow",
            "",
            "```text",
            flow.to_string(index=False),
            "```",
            "",
            "## Exposure prevalence",
            "",
            "```text",
            prevalence.to_string(index=False),
            "```",
            "",
            "## Exposure cross-classification",
            "",
            "```text",
            cross.to_string(index=False),
            "```",
            "",
            "## Anchor-class eMAR-to-POE identity linkage",
            "",
            "```text",
            linkage.to_string(index=False),
            "```",
            "",
            "A1 administration exposure is documented strict eMAR delivery",
            "linked to an eligible subcutaneous prophylactic UFH/enoxaparin",
            "order. A2 administration exposure is any strict PPI eMAR",
            "administration in the first 48 hours. The A2 ICD cohort is the",
            "frozen transparent operational re-estimation and is not claimed",
            "to reproduce the publication's Sepsis-3 cohort exactly.",
            "",
            "## Machine-readable summary",
            "",
            "```text",
            str(summary),
            "```",
            "",
        ]
    )


def main() -> None:
    started = time.time()
    ensure_dirs()
    verify_frozen_contract()
    con = connect_duckdb()
    required = (
        "adult_stays",
        "eligible_order_clusters",
        "order_conversion_complete",
        "emar_stay_events",
        "oasis_scores",
    )
    absent = [name for name in required if not table_exists(con, name)]
    if absent:
        raise RuntimeError(
            "Run scripts 01-03 first; missing " + ", ".join(absent)
        )
    build_diagnosis_flags(con)
    build_anchor_a1(con)
    build_anchor_a2(con)
    build_anchor_linkage_audit(con)
    summary = export_and_summarize(con)
    con.close()

    (REPORTS / "04_published_association_cohorts.md").write_text(
        render_report(summary), encoding="utf-8"
    )
    metadata = script_metadata(started, SCRIPT)
    metadata.update(summary)
    metadata.update(
        {
            "same_cohort_and_covariates_within_anchor": True,
            "outcome_models_fitted_here": False,
            "causal_claim": False,
        }
    )
    write_json(
        metadata,
        MANIFESTS / "04_build_published_association_cohorts.json",
    )
    LOG(f"DONE anchor cohort build elapsed={metadata['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
