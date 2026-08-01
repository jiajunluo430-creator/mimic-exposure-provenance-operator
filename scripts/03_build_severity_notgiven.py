from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from common import (
    CACHE,
    MANIFESTS,
    MIMIC_ROOT,
    OUTPUTS,
    REPORTS,
    TABLES,
    RunLogger,
    connect_duckdb,
    ensure_dirs,
    script_metadata,
    sql_path,
    sql_quote,
    verify_frozen_contract,
    verify_semantic_addendum,
    write_csv,
    write_json,
)


SCRIPT = Path(__file__).resolve()
LOG = RunLogger("03_build_severity_notgiven")
AUDIT = OUTPUTS / "audit"
FORBIDDEN_PLAN_OPERATORS = (
    "BLOCKWISE_NL_JOIN",
    "NESTED_LOOP_JOIN",
    "CROSS_PRODUCT",
)


CSV_COLUMNS = {
    "chartevents": [
        "subject_id",
        "hadm_id",
        "stay_id",
        "caregiver_id",
        "charttime",
        "storetime",
        "itemid",
        "value",
        "valuenum",
        "valueuom",
        "warning",
    ],
    "procedureevents": [
        "subject_id",
        "hadm_id",
        "stay_id",
        "caregiver_id",
        "starttime",
        "endtime",
        "storetime",
        "itemid",
        "value",
        "valueuom",
        "location",
        "locationcategory",
        "orderid",
        "linkorderid",
        "ordercategoryname",
        "ordercategorydescription",
        "patientweight",
        "isopenbag",
        "continueinnextdept",
        "statusdescription",
        "originalamount",
        "originalrate",
    ],
    "inputevents": [
        "subject_id",
        "hadm_id",
        "stay_id",
        "caregiver_id",
        "starttime",
        "endtime",
        "storetime",
        "itemid",
        "amount",
        "amountuom",
        "rate",
        "rateuom",
        "orderid",
        "linkorderid",
        "ordercategoryname",
        "secondaryordercategoryname",
        "ordercomponenttypedescription",
        "ordercategorydescription",
        "patientweight",
        "totalamount",
        "totalamountuom",
        "isopenbag",
        "continueinnextdept",
        "statusdescription",
        "originalamount",
        "originalrate",
    ],
    "outputevents": [
        "subject_id",
        "hadm_id",
        "stay_id",
        "caregiver_id",
        "charttime",
        "storetime",
        "itemid",
        "value",
        "valueuom",
    ],
    "services": [
        "subject_id",
        "hadm_id",
        "transfertime",
        "prev_service",
        "curr_service",
    ],
}


def fixed_varchar_scan(relative_path: str, schema_name: str) -> str:
    columns = CSV_COLUMNS[schema_name]
    schema = ", ".join(
        f"{sql_quote(column)}: 'VARCHAR'" for column in columns
    )
    path = MIMIC_ROOT / relative_path
    return (
        f"read_csv('{sql_path(path)}', header=true, "
        f"auto_detect=false, columns={{{schema}}}, "
        "ignore_errors=false, strict_mode=true, null_padding=false)"
    )


