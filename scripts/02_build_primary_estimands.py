from __future__ import annotations

import math
import time
from pathlib import Path

import pandas as pd

from common import (
    MANIFESTS,
    MIMIC_ROOT,
    REPORTS,
    TABLES,
    RunLogger,
    class_case_sql,
    connect_duckdb,
    csv_scan,
    ensure_dirs,
    ingredient_case_sql,
    load_whitelist,
    regex_sql_condition,
    script_metadata,
    sql_quote,
    subclass_case_sql,
    verify_frozen_contract,
    write_csv,
    write_json,
)


SCRIPT = Path(__file__).resolve()
LOG = RunLogger("02_build_primary_estimands")


def qdf(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def scalar(con, sql: str) -> int:
    return int(con.execute(sql).fetchone()[0])


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


def build_adult_stays(con) -> None:
    if table_exists(con, "adult_stays"):
        rows = scalar(con, "SELECT count(*) FROM adult_stays")
        if rows > 0:
            LOG(f"RESUME adult_stays rows={rows}")
            return
    LOG("START adult ICU-stay cohort")
    icu = csv_scan(MIMIC_ROOT / "icu" / "icustays.csv.gz")
    patients = csv_scan(MIMIC_ROOT / "hosp" / "patients.csv.gz")
    admissions = csv_scan(MIMIC_ROOT / "hosp" / "admissions.csv.gz")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE adult_stays AS
        WITH joined AS (
          SELECT
            TRY_CAST(i.subject_id AS BIGINT) AS subject_id,
            TRY_CAST(i.hadm_id AS BIGINT) AS hadm_id,
            TRY_CAST(i.stay_id AS BIGINT) AS stay_id,
            i.first_careunit,
            i.last_careunit,
            TRY_CAST(i.intime AS TIMESTAMP) AS intime,
            TRY_CAST(i.outtime AS TIMESTAMP) AS outtime,
            TRY_CAST(i.los AS DOUBLE) AS icu_los_days,
            p.gender,
            TRY_CAST(p.anchor_age AS INTEGER) AS anchor_age,
            TRY_CAST(p.anchor_year AS INTEGER) AS anchor_year,
            p.anchor_year_group,
            TRY_CAST(p.dod AS DATE) AS dod,
            TRY_CAST(a.admittime AS TIMESTAMP) AS admittime,
            TRY_CAST(a.dischtime AS TIMESTAMP) AS dischtime,
            TRY_CAST(a.deathtime AS TIMESTAMP) AS deathtime,
            a.admission_type,
            a.admission_location,
            a.discharge_location,
            a.race,
            TRY_CAST(a.hospital_expire_flag AS INTEGER)
              AS hospital_expire_flag,
            TRY_CAST(p.anchor_age AS INTEGER)
              + year(TRY_CAST(i.intime AS TIMESTAMP))
              - TRY_CAST(p.anchor_year AS INTEGER) AS age_at_icu
          FROM {icu} i
          JOIN {patients} p ON i.subject_id = p.subject_id
          JOIN {admissions} a ON i.hadm_id = a.hadm_id
        )
        SELECT
          *,
          row_number() OVER (
            PARTITION BY subject_id ORDER BY intime, stay_id
          ) AS subject_stay_order,
          row_number() OVER (
            PARTITION BY hadm_id ORDER BY intime, stay_id
          ) AS hadm_stay_order,
          count(*) OVER (PARTITION BY subject_id) AS subject_icu_stays_n,
          count(*) OVER (PARTITION BY hadm_id) AS hadm_icu_stays_n,
          CASE
            WHEN upper(coalesce(admission_type, '')) IN (
              'EMERGENCY', 'URGENT', 'EW EMER.'
            ) THEN 1 ELSE 0
          END AS emergency_admission,
          CASE
            WHEN anchor_year_group IN ('2008 - 2010', '2011 - 2013')
              THEN '2008-2013'
            WHEN anchor_year_group IN ('2014 - 2016', '2017 - 2019')
              THEN '2014-2019'
            ELSE '2020-2022'
          END AS anchor_era
        FROM joined
        WHERE age_at_icu >= 18
          AND intime IS NOT NULL
          AND outtime IS NOT NULL
          AND outtime > intime
        """
    )
    LOG(
        "DONE adult ICU-stay cohort "
        f"rows={scalar(con, 'SELECT count(*) FROM adult_stays')}"
    )


def build_pharmacy_candidates(con, whitelist: pd.DataFrame) -> None:
    if table_exists(con, "pharmacy_name_candidates"):
        rows = scalar(con, "SELECT count(*) FROM pharmacy_name_candidates")
        if rows > 0:
            LOG(f"RESUME pharmacy candidates rows={rows}")
            return
    LOG("START full pharmacy frozen-name scan")
    pharmacy = csv_scan(MIMIC_ROOT / "hosp" / "pharmacy.csv.gz")
    text = "lower(trim(coalesce(p.medication, '')))"
    any_match = regex_sql_condition(text, whitelist)
    class_case = class_case_sql(text, whitelist, "drug_class")
    ingredient_case = ingredient_case_sql(text, whitelist, "ingredient")
    subclass_case = subclass_case_sql(text, whitelist, "subclass")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE pharmacy_name_candidates AS
        SELECT
          TRY_CAST(p.subject_id AS BIGINT) AS subject_id,
          TRY_CAST(p.hadm_id AS BIGINT) AS hadm_id,
          p.pharmacy_id,
          p.poe_id,
          TRY_CAST(p.starttime AS TIMESTAMP) AS pharmacy_starttime,
          TRY_CAST(p.stoptime AS TIMESTAMP) AS pharmacy_stoptime,
          p.medication AS pharmacy_medication,
          p.status AS pharmacy_status,
          p.route AS pharmacy_route,
          p.frequency AS pharmacy_frequency,
          p.sliding_scale,
          {class_case},
          {ingredient_case},
          {subclass_case}
        FROM {pharmacy} p
        WHERE {any_match}
        """
    )
    LOG(
        "DONE pharmacy frozen-name scan "
        f"rows={scalar(con, 'SELECT count(*) FROM pharmacy_name_candidates')}"
    )


def build_prescription_candidates(con, whitelist: pd.DataFrame) -> None:
    if table_exists(con, "prescription_candidates"):
        rows = scalar(con, "SELECT count(*) FROM prescription_candidates")
        if rows > 0:
            LOG(f"RESUME prescription candidates rows={rows}")
            return
    LOG("START full prescriptions scan with pharmacy-name recovery")
    prescriptions = csv_scan(
        MIMIC_ROOT / "hosp" / "prescriptions.csv.gz"
    )
    raw_name_text = (
        "lower(trim(coalesce(p.drug, '') || ' ' || "
        "coalesce(p.formulary_drug_cd, '')))"
    )
    dictionary_name_text = "d.name_key"
    dictionary_ingredient_case = ingredient_case_sql(
        dictionary_name_text, whitelist, "direct_ingredient"
    )
    ingredient_map = whitelist[
        ["ingredient", "drug_class", "subclass"]
    ].drop_duplicates()
    if len(ingredient_map) != whitelist["ingredient"].nunique():
        raise RuntimeError(
            "Frozen strict ingredients no longer map one-to-one to "
            "drug_class/subclass"
        )

    dictionary_exists = table_exists(con, "prescription_name_dictionary")
    map_exists = table_exists(con, "prescription_name_map")
    if not dictionary_exists:
        LOG("START full prescription distinct-name dictionary scan")
        con.execute(
            f"""
            CREATE OR REPLACE TABLE prescription_name_dictionary AS
            SELECT
              {raw_name_text} AS name_key,
              count(*)::BIGINT AS source_rows_n
            FROM {prescriptions} p
            GROUP BY {raw_name_text}
            """
        )
        dictionary_keys_n = scalar(
            con, "SELECT count(*) FROM prescription_name_dictionary"
        )
        LOG(
            "DONE prescription distinct-name dictionary "
            f"keys={dictionary_keys_n}"
        )
    else:
        dictionary_keys_n = scalar(
            con, "SELECT count(*) FROM prescription_name_dictionary"
        )
        LOG(
            "RESUME prescription distinct-name dictionary "
            f"keys={dictionary_keys_n}"
        )
    if not map_exists:
        con.execute(
            f"""
            CREATE OR REPLACE TABLE prescription_name_map AS
            SELECT
              d.*,
              {dictionary_ingredient_case}
            FROM prescription_name_dictionary d
            """
        )
    map_keys_n = scalar(con, "SELECT count(*) FROM prescription_name_map")
    matched_keys_n = scalar(
        con,
        "SELECT count(*) FROM prescription_name_map "
        "WHERE direct_ingredient IS NOT NULL",
    )
    LOG(
        "PRESCRIPTION exact frozen name map "
        f"keys={map_keys_n} matched_keys={matched_keys_n}"
    )

    if table_exists(con, "prescription_prefilter"):
        prefilter_rows = scalar(
            con, "SELECT count(*) FROM prescription_prefilter"
        )
    else:
        prefilter_rows = 0
    if prefilter_rows > 0:
        LOG(f"RESUME lossless prescription prefilter rows={prefilter_rows}")
    else:
        LOG("START exact-name/native-identity prescription prefilter")
        con.execute(
            f"""
            CREATE OR REPLACE TABLE prescription_prefilter AS
            WITH pharmacy_id_keys AS (
              SELECT DISTINCT
                subject_id, hadm_id, pharmacy_id
              FROM pharmacy_name_candidates
              WHERE pharmacy_id IS NOT NULL AND trim(pharmacy_id) <> ''
            ),
            pharmacy_poe_keys AS (
              SELECT DISTINCT
                subject_id, hadm_id, poe_id
              FROM pharmacy_name_candidates
              WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
            )
            SELECT
              TRY_CAST(p.subject_id AS BIGINT) AS subject_id,
              TRY_CAST(p.hadm_id AS BIGINT) AS hadm_id,
              p.pharmacy_id,
              p.poe_id,
              TRY_CAST(p.poe_seq AS BIGINT) AS poe_seq,
              TRY_CAST(p.starttime AS TIMESTAMP) AS starttime,
              TRY_CAST(p.stoptime AS TIMESTAMP) AS stoptime,
              p.drug_type,
              p.drug,
              p.formulary_drug_cd,
              p.gsn,
              p.ndc,
              p.prod_strength,
              p.dose_val_rx,
              p.dose_unit_rx,
              p.doses_per_24_hrs,
              p.route,
              nm.direct_ingredient
            FROM {prescriptions} p
            LEFT JOIN prescription_name_map nm
              ON {raw_name_text} = nm.name_key
            LEFT JOIN pharmacy_id_keys phi
              ON TRY_CAST(p.subject_id AS BIGINT) = phi.subject_id
             AND TRY_CAST(p.hadm_id AS BIGINT) = phi.hadm_id
             AND p.pharmacy_id IS NOT NULL
             AND trim(p.pharmacy_id) <> ''
             AND p.pharmacy_id = phi.pharmacy_id
            LEFT JOIN pharmacy_poe_keys php
              ON TRY_CAST(p.subject_id AS BIGINT) = php.subject_id
             AND TRY_CAST(p.hadm_id AS BIGINT) = php.hadm_id
             AND (p.pharmacy_id IS NULL OR trim(p.pharmacy_id) = '')
             AND p.poe_id IS NOT NULL
             AND trim(p.poe_id) <> ''
             AND p.poe_id = php.poe_id
            WHERE nm.direct_ingredient IS NOT NULL
               OR phi.pharmacy_id IS NOT NULL
               OR php.poe_id IS NOT NULL
            """
        )
        prefilter_rows = scalar(
            con, "SELECT count(*) FROM prescription_prefilter"
        )
        LOG(f"DONE lossless prescription prefilter rows={prefilter_rows}")

    class_from_ingredient = ["CASE r.direct_ingredient"]
    subclass_from_ingredient = ["CASE r.direct_ingredient"]
    for row in ingredient_map.itertuples(index=False):
        class_from_ingredient.append(
            f"WHEN {sql_quote(row.ingredient)} "
            f"THEN {sql_quote(row.drug_class)}"
        )
        subclass_from_ingredient.append(
            f"WHEN {sql_quote(row.ingredient)} "
            f"THEN {sql_quote(row.subclass)}"
        )
    class_from_ingredient.append("END AS direct_drug_class")
    subclass_from_ingredient.append("END AS direct_subclass")
    class_from_ingredient_sql = "\n".join(class_from_ingredient)
    subclass_from_ingredient_sql = "\n".join(subclass_from_ingredient)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE prescription_candidates AS
        WITH raw AS (
          SELECT p.*
          FROM prescription_prefilter p
        ),
        direct AS (
          SELECT
            r.*,
            {class_from_ingredient_sql},
            {subclass_from_ingredient_sql},
            r.direct_ingredient IS NOT NULL AS direct_name_match
          FROM raw r
        ),
        pharmacy_by_id AS (
          SELECT
            subject_id, hadm_id, pharmacy_id,
            arg_min(
              drug_class,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS drug_class,
            arg_min(
              ingredient,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS ingredient,
            arg_min(
              subclass,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS subclass,
            arg_min(
              pharmacy_medication,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            )
              AS pharmacy_medication,
            arg_min(
              pharmacy_route,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS pharmacy_route,
            arg_min(
              pharmacy_status,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS pharmacy_status
          FROM pharmacy_name_candidates
          WHERE pharmacy_id IS NOT NULL AND trim(pharmacy_id) <> ''
          GROUP BY subject_id, hadm_id, pharmacy_id
        ),
        pharmacy_by_poe AS (
          SELECT
            subject_id, hadm_id, poe_id,
            arg_min(
              drug_class,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS drug_class,
            arg_min(
              ingredient,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS ingredient,
            arg_min(
              subclass,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS subclass,
            arg_min(
              pharmacy_medication,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS pharmacy_medication,
            arg_min(
              pharmacy_route,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS pharmacy_route,
            arg_min(
              pharmacy_status,
              coalesce(pharmacy_starttime, TIMESTAMP '9999-12-31')
            ) AS pharmacy_status
          FROM pharmacy_name_candidates
          WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
          GROUP BY subject_id, hadm_id, poe_id
        )
        SELECT
          d.* EXCLUDE (
            direct_drug_class, direct_ingredient, direct_subclass,
            direct_name_match
          ),
          coalesce(
            d.direct_drug_class, phi.drug_class, php.drug_class
          ) AS drug_class,
          coalesce(
            d.direct_ingredient, phi.ingredient, php.ingredient
          ) AS ingredient,
          coalesce(
            d.direct_subclass, phi.subclass, php.subclass
          ) AS subclass,
          coalesce(
            phi.pharmacy_medication, php.pharmacy_medication
          ) AS pharmacy_medication,
          coalesce(phi.pharmacy_route, php.pharmacy_route)
            AS pharmacy_route,
          coalesce(phi.pharmacy_status, php.pharmacy_status)
            AS pharmacy_status,
          CASE
            WHEN d.direct_name_match THEN 'prescriptions'
            ELSE 'pharmacy_recovery'
          END AS order_name_match_source,
          TRY_CAST(
            nullif(regexp_extract(
              coalesce(d.dose_val_rx, ''), '([0-9]+(?:[.][0-9]+)?)', 1
            ), '') AS DOUBLE
          ) AS parsed_dose
        FROM direct d
        LEFT JOIN pharmacy_by_id phi
          ON d.subject_id = phi.subject_id
         AND d.hadm_id = phi.hadm_id
         AND d.pharmacy_id IS NOT NULL
         AND trim(d.pharmacy_id) <> ''
         AND d.pharmacy_id = phi.pharmacy_id
        LEFT JOIN pharmacy_by_poe php
          ON d.subject_id = php.subject_id
         AND d.hadm_id = php.hadm_id
         AND (d.pharmacy_id IS NULL OR trim(d.pharmacy_id) = '')
         AND d.poe_id IS NOT NULL
         AND trim(d.poe_id) <> ''
         AND d.poe_id = php.poe_id
        WHERE d.direct_name_match
           OR phi.drug_class IS NOT NULL
           OR php.drug_class IS NOT NULL
        """
    )
    LOG(
        "DONE prescriptions scan "
        f"rows={scalar(con, 'SELECT count(*) FROM prescription_candidates')}"
    )


def build_order_clusters(con) -> None:
    if table_exists(con, "eligible_order_clusters"):
        rows = scalar(con, "SELECT count(*) FROM eligible_order_clusters")
        if rows > 0:
            LOG(f"RESUME eligible order clusters rows={rows}")
            return
    LOG("START native-identity order assignment and clustering")
    con.execute(
        """
        CREATE OR REPLACE TABLE assigned_order_rows AS
        WITH identity AS (
          SELECT
            p.*,
            i.first_ordertime AS ordertime,
            i.subject_id AS poe_subject_id,
            i.hadm_id AS poe_hadm_id,
            i.poe_id IS NOT NULL AS poe_any_link,
            (
              i.poe_id IS NOT NULL
              AND i.subject_id = p.subject_id
              AND (
                i.hadm_id = p.hadm_id
                OR (i.hadm_id IS NULL AND p.hadm_id IS NULL)
              )
            ) AS poe_identity_link
          FROM prescription_candidates p
          LEFT JOIN poe_identity i ON p.poe_id = i.poe_id
          WHERE p.drug_class IS NOT NULL
        ),
        candidate_stays AS (
          SELECT
            i.*,
            s.stay_id, s.intime, s.outtime,
            s.subject_stay_order, s.hadm_stay_order,
            row_number() OVER (
              PARTITION BY
                i.subject_id, i.hadm_id, i.poe_id, i.pharmacy_id,
                i.drug_class, i.starttime, i.stoptime, i.drug
              ORDER BY
                CASE
                  WHEN i.ordertime BETWEEN s.intime AND s.outtime
                    THEN 0 ELSE 1
                END,
                s.intime, s.stay_id
            ) AS stay_assignment_rank
          FROM identity i
          JOIN adult_stays s
            ON i.subject_id = s.subject_id
           AND i.hadm_id = s.hadm_id
           AND i.ordertime BETWEEN
               s.intime - INTERVAL 6 HOUR AND s.outtime
           AND coalesce(i.starttime, i.ordertime) <= s.outtime
           AND coalesce(i.stoptime, s.outtime) >= s.intime
        )
        SELECT *
        FROM candidate_stays
        WHERE stay_assignment_rank = 1
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE order_clusters_all AS
        SELECT
          subject_id, hadm_id, stay_id, drug_class, poe_id,
          min(ordertime) AS ordertime,
          min(starttime) AS prescription_starttime,
          max(stoptime) AS prescription_stoptime,
          arg_min(drug, coalesce(starttime, ordertime)) AS drug,
          arg_min(ingredient, coalesce(starttime, ordertime)) AS ingredient,
          arg_min(subclass, coalesce(starttime, ordertime)) AS subclass,
          arg_min(route, coalesce(starttime, ordertime)) AS route,
          arg_min(dose_val_rx, coalesce(starttime, ordertime))
            AS dose_val_rx,
          arg_min(dose_unit_rx, coalesce(starttime, ordertime))
            AS dose_unit_rx,
          arg_min(parsed_dose, coalesce(starttime, ordertime))
            AS parsed_dose,
          arg_min(doses_per_24_hrs, coalesce(starttime, ordertime))
            AS doses_per_24_hrs,
          bool_or(poe_any_link) AS poe_any_link,
          bool_or(poe_identity_link) AS poe_identity_link,
          count(*) AS prescription_rows_n
        FROM assigned_order_rows
        WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
        GROUP BY subject_id, hadm_id, stay_id, drug_class, poe_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE eligible_order_clusters AS
        SELECT
          o.*,
          s.intime,
          s.outtime,
          CASE
            WHEN o.drug_class <> 'vte_prophylaxis' THEN TRUE
            WHEN lower(coalesce(o.route, '')) SIMILAR TO
              '%(sc|sq|subcut)%'
             AND (
               (
                 o.ingredient = 'heparin'
                 AND o.parsed_dose IN (5000, 7500)
               )
               OR (
                 o.ingredient = 'enoxaparin'
                 AND o.parsed_dose BETWEEN 20 AND 60
               )
             )
            THEN TRUE
            ELSE FALSE
          END AS route_dose_eligible
        FROM order_clusters_all o
        JOIN adult_stays s USING (subject_id, hadm_id, stay_id)
        WHERE o.poe_identity_link
          AND (
            o.drug_class <> 'vte_prophylaxis'
            OR (
              lower(coalesce(o.route, '')) SIMILAR TO
                '%(sc|sq|subcut)%'
              AND (
                (
                  o.ingredient = 'heparin'
                  AND o.parsed_dose IN (5000, 7500)
                )
                OR (
                  o.ingredient = 'enoxaparin'
                  AND o.parsed_dose BETWEEN 20 AND 60
                )
              )
            )
          )
        """
    )
    LOG(
        "DONE order clusters "
        f"all={scalar(con, 'SELECT count(*) FROM order_clusters_all')} "
        "eligible="
        f"{scalar(con, 'SELECT count(*) FROM eligible_order_clusters')}"
    )


def build_emar_stay_events(con) -> None:
    if table_exists(con, "emar_stay_events"):
        rows = scalar(con, "SELECT count(*) FROM emar_stay_events")
        if rows > 0:
            LOG(f"RESUME eMAR stay events rows={rows}")
            return
    LOG("START assign frozen eMAR events to ICU stays")
    con.execute(
        """
        CREATE OR REPLACE TABLE emar_stay_events AS
        SELECT * EXCLUDE (stay_assignment_rank)
        FROM (
          SELECT
            e.*,
            s.stay_id, s.intime, s.outtime,
            s.first_careunit, s.anchor_era,
            row_number() OVER (
              PARTITION BY e.emar_id, e.emar_seq, e.drug_class
              ORDER BY s.intime, s.stay_id
            ) AS stay_assignment_rank
          FROM emar_medication_events e
          JOIN adult_stays s
            ON e.subject_id = s.subject_id
           AND e.hadm_id = s.hadm_id
           AND e.charttime BETWEEN s.intime AND s.outtime
        )
        WHERE stay_assignment_rank = 1
        """
    )
    LOG(
        "DONE eMAR stay assignment "
        f"rows={scalar(con, 'SELECT count(*) FROM emar_stay_events')}"
    )


def build_conversion(con) -> None:
    LOG("START linked order-to-administration conversion")
    con.execute(
        """
        CREATE OR REPLACE TABLE order_conversion AS
        SELECT
          o.*,
          min(e.charttime) FILTER (
            WHERE e.event_category = 'given_strict'
              AND (
                o.drug_class <> 'vte_prophylaxis'
                OR lower(coalesce(e.route, '')) SIMILAR TO
                   '%(sc|sq|subcut)%'
              )
          ) AS first_administration_time,
          count(*) FILTER (
            WHERE e.event_category = 'given_strict'
              AND (
                o.drug_class <> 'vte_prophylaxis'
                OR lower(coalesce(e.route, '')) SIMILAR TO
                   '%(sc|sq|subcut)%'
              )
          ) AS linked_given_events_n,
          count(*) FILTER (
            WHERE e.event_category = 'not_given'
          ) AS linked_not_given_events_n
        FROM eligible_order_clusters o
        LEFT JOIN emar_stay_events e
          ON o.subject_id = e.subject_id
         AND o.hadm_id = e.hadm_id
         AND o.stay_id = e.stay_id
         AND o.drug_class = e.drug_class
         AND o.poe_id = e.poe_id
         AND e.charttime BETWEEN
             o.ordertime - INTERVAL 2 HOUR
             AND least(
               coalesce(
                 o.prescription_stoptime + INTERVAL 6 HOUR,
                 o.outtime
               ),
               o.outtime
             )
        GROUP BY ALL
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE order_conversion_complete AS
        SELECT
          *,
          first_administration_time IS NOT NULL AS converted,
          date_diff(
            'second', ordertime, first_administration_time
          ) / 3600.0 AS first_dose_lag_hours,
          CASE
            WHEN first_administration_time IS NULL THEN 'not_converted'
            WHEN first_administration_time < ordertime
              THEN 'negative_minus2_to_0'
            WHEN first_administration_time
                 <= ordertime + INTERVAL 24 HOUR
              THEN '0_to_24h'
            WHEN first_administration_time
                 <= ordertime + INTERVAL 7 DAY
              THEN '24h_to_7d'
            ELSE 'over_7d'
          END AS lag_audit_category
        FROM order_conversion
        """
    )
    LOG(
        "DONE order conversion "
        f"rows={scalar(con, 'SELECT count(*) FROM order_conversion_complete')}"
    )


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return math.nan, math.nan
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = (
        z
        * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
        / denominator
    )
    return center - half, center + half


def summarize_primary(con) -> dict[str, object]:
    LOG("START primary estimand summaries")
    conversion = qdf(
        con,
        """
        SELECT
          drug_class,
          count(*) AS eligible_orders_n,
          sum(converted::INTEGER) AS converted_orders_n,
          100.0 * avg(converted::INTEGER) AS conversion_pct,
          sum((lag_audit_category = 'negative_minus2_to_0')::INTEGER)
            AS negative_lag_n,
          sum((lag_audit_category = '0_to_24h')::INTEGER)
            AS lag_0_24h_n,
          sum((lag_audit_category = '24h_to_7d')::INTEGER)
            AS lag_24h_7d_n,
          sum((lag_audit_category = 'over_7d')::INTEGER)
            AS lag_over_7d_n,
          sum((lag_audit_category = 'not_converted')::INTEGER)
            AS not_converted_n
        FROM order_conversion_complete
        GROUP BY drug_class
        ORDER BY drug_class
        """,
    )
    all_classes = pd.DataFrame(
        {
            "drug_class": [
                "stress_ulcer_prophylaxis",
                "vte_prophylaxis",
                "intra_abdominal_antibiotics",
                "electrolyte_replacement",
                "prokinetic",
                "insulin",
            ]
        }
    )
    conversion = all_classes.merge(conversion, on="drug_class", how="left")
    for column in (
        "eligible_orders_n",
        "converted_orders_n",
        "negative_lag_n",
        "lag_0_24h_n",
        "lag_24h_7d_n",
        "lag_over_7d_n",
        "not_converted_n",
    ):
        conversion[column] = conversion[column].fillna(0).astype("int64")
    intervals = [
        wilson_interval(int(row.converted_orders_n), int(row.eligible_orders_n))
        for row in conversion.itertuples(index=False)
    ]
    conversion["conversion_ci_low_pct"] = [100 * x[0] for x in intervals]
    conversion["conversion_ci_high_pct"] = [100 * x[1] for x in intervals]
    conversion["count_status"] = conversion["eligible_orders_n"].map(
        lambda n: "primary_estimation" if n >= 500 else "descriptive_only"
    )
    write_csv(conversion, TABLES / "order_to_administration_conversion.csv")

    lag = qdf(
        con,
        """
        SELECT
          drug_class,
          count(*) AS converted_nonnegative_le7d_n,
          quantile_cont(first_dose_lag_hours, 0.10) AS p10_hours,
          quantile_cont(first_dose_lag_hours, 0.25) AS p25_hours,
          median(first_dose_lag_hours) AS median_hours,
          quantile_cont(first_dose_lag_hours, 0.75) AS p75_hours,
          quantile_cont(first_dose_lag_hours, 0.90) AS p90_hours,
          quantile_cont(first_dose_lag_hours, 0.95) AS p95_hours,
          avg((first_dose_lag_hours > 24)::INTEGER) * 100
            AS over_24h_pct
        FROM order_conversion_complete
        WHERE converted
          AND first_dose_lag_hours >= 0
          AND first_dose_lag_hours <= 24 * 7
        GROUP BY drug_class
        ORDER BY drug_class
        """,
    )
    write_csv(lag, TABLES / "first_dose_lag_distribution.csv")

    lag_audit = qdf(
        con,
        """
        SELECT
          drug_class,
          lag_audit_category,
          count(*) AS orders_n,
          min(first_dose_lag_hours) AS min_lag_hours,
          max(first_dose_lag_hours) AS max_lag_hours
        FROM order_conversion_complete
        GROUP BY drug_class, lag_audit_category
        ORDER BY drug_class, lag_audit_category
        """,
    )
    write_csv(lag_audit, TABLES / "first_dose_lag_audit.csv")

    order_link = qdf(
        con,
        """
        SELECT
          drug_class,
          count(*) AS prescription_candidate_rows_n,
          sum((poe_id IS NOT NULL AND trim(poe_id) <> '')::INTEGER)
            AS poe_id_nonmissing_n,
          sum(poe_any_link::INTEGER) AS poe_any_link_n,
          sum(poe_identity_link::INTEGER) AS poe_identity_link_n,
          100.0 * avg((
            poe_id IS NOT NULL AND trim(poe_id) <> ''
          )::INTEGER) AS poe_id_nonmissing_pct,
          100.0 * sum(poe_identity_link::INTEGER)
            / nullif(sum((
              poe_id IS NOT NULL AND trim(poe_id) <> ''
            )::INTEGER), 0) AS identity_link_among_nonmissing_pct
        FROM assigned_order_rows
        GROUP BY drug_class
        ORDER BY drug_class
        """,
    )
    write_csv(order_link, TABLES / "order_poe_link_by_class.csv")

    detail_denominator = qdf(
        con,
        """
        SELECT
          drug_class,
          count(*) AS assigned_events_n,
          sum((event_category = 'given_strict')::INTEGER) AS given_n,
          sum((event_category = 'not_given')::INTEGER) AS not_given_n,
          sum((event_category = 'flushed')::INTEGER) AS flushed_n,
          sum((event_category = 'confirmed')::INTEGER) AS confirmed_n,
          sum((event_category = 'blank')::INTEGER) AS blank_n,
          sum((event_category = 'other_excluded')::INTEGER)
            AS other_excluded_n,
          100.0 * sum((event_category = 'not_given')::INTEGER)
            / nullif(sum((
              event_category IN ('given_strict', 'not_given')
            )::INTEGER), 0) AS not_given_pct
        FROM emar_stay_events
        GROUP BY drug_class
        ORDER BY drug_class
        """,
    )
    write_csv(
        detail_denominator,
        TABLES / "not_given_proportion_by_class_unadjusted.csv",
    )

    summary = {
        "adult_stays_n": scalar(con, "SELECT count(*) FROM adult_stays"),
        "prescription_candidate_rows_n": scalar(
            con, "SELECT count(*) FROM prescription_candidates"
        ),
        "eligible_order_clusters_n": scalar(
            con, "SELECT count(*) FROM eligible_order_clusters"
        ),
        "converted_order_clusters_n": scalar(
            con,
            "SELECT count(*) FROM order_conversion_complete WHERE converted",
        ),
        "six_classes_retained": bool(len(conversion) == 6),
        "all_conversion_gt97": bool(
            conversion["conversion_pct"].notna().all()
            and (conversion["conversion_pct"] > 97).all()
        ),
    }
    LOG(f"DONE primary summaries {summary}")
    return summary


def render_report(summary: dict[str, object]) -> str:
    conversion = pd.read_csv(
        TABLES / "order_to_administration_conversion.csv"
    )
    lag = pd.read_csv(TABLES / "first_dose_lag_distribution.csv")
    not_given = pd.read_csv(
        TABLES / "not_given_proportion_by_class_unadjusted.csv"
    )
    link = pd.read_csv(TABLES / "order_poe_link_by_class.csv")
    return "\n".join(
        [
            "# 02 — Six-class order-to-administration primary estimands",
            "",
            "All six classes use the pre-result frozen strict whitelist. Low",
            "counts are labeled; no class is selected or removed.",
            "",
            "## Order-to-administration conversion",
            "",
            "```text",
            conversion.to_string(index=False),
            "```",
            "",
            "## First-dose lag",
            "",
            "Negative documentation-timing anomalies and lags over seven days",
            "are retained in the audit table but excluded from the inferential",
            "lag distribution.",
            "",
            "```text",
            lag.to_string(index=False),
            "```",
            "",
            "## Held/not-given crude proportions",
            "",
            "Flushed, Confirmed, blank, and other event text remain outside the",
            "decision denominator.",
            "",
            "```text",
            not_given.to_string(index=False),
            "```",
            "",
            "## Order POE-link coverage",
            "",
            "```text",
            link.to_string(index=False),
            "```",
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
    whitelist = load_whitelist("strict")
    if whitelist["drug_class"].nunique() != 6:
        raise RuntimeError("Frozen strict whitelist no longer has six classes")

    con = connect_duckdb()
    if not table_exists(con, "emar_medication_events"):
        raise RuntimeError(
            "Mandatory audit table emar_medication_events is absent; "
            "run 01_full_interface_audit.py first"
        )
    build_adult_stays(con)
    build_pharmacy_candidates(con, whitelist)
    build_prescription_candidates(con, whitelist)
    build_order_clusters(con)
    build_emar_stay_events(con)
    build_conversion(con)
    summary = summarize_primary(con)
    con.close()

    (REPORTS / "02_primary_estimands.md").write_text(
        render_report(summary), encoding="utf-8"
    )
    metadata = script_metadata(started, SCRIPT)
    metadata.update(summary)
    write_json(metadata, MANIFESTS / "02_build_primary_estimands.json")
    LOG(f"DONE primary estimands elapsed={metadata['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