def qdf(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def explain_guard(
    con,
    *,
    step: str,
    select_sql: str,
    analyze: bool = False,
) -> str:
    mode = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
    rows = con.execute(f"{mode} {select_sql}").fetchall()
    plan = "\n".join(
        f"{row[0]}\n{row[1]}" if len(row) > 1 else str(row[0])
        for row in rows
    )
    AUDIT.mkdir(parents=True, exist_ok=True)
    suffix = "analyze" if analyze else "plan"
    (AUDIT / f"03_{step}_{suffix}.txt").write_text(
        plan, encoding="utf-8"
    )
    forbidden = [
        operator
        for operator in FORBIDDEN_PLAN_OPERATORS
        if operator in plan
    ]
    LOG(
        f"{mode} step={step} forbidden={forbidden or 'none'}"
    )
    if forbidden:
        raise RuntimeError(
            f"Unsafe Stage 03 plan for {step}: {forbidden}"
        )
    return plan


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


def build_oasis_chart_raw(con) -> None:
    if table_exists(con, "oasis_chart_raw"):
        rows = scalar(con, "SELECT count(*) FROM oasis_chart_raw")
        if rows > 0:
            LOG(f"RESUME OASIS chart subset rows={rows}")
            return
    LOG("START full chartevents scan for frozen OASIS item set")
    chartevents = fixed_varchar_scan(
        "icu/chartevents.csv.gz", "chartevents"
    )
    itemids = (
        "220045, 220052, 220181, 225312, 220210, 224690, "
        "223761, 223762, 223900, 223901, 220739, "
        "223849, 229314, 226732"
    )
    select_sql = f"""
        SELECT
          TRY_CAST(ce.subject_id AS BIGINT) AS subject_id,
          TRY_CAST(ce.hadm_id AS BIGINT) AS hadm_id,
          TRY_CAST(ce.stay_id AS BIGINT) AS stay_id,
          TRY_CAST(ce.charttime AS TIMESTAMP) AS charttime,
          TRY_CAST(ce.storetime AS TIMESTAMP) AS storetime,
          TRY_CAST(ce.itemid AS BIGINT) AS itemid,
          ce.value,
          TRY_CAST(ce.valuenum AS DOUBLE) AS valuenum,
          ce.valueuom,
          s.intime
        FROM {chartevents} ce
        JOIN adult_stays s
          ON TRY_CAST(ce.stay_id AS BIGINT) = s.stay_id
         AND TRY_CAST(ce.charttime AS TIMESTAMP)
             BETWEEN s.intime - INTERVAL 6 HOUR
             AND s.outtime
        WHERE TRY_CAST(ce.itemid AS BIGINT) IN ({itemids})
    """
    explain_guard(
        con,
        step="oasis_chart_projection",
        select_sql=select_sql,
    )
    limited_source = f"(SELECT * FROM {chartevents} LIMIT 1000000)"
    limited_select_sql = select_sql.replace(
        f"FROM {chartevents} ce",
        f"FROM {limited_source} ce",
        1,
    )
    explain_guard(
        con,
        step="oasis_chart_projection_limited",
        select_sql=f"{limited_select_sql} LIMIT 10000",
        analyze=True,
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE oasis_chart_raw AS
        {select_sql}
        """
    )
    LOG(
        "DONE OASIS chartevents subset "
        f"rows={scalar(con, 'SELECT count(*) FROM oasis_chart_raw')}"
    )


def build_first_day_vitals_gcs(con) -> None:
    LOG("START first-day vital-sign and GCS components")
    con.execute(
        """
        CREATE OR REPLACE TABLE first_day_vitals AS
        SELECT
          stay_id,
          min(valuenum) FILTER (
            WHERE itemid = 220045 AND valuenum > 0 AND valuenum < 300
          ) AS heart_rate_min,
          max(valuenum) FILTER (
            WHERE itemid = 220045 AND valuenum > 0 AND valuenum < 300
          ) AS heart_rate_max,
          min(valuenum) FILTER (
            WHERE itemid IN (220052, 220181, 225312)
              AND valuenum > 0 AND valuenum < 300
          ) AS mbp_min,
          max(valuenum) FILTER (
            WHERE itemid IN (220052, 220181, 225312)
              AND valuenum > 0 AND valuenum < 300
          ) AS mbp_max,
          min(valuenum) FILTER (
            WHERE itemid IN (220210, 224690)
              AND valuenum > 0 AND valuenum < 70
          ) AS resp_rate_min,
          max(valuenum) FILTER (
            WHERE itemid IN (220210, 224690)
              AND valuenum > 0 AND valuenum < 70
          ) AS resp_rate_max,
          min(
            CASE
              WHEN itemid = 223761
                AND valuenum > 70 AND valuenum < 120
                THEN (valuenum - 32) / 1.8
              WHEN itemid = 223762
                AND valuenum > 10 AND valuenum < 50
                THEN valuenum
            END
          ) AS temperature_min,
          max(
            CASE
              WHEN itemid = 223761
                AND valuenum > 70 AND valuenum < 120
                THEN (valuenum - 32) / 1.8
              WHEN itemid = 223762
                AND valuenum > 10 AND valuenum < 50
                THEN valuenum
            END
          ) AS temperature_max
        FROM oasis_chart_raw
        WHERE charttime <= intime + INTERVAL 24 HOUR
        GROUP BY stay_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE gcs_base AS
        SELECT
          subject_id, stay_id, charttime,
          max(valuenum) FILTER (WHERE itemid = 223901) AS gcsmotor,
          max(
            CASE
              WHEN itemid = 223900 AND value = 'No Response-ETT' THEN 0
              WHEN itemid = 223900 THEN valuenum
            END
          ) AS gcsverbal,
          max(valuenum) FILTER (WHERE itemid = 220739) AS gcseyes,
          row_number() OVER (
            PARTITION BY stay_id ORDER BY charttime
          ) AS rn
        FROM oasis_chart_raw
        WHERE itemid IN (223900, 223901, 220739)
          AND charttime <= intime + INTERVAL 24 HOUR
        GROUP BY subject_id, stay_id, charttime
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE first_day_gcs AS
        WITH scored AS (
          SELECT
            b.subject_id, b.stay_id, b.charttime,
            CASE
              WHEN b.gcsverbal = 0 THEN 15
              WHEN b.gcsverbal IS NULL AND b2.gcsverbal = 0 THEN 15
              WHEN b2.gcsverbal = 0 THEN
                coalesce(b.gcsmotor, 6)
                + coalesce(b.gcsverbal, 5)
                + coalesce(b.gcseyes, 4)
              ELSE
                coalesce(b.gcsmotor, b2.gcsmotor, 6)
                + coalesce(b.gcsverbal, b2.gcsverbal, 5)
                + coalesce(b.gcseyes, b2.gcseyes, 4)
            END AS gcs
          FROM gcs_base b
          LEFT JOIN gcs_base b2
            ON b.stay_id = b2.stay_id
           AND b.rn = b2.rn + 1
           AND b2.charttime > b.charttime - INTERVAL 6 HOUR
        )
        SELECT stay_id, min(gcs) AS gcs_min
        FROM scored
        GROUP BY stay_id
        """
    )
    LOG("DONE first-day vital-sign and GCS components")


def build_official_ventilation(con) -> None:
    if table_exists(con, "official_ventilation_intervals"):
        rows = scalar(con, "SELECT count(*) FROM official_ventilation_intervals")
        if rows > 0:
            LOG(f"RESUME official ventilation intervals rows={rows}")
            return
    LOG("START official MIMIC ventilation status/interval derivation")
    con.execute(
        """
        CREATE OR REPLACE TABLE ventilation_status_points AS
        WITH ventilator_setting AS (
          SELECT
            stay_id, charttime,
            max(value) FILTER (WHERE itemid = 223849)
              AS ventilator_mode,
            max(value) FILTER (WHERE itemid = 229314)
              AS ventilator_mode_hamilton
          FROM oasis_chart_raw
          WHERE itemid IN (223849, 229314)
            AND value IS NOT NULL
          GROUP BY stay_id, charttime
        ),
        oxygen_ranked AS (
          SELECT
            stay_id, charttime, value AS o2_device,
            row_number() OVER (
              PARTITION BY stay_id, charttime
              ORDER BY storetime DESC NULLS LAST,
                       value DESC NULLS LAST
            ) AS rn
          FROM oasis_chart_raw
          WHERE itemid = 226732
            AND value IS NOT NULL
        ),
        oxygen_delivery AS (
          SELECT
            stay_id, charttime,
            max(o2_device) FILTER (WHERE rn = 1)
              AS o2_delivery_device_1,
            max(o2_device) FILTER (WHERE rn = 2)
              AS o2_delivery_device_2,
            max(o2_device) FILTER (WHERE rn = 3)
              AS o2_delivery_device_3,
            max(o2_device) FILTER (WHERE rn = 4)
              AS o2_delivery_device_4
          FROM oxygen_ranked
          GROUP BY stay_id, charttime
        ),
        tm AS (
          SELECT stay_id, charttime FROM ventilator_setting
          UNION
          SELECT stay_id, charttime FROM oxygen_delivery
        ),
        joined AS (
          SELECT
            tm.stay_id, tm.charttime,
            od.o2_delivery_device_1,
            od.o2_delivery_device_2,
            od.o2_delivery_device_3,
            od.o2_delivery_device_4,
            vs.ventilator_mode,
            vs.ventilator_mode_hamilton,
            coalesce(
              vs.ventilator_mode, vs.ventilator_mode_hamilton
            ) AS vent_mode
          FROM tm
          LEFT JOIN ventilator_setting vs
            ON tm.stay_id = vs.stay_id
           AND tm.charttime = vs.charttime
          LEFT JOIN oxygen_delivery od
            ON tm.stay_id = od.stay_id
           AND tm.charttime = od.charttime
        )
        SELECT
          *,
          CASE
            WHEN lower(trim(coalesce(o2_delivery_device_1, '')))
                 IN ('tracheostomy tube', 'trach mask')
              THEN 'Tracheostomy'
            WHEN lower(trim(coalesce(o2_delivery_device_1, '')))
                 = 'endotracheal tube'
              OR vent_mode IN (
                '(S) CMV', 'APRV', 'APRV/Biphasic+ApnPress',
                'APRV/Biphasic+ApnVol', 'APV (cmv)', 'Ambient',
                'Apnea Ventilation', 'CMV', 'CMV/ASSIST',
                'CMV/ASSIST/AutoFlow', 'CMV/AutoFlow', 'CPAP/PPS',
                'CPAP/PSV', 'CPAP/PSV+Apn TCPL',
                'CPAP/PSV+ApnPres', 'CPAP/PSV+ApnVol', 'MMV',
                'MMV/AutoFlow', 'MMV/PSV', 'MMV/PSV/AutoFlow',
                'P-CMV', 'PCV+', 'PCV+/PSV', 'PCV+Assist',
                'PRES/AC', 'PRVC/AC', 'PRVC/SIMV', 'PSV/SBT',
                'SIMV', 'SIMV/AutoFlow', 'SIMV/PRES', 'SIMV/PSV',
                'SIMV/PSV/AutoFlow', 'SIMV/VOL', 'SYNCHRON MASTER',
                'SYNCHRON SLAVE', 'VOL/AC', 'APV (simv)', 'P-SIMV',
                'VS', 'ASV'
              )
              THEN 'InvasiveVent'
            WHEN (
              lower(trim(coalesce(o2_delivery_device_1, '')))
                IN ('bipap mask', 'cpap mask')
              OR lower(trim(coalesce(o2_delivery_device_2, '')))
                IN ('bipap mask', 'cpap mask')
              OR lower(trim(coalesce(o2_delivery_device_3, '')))
                IN ('bipap mask', 'cpap mask')
              OR lower(trim(coalesce(o2_delivery_device_4, '')))
                IN ('bipap mask', 'cpap mask')
              OR ventilator_mode_hamilton IN ('DuoPaP', 'NIV', 'NIV-ST')
            )
              THEN 'NonInvasiveVent'
            WHEN lower(trim(coalesce(o2_delivery_device_1, '')))
                 = 'high flow nasal cannula'
              THEN 'HFNC'
            WHEN lower(trim(coalesce(o2_delivery_device_1, ''))) IN (
              'non-rebreather', 'face tent', 'aerosol-cool',
              'venti mask', 'medium conc mask', 'ultrasonic neb',
              'vapomist', 'oxymizer', 'high flow neb', 'nasal cannula'
            )
              THEN 'SupplementalOxygen'
            WHEN lower(trim(coalesce(o2_delivery_device_1, ''))) = 'none'
              THEN 'None'
          END AS ventilation_status
        FROM joined
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE official_ventilation_intervals AS
        WITH vd0 AS (
          SELECT
            stay_id, charttime,
            lag(charttime, 1) OVER (
              PARTITION BY stay_id, ventilation_status
              ORDER BY charttime
            ) AS charttime_lag,
            lead(charttime, 1) OVER (
              PARTITION BY stay_id ORDER BY charttime
            ) AS charttime_lead,
            ventilation_status,
            lag(ventilation_status, 1) OVER (
              PARTITION BY stay_id ORDER BY charttime
            ) AS ventilation_status_lag
          FROM ventilation_status_points
          WHERE ventilation_status IS NOT NULL
        ),
        vd1 AS (
          SELECT
            *,
            CASE
              WHEN ventilation_status_lag IS NULL THEN 1
              WHEN date_diff('hour', charttime_lag, charttime) >= 14
                THEN 1
              WHEN ventilation_status_lag <> ventilation_status THEN 1
              ELSE 0
            END AS new_ventilation_event
          FROM vd0
        ),
        vd2 AS (
          SELECT
            *,
            sum(new_ventilation_event) OVER (
              PARTITION BY stay_id ORDER BY charttime
            ) AS vent_seq
          FROM vd1
        )
        SELECT
          stay_id,
          min(charttime) AS starttime,
          max(
            CASE
              WHEN charttime_lead IS NULL
                OR date_diff('hour', charttime, charttime_lead) >= 14
                THEN charttime
              ELSE charttime_lead
            END
          ) AS endtime,
          max(ventilation_status) AS ventilation_status
        FROM vd2
        GROUP BY stay_id, vent_seq
        HAVING min(charttime) <> max(charttime)
        """
    )
    LOG(
        "DONE official ventilation derivation "
        f"points={scalar(con, 'SELECT count(*) FROM ventilation_status_points')} "
        "intervals="
        f"{scalar(con, 'SELECT count(*) FROM official_ventilation_intervals')}"
    )


def build_organ_support_intervals(con) -> None:
    if table_exists(con, "organ_support_intervals"):
        rows = scalar(con, "SELECT count(*) FROM organ_support_intervals")
        if rows > 0:
            LOG(f"RESUME organ-support intervals rows={rows}")
            return
    LOG("START procedure/inputevents organ-support scans")
    build_official_ventilation(con)
    procedures = fixed_varchar_scan(
        "icu/procedureevents.csv.gz", "procedureevents"
    )
    inputs = fixed_varchar_scan(
        "icu/inputevents.csv.gz", "inputevents"
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE organ_support_intervals AS
        SELECT
          stay_id,
          starttime,
          endtime,
          'invasive_ventilation' AS support_type,
          NULL::BIGINT AS itemid
        FROM official_ventilation_intervals
        WHERE ventilation_status = 'InvasiveVent'

        UNION ALL

        SELECT
          TRY_CAST(stay_id AS BIGINT) AS stay_id,
          TRY_CAST(starttime AS TIMESTAMP) AS starttime,
          TRY_CAST(endtime AS TIMESTAMP) AS endtime,
          'rrt' AS support_type,
          TRY_CAST(itemid AS BIGINT) AS itemid
        FROM {procedures}
        WHERE TRY_CAST(itemid AS BIGINT) IN (
          225802, 225803, 225809, 225955
        )
          AND TRY_CAST(starttime AS TIMESTAMP) IS NOT NULL
          AND TRY_CAST(endtime AS TIMESTAMP)
              >= TRY_CAST(starttime AS TIMESTAMP)
          AND lower(coalesce(statusdescription, '')) <> 'rewritten'

        UNION ALL

        SELECT
          TRY_CAST(stay_id AS BIGINT) AS stay_id,
          TRY_CAST(starttime AS TIMESTAMP) AS starttime,
          TRY_CAST(endtime AS TIMESTAMP) AS endtime,
          'vasopressor' AS support_type,
          TRY_CAST(itemid AS BIGINT) AS itemid
        FROM {inputs}
        WHERE TRY_CAST(itemid AS BIGINT) IN (
          221289, 221662, 221749, 221906, 222315,
          229617, 229630, 229631, 229632
        )
          AND TRY_CAST(starttime AS TIMESTAMP) IS NOT NULL
          AND TRY_CAST(endtime AS TIMESTAMP)
              >= TRY_CAST(starttime AS TIMESTAMP)
          AND (
            TRY_CAST(rate AS DOUBLE) > 0
            OR TRY_CAST(amount AS DOUBLE) > 0
          )
          AND lower(coalesce(statusdescription, '')) <> 'rewritten'
        """
    )
    LOG(
        "DONE organ-support intervals "
        f"rows={scalar(con, 'SELECT count(*) FROM organ_support_intervals')}"
    )


def build_first_day_urine(con) -> None:
    if table_exists(con, "first_day_urine"):
        rows = scalar(con, "SELECT count(*) FROM first_day_urine")
        if rows > 0:
            LOG(f"RESUME first-day urine rows={rows}")
            return
    LOG("START full outputevents scan for official urine-output items")
    outputevents = fixed_varchar_scan(
        "icu/outputevents.csv.gz", "outputevents"
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE first_day_urine AS
        SELECT
          s.stay_id,
          sum(
            CASE
              WHEN TRY_CAST(o.itemid AS BIGINT) = 227488
                AND TRY_CAST(o.value AS DOUBLE) > 0
                THEN -TRY_CAST(o.value AS DOUBLE)
              ELSE TRY_CAST(o.value AS DOUBLE)
            END
          ) AS urineoutput
        FROM {outputevents} o
        JOIN adult_stays s
          ON TRY_CAST(o.stay_id AS BIGINT) = s.stay_id
         AND TRY_CAST(o.charttime AS TIMESTAMP)
             BETWEEN s.intime AND s.intime + INTERVAL 24 HOUR
        WHERE TRY_CAST(o.itemid AS BIGINT) IN (
          226559, 226560, 226561, 226584, 226563, 226564,
          226565, 226567, 226557, 226558, 227488, 227489
        )
        GROUP BY s.stay_id
        """
    )
    LOG(
        "DONE first-day urine "
        f"rows={scalar(con, 'SELECT count(*) FROM first_day_urine')}"
    )


def build_oasis(con) -> None:
    LOG("START OASIS scoring with official v3.0.0 cutpoints")
    services = fixed_varchar_scan(
        "hosp/services.csv.gz", "services"
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE first_day_surgical_flag AS
        SELECT
          s.stay_id,
          max(
            CASE
              WHEN lower(coalesce(se.curr_service, '')) LIKE '%surg%'
                OR se.curr_service = 'ORTHO'
                THEN 1 ELSE 0
            END
          ) AS surgical
        FROM adult_stays s
        LEFT JOIN {services} se
          ON s.hadm_id = TRY_CAST(se.hadm_id AS BIGINT)
         AND TRY_CAST(se.transfertime AS TIMESTAMP)
             < s.intime + INTERVAL 24 HOUR
        GROUP BY s.stay_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE first_day_support AS
        SELECT
          s.stay_id,
          max((
            i.support_type = 'invasive_ventilation'
          )::INTEGER) AS mechvent,
          max((i.support_type = 'vasopressor')::INTEGER) AS vasopressor,
          max((i.support_type = 'rrt')::INTEGER) AS rrt
        FROM adult_stays s
        LEFT JOIN organ_support_intervals i
          ON s.stay_id = i.stay_id
         AND i.starttime <= s.intime + INTERVAL 24 HOUR
         AND i.endtime >= s.intime
        GROUP BY s.stay_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE oasis_components AS
        SELECT
          s.subject_id, s.hadm_id, s.stay_id,
          s.anchor_age + year(s.admittime) - s.anchor_year AS age,
          date_diff('second', s.admittime, s.intime) / 60.0 AS preiculos,
          g.gcs_min,
          v.heart_rate_min, v.heart_rate_max,
          v.mbp_min, v.mbp_max,
          v.resp_rate_min, v.resp_rate_max,
          v.temperature_min, v.temperature_max,
          u.urineoutput,
          coalesce(fs.mechvent, 0) AS mechvent,
          coalesce(fs.vasopressor, 0) AS first_day_vasopressor,
          coalesce(fs.rrt, 0) AS first_day_rrt,
          CASE
            WHEN upper(coalesce(s.admission_type, '')) = 'ELECTIVE'
              AND coalesce(sf.surgical, 0) = 1
              THEN 1 ELSE 0
          END AS electivesurgery
        FROM adult_stays s
        LEFT JOIN first_day_vitals v USING (stay_id)
        LEFT JOIN first_day_gcs g USING (stay_id)
        LEFT JOIN first_day_urine u USING (stay_id)
        LEFT JOIN first_day_support fs USING (stay_id)
        LEFT JOIN first_day_surgical_flag sf USING (stay_id)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE oasis_scores AS
        WITH components AS (
          SELECT
            *,
            CASE
              WHEN preiculos IS NULL THEN NULL
              WHEN preiculos < 10.2 THEN 5
              WHEN preiculos < 297 THEN 3
              WHEN preiculos < 1440 THEN 0
              WHEN preiculos < 18708 THEN 2
              ELSE 1
            END AS preiculos_score,
            CASE
              WHEN age IS NULL THEN NULL
              WHEN age < 24 THEN 0
              WHEN age <= 53 THEN 3
              WHEN age <= 77 THEN 6
              WHEN age <= 89 THEN 9
              WHEN age >= 90 THEN 7
              ELSE 0
            END AS age_score,
            CASE
              WHEN gcs_min IS NULL THEN NULL
              WHEN gcs_min <= 7 THEN 10
              WHEN gcs_min < 14 THEN 4
              WHEN gcs_min = 14 THEN 3
              ELSE 0
            END AS gcs_score,
            CASE
              WHEN heart_rate_max IS NULL THEN NULL
              WHEN heart_rate_max > 125 THEN 6
              WHEN heart_rate_min < 33 THEN 4
              WHEN heart_rate_max BETWEEN 107 AND 125 THEN 3
              WHEN heart_rate_max BETWEEN 89 AND 106 THEN 1
              ELSE 0
            END AS heart_rate_score,
            CASE
              WHEN mbp_min IS NULL THEN NULL
              WHEN mbp_min < 20.65 THEN 4
              WHEN mbp_min < 51 THEN 3
              WHEN mbp_max > 143.44 THEN 3
              WHEN mbp_min >= 51 AND mbp_min < 61.33 THEN 2
              ELSE 0
            END AS mbp_score,
            CASE
              WHEN resp_rate_min IS NULL THEN NULL
              WHEN resp_rate_min < 6 THEN 10
              WHEN resp_rate_max > 44 THEN 9
              WHEN resp_rate_max > 30 THEN 6
              WHEN resp_rate_max > 22 THEN 1
              WHEN resp_rate_min < 13 THEN 1
              ELSE 0
            END AS resp_rate_score,
            CASE
              WHEN temperature_max IS NULL THEN NULL
              WHEN temperature_max > 39.88 THEN 6
              WHEN temperature_min BETWEEN 33.22 AND 35.93 THEN 4
              WHEN temperature_max BETWEEN 33.22 AND 35.93 THEN 4
              WHEN temperature_min < 33.22 THEN 3
              WHEN temperature_min > 35.93
                   AND temperature_min <= 36.39 THEN 2
              WHEN temperature_max BETWEEN 36.89 AND 39.88 THEN 2
              ELSE 0
            END AS temp_score,
            CASE
              WHEN urineoutput IS NULL THEN NULL
              WHEN urineoutput < 671.09 THEN 10
              WHEN urineoutput > 6896.80 THEN 8
              WHEN urineoutput BETWEEN 671.09 AND 1426.99 THEN 5
              WHEN urineoutput BETWEEN 1427.00 AND 2544.14 THEN 1
              ELSE 0
            END AS urineoutput_score,
            CASE WHEN mechvent = 1 THEN 9 ELSE 0 END
              AS mechvent_score,
            CASE WHEN electivesurgery = 1 THEN 0 ELSE 6 END
              AS electivesurgery_score
          FROM oasis_components
        )
        SELECT
          *,
          coalesce(age_score, 0)
          + coalesce(preiculos_score, 0)
          + coalesce(gcs_score, 0)
          + coalesce(heart_rate_score, 0)
          + coalesce(mbp_score, 0)
          + coalesce(resp_rate_score, 0)
          + coalesce(temp_score, 0)
          + coalesce(urineoutput_score, 0)
          + coalesce(mechvent_score, 0)
          + coalesce(electivesurgery_score, 0) AS oasis,
          1 / (
            1 + exp(-(-6.1746 + 0.1275 * (
              coalesce(age_score, 0)
              + coalesce(preiculos_score, 0)
              + coalesce(gcs_score, 0)
              + coalesce(heart_rate_score, 0)
              + coalesce(mbp_score, 0)
              + coalesce(resp_rate_score, 0)
              + coalesce(temp_score, 0)
              + coalesce(urineoutput_score, 0)
              + coalesce(mechvent_score, 0)
              + coalesce(electivesurgery_score, 0)
            )))
          ) AS oasis_prob,
          (
            (age_score IS NULL)::INTEGER
            + (preiculos_score IS NULL)::INTEGER
            + (gcs_score IS NULL)::INTEGER
            + (heart_rate_score IS NULL)::INTEGER
            + (mbp_score IS NULL)::INTEGER
            + (resp_rate_score IS NULL)::INTEGER
            + (temp_score IS NULL)::INTEGER
            + (urineoutput_score IS NULL)::INTEGER
          ) AS oasis_missing_components_n
        FROM components
        """
    )
    LOG(
        "DONE OASIS scoring "
        f"rows={scalar(con, 'SELECT count(*) FROM oasis_scores')}"
    )


def build_not_given_dataset(con) -> None:
    LOG("START decision-event organ-support alignment")
    con.execute(
        """
        CREATE OR REPLACE TABLE decision_events_scoped AS
        SELECT e.*
        FROM emar_stay_events e
        WHERE e.event_category IN ('given_strict', 'not_given')
          AND (
            e.drug_class <> 'vte_prophylaxis'
            OR EXISTS (
              SELECT 1
              FROM eligible_order_clusters o
              WHERE o.subject_id = e.subject_id
                AND o.hadm_id = e.hadm_id
                AND o.stay_id = e.stay_id
                AND o.drug_class = e.drug_class
                AND o.poe_id = e.poe_id
            )
          )
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE
          decision_events_audit_sensitivity_scoped AS
        SELECT
          e.*,
          CASE
            WHEN e.event_category = 'not_given' THEN 1
            WHEN lower(trim(coalesce(e.event_txt, ''))) = 'hold dose'
              THEN 1
            WHEN lower(trim(coalesce(e.event_txt, '')))
                 LIKE 'not given per sliding scale%'
              THEN 1
            ELSE 0
          END AS not_given_audit_sensitivity
        FROM emar_stay_events e
        WHERE (
            e.event_category IN ('given_strict', 'not_given')
            OR lower(trim(coalesce(e.event_txt, ''))) = 'hold dose'
            OR lower(trim(coalesce(e.event_txt, '')))
               LIKE 'not given per sliding scale%'
          )
          AND (
            e.drug_class <> 'vte_prophylaxis'
            OR EXISTS (
              SELECT 1
              FROM eligible_order_clusters o
              WHERE o.subject_id = e.subject_id
                AND o.hadm_id = e.hadm_id
                AND o.stay_id = e.stay_id
                AND o.drug_class = e.drug_class
                AND o.poe_id = e.poe_id
            )
          )
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE decision_event_support AS
        SELECT
          e.emar_id, e.emar_seq, e.drug_class,
          max((i.support_type = 'invasive_ventilation')::INTEGER)
            AS invasive_ventilation_active,
          max((i.support_type = 'vasopressor')::INTEGER)
            AS vasopressor_active,
          max((i.support_type = 'rrt')::INTEGER) AS rrt_active
        FROM decision_events_audit_sensitivity_scoped e
        LEFT JOIN organ_support_intervals i
          ON e.stay_id = i.stay_id
         AND e.charttime BETWEEN i.starttime AND i.endtime
        GROUP BY e.emar_id, e.emar_seq, e.drug_class
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE not_given_event_model AS
        SELECT
          e.subject_id, e.hadm_id, e.stay_id,
          e.emar_id, e.emar_seq, e.drug_class, e.charttime,
          (e.event_category = 'not_given')::INTEGER AS not_given,
          CASE
            WHEN hour(e.charttime) >= 7 AND hour(e.charttime) < 19
              THEN 'day_0700_1859'
            ELSE 'night_1900_0659'
          END AS shift,
          coalesce(es.invasive_ventilation_active, 0)
            AS invasive_ventilation_active,
          coalesce(es.vasopressor_active, 0) AS vasopressor_active,
          coalesce(es.rrt_active, 0) AS rrt_active,
          o.oasis,
          o.oasis_missing_components_n,
          s.age_at_icu,
          s.gender,
          s.emergency_admission,
          s.first_careunit,
          s.anchor_era
        FROM decision_events_scoped e
        JOIN adult_stays s USING (subject_id, hadm_id, stay_id)
        LEFT JOIN oasis_scores o USING (subject_id, hadm_id, stay_id)
        LEFT JOIN decision_event_support es
          ON e.emar_id = es.emar_id
         AND e.emar_seq = es.emar_seq
         AND e.drug_class = es.drug_class
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE not_given_model_aggregated AS
        SELECT
          stay_id, drug_class, shift,
          invasive_ventilation_active,
          vasopressor_active, rrt_active,
          oasis, oasis_missing_components_n,
          age_at_icu, gender, emergency_admission,
          first_careunit, anchor_era,
          sum(not_given) AS not_given_n,
          sum(1 - not_given) AS given_n,
          count(*) AS decision_events_n
        FROM not_given_event_model
        GROUP BY ALL
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE
          not_given_audit_sensitivity_event_model AS
        SELECT
          e.subject_id, e.hadm_id, e.stay_id,
          e.emar_id, e.emar_seq, e.drug_class, e.charttime,
          e.not_given_audit_sensitivity AS not_given,
          CASE
            WHEN hour(e.charttime) >= 7 AND hour(e.charttime) < 19
              THEN 'day_0700_1859'
            ELSE 'night_1900_0659'
          END AS shift,
          coalesce(es.invasive_ventilation_active, 0)
            AS invasive_ventilation_active,
          coalesce(es.vasopressor_active, 0) AS vasopressor_active,
          coalesce(es.rrt_active, 0) AS rrt_active,
          o.oasis,
          o.oasis_missing_components_n,
          s.age_at_icu,
          s.gender,
          s.emergency_admission,
          s.first_careunit,
          s.anchor_era
        FROM decision_events_audit_sensitivity_scoped e
        JOIN adult_stays s USING (subject_id, hadm_id, stay_id)
        LEFT JOIN oasis_scores o USING (subject_id, hadm_id, stay_id)
        LEFT JOIN decision_event_support es
          ON e.emar_id = es.emar_id
         AND e.emar_seq = es.emar_seq
         AND e.drug_class = es.drug_class
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE
          not_given_audit_sensitivity_model_aggregated AS
        SELECT
          stay_id, drug_class, shift,
          invasive_ventilation_active,
          vasopressor_active, rrt_active,
          oasis, oasis_missing_components_n,
          age_at_icu, gender, emergency_admission,
          first_careunit, anchor_era,
          sum(not_given) AS not_given_n,
          sum(1 - not_given) AS given_n,
          count(*) AS decision_events_n
        FROM not_given_audit_sensitivity_event_model
        GROUP BY ALL
        """
    )
    model = qdf(
        con,
        """
        SELECT * FROM not_given_model_aggregated
        ORDER BY stay_id, drug_class, shift
        """,
    )
    write_csv(model, CACHE / "not_given_model_aggregated.csv")
    sensitivity_model = qdf(
        con,
        """
        SELECT *
        FROM not_given_audit_sensitivity_model_aggregated
        ORDER BY stay_id, drug_class, shift
        """,
    )
    write_csv(
        sensitivity_model,
        CACHE / "not_given_audit_semantic_sensitivity_aggregated.csv",
    )
    sensitivity_events_n = scalar(
        con,
        "SELECT count(*) "
        "FROM not_given_audit_sensitivity_event_model",
    )
    LOG(
        "DONE not-given model dataset "
        f"events={scalar(con, 'SELECT count(*) FROM not_given_event_model')} "
        f"aggregated_rows={len(model)} sensitivity_events="
        f"{sensitivity_events_n} "
        f"sensitivity_aggregated_rows={len(sensitivity_model)}"
    )


def summarize(con) -> dict[str, object]:
    LOG("START severity/not-given descriptive summaries")
    coverage = qdf(
        con,
        """
        SELECT
          count(*) AS adult_stays_n,
          sum((gcs_min IS NOT NULL)::INTEGER) AS gcs_available_n,
          sum((heart_rate_max IS NOT NULL)::INTEGER) AS hr_available_n,
          sum((mbp_min IS NOT NULL)::INTEGER) AS mbp_available_n,
          sum((resp_rate_max IS NOT NULL)::INTEGER) AS rr_available_n,
          sum((temperature_max IS NOT NULL)::INTEGER)
            AS temperature_available_n,
          sum((urineoutput IS NOT NULL)::INTEGER) AS urine_available_n,
          avg(oasis) AS oasis_mean,
          median(oasis) AS oasis_median,
          quantile_cont(oasis, 0.25) AS oasis_p25,
          quantile_cont(oasis, 0.75) AS oasis_p75,
          avg(oasis_missing_components_n) AS mean_missing_components
        FROM oasis_scores
        """,
    )
    write_csv(coverage, TABLES / "oasis_component_coverage.csv")

    stratified = qdf(
        con,
        """
        WITH x AS (
          SELECT
            *,
            ntile(4) OVER (ORDER BY oasis) AS oasis_quartile
          FROM not_given_event_model
        )
        SELECT
          'oasis_quartile' AS dimension,
          cast(oasis_quartile AS VARCHAR) AS level,
          count(*) AS decision_events_n,
          sum(not_given) AS not_given_n,
          100.0 * avg(not_given) AS not_given_pct
        FROM x GROUP BY oasis_quartile
        UNION ALL
        SELECT 'shift', shift, count(*), sum(not_given),
               100.0 * avg(not_given)
        FROM x GROUP BY shift
        UNION ALL
        SELECT 'invasive_ventilation_active',
               cast(invasive_ventilation_active AS VARCHAR),
               count(*), sum(not_given), 100.0 * avg(not_given)
        FROM x GROUP BY invasive_ventilation_active
        UNION ALL
        SELECT 'vasopressor_active',
               cast(vasopressor_active AS VARCHAR),
               count(*), sum(not_given), 100.0 * avg(not_given)
        FROM x GROUP BY vasopressor_active
        UNION ALL
        SELECT 'rrt_active', cast(rrt_active AS VARCHAR),
               count(*), sum(not_given), 100.0 * avg(not_given)
        FROM x GROUP BY rrt_active
        ORDER BY dimension, level
        """,
    )
    write_csv(stratified, TABLES / "not_given_stratified_rates.csv")

    class_rates = qdf(
        con,
        """
        SELECT
          drug_class,
          count(*) AS decision_events_n,
          sum(not_given) AS not_given_n,
          100.0 * avg(not_given) AS not_given_pct,
          count(DISTINCT stay_id) AS stays_n
        FROM not_given_event_model
        GROUP BY drug_class
        ORDER BY drug_class
        """,
    )
    write_csv(class_rates, TABLES / "not_given_class_rates_scoped.csv")

    sensitivity_class_rates = qdf(
        con,
        """
        SELECT
          drug_class,
          count(*) AS decision_events_n,
          sum(not_given) AS not_given_n,
          100.0 * avg(not_given) AS not_given_pct,
          count(DISTINCT stay_id) AS stays_n
        FROM not_given_audit_sensitivity_event_model
        GROUP BY drug_class
        ORDER BY drug_class
        """,
    )
    write_csv(
        sensitivity_class_rates,
        TABLES / "not_given_audit_semantic_sensitivity_class_rates.csv",
    )

    support = qdf(
        con,
        """
        SELECT support_type, count(*) AS intervals_n,
               count(DISTINCT stay_id) AS stays_n
        FROM organ_support_intervals
        GROUP BY support_type
        ORDER BY support_type
        """,
    )
    write_csv(support, TABLES / "organ_support_interval_counts.csv")

    summary = {
        "oasis_rows_n": scalar(con, "SELECT count(*) FROM oasis_scores"),
        "not_given_decision_events_n": scalar(
            con, "SELECT count(*) FROM not_given_event_model"
        ),
        "not_given_events_n": scalar(
            con,
            "SELECT sum(not_given) FROM not_given_event_model",
        ),
        "not_given_model_aggregated_rows_n": scalar(
            con, "SELECT count(*) FROM not_given_model_aggregated"
        ),
        "not_given_audit_sensitivity_decision_events_n": scalar(
            con,
            "SELECT count(*) "
            "FROM not_given_audit_sensitivity_event_model",
        ),
        "not_given_audit_sensitivity_events_n": scalar(
            con,
            "SELECT sum(not_given) "
            "FROM not_given_audit_sensitivity_event_model",
        ),
    }
    LOG(f"DONE severity/not-given summaries {summary}")
    return summary


def render_report(summary: dict[str, object]) -> str:
    coverage = pd.read_csv(TABLES / "oasis_component_coverage.csv")
    rates = pd.read_csv(TABLES / "not_given_stratified_rates.csv")
    class_rates = pd.read_csv(
        TABLES / "not_given_class_rates_scoped.csv"
    )
    sensitivity_rates = pd.read_csv(
        TABLES / "not_given_audit_semantic_sensitivity_class_rates.csv"
    )
    support = pd.read_csv(TABLES / "organ_support_interval_counts.csv")
    return "\n".join(
        [
            "# 03 — Severity, shift, and organ-support alignment",
            "",
            "OASIS uses the official MIMIC Code v3.0.0 component cutpoints,",
            "vital-sign item mappings, GCS handling, and urine-output item set.",
            "The implementation is frozen and independent of medication",
            "outcomes.",
            "",
            "Official source: MIT-LCP MIMIC Code `oasis.sql`, `gcs.sql`,",
            "`first_day_*`, `ventilator_setting.sql`,",
            "`oxygen_delivery.sql`, and `ventilation.sql` (repository main",
            "branch inspected 2026-07-29).",
            "",
            "## OASIS component coverage",
            "",
            "```text",
            coverage.to_string(index=False),
            "```",
            "",
            "## Organ-support intervals",
            "",
            "```text",
            support.to_string(index=False),
            "```",
            "",
            "## Class-specific decision-event rates",
            "",
            "```text",
            class_rates.to_string(index=False),
            "```",
            "",
            "## Pre-model semantic-audit sensitivity",
            "",
            "The original literal mapping remains primary. The separately",
            "hashed pre-model addendum adds only exact `Hold Dose` and the",
            "`Not Given per Sliding Scale*` vendor subtype. It cannot alter",
            "pilot gates or the final stop-loss decision.",
            "",
            "```text",
            sensitivity_rates.to_string(index=False),
            "```",
            "",
            "## Prespecified crude stratification",
            "",
            "```text",
            rates.to_string(index=False),
            "```",
            "",
            "The adjusted clustered logistic model is fitted by the locked R",
            "script after this extraction; these crude rates are not used to",
            "select classes or covariates.",
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
    verify_semantic_addendum()
    con = connect_duckdb()
    required = (
        "adult_stays",
        "emar_stay_events",
        "eligible_order_clusters",
    )
    absent = [name for name in required if not table_exists(con, name)]
    if absent:
        raise RuntimeError(
            "Run 02_build_primary_estimands_v2.py --full first; missing "
            + ", ".join(absent)
        )
    build_oasis_chart_raw(con)
    build_first_day_vitals_gcs(con)
    build_organ_support_intervals(con)
    build_first_day_urine(con)
    build_oasis(con)
    build_not_given_dataset(con)
    summary = summarize(con)
    con.close()

    (REPORTS / "03_severity_shift_organ_support.md").write_text(
        render_report(summary), encoding="utf-8"
    )
    metadata = script_metadata(started, SCRIPT)
    metadata.update(summary)
    metadata.update(
        {
            "oasis_reference": (
                "MIT-LCP/mimic-code v3.0.0 concepts/score/oasis.sql"
            ),
            "oasis_chartevents_full_scan": True,
        }
    )
    write_json(metadata, MANIFESTS / "03_build_severity_notgiven.json")
    LOG(f"DONE severity extraction elapsed={metadata['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
