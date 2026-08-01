from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pandas as pd

from common import (
    CONFIG,
    EICU_ZIP,
    MANIFESTS,
    MIMIC_ROOT,
    ND03_EICU_WHITELIST,
    ND03_MIMIC_WHITELIST,
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
    source_stat,
    subclass_case_sql,
    verify_frozen_contract,
    write_csv,
    write_json,
)


SCRIPT = Path(__file__).resolve()
LOG = RunLogger("01_full_interface_audit")


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


def build_poe_identity(con) -> None:
    if table_exists(con, "poe_identity"):
        rows = scalar(con, "SELECT count(*) FROM poe_identity")
        if rows > 0:
            LOG(f"RESUME existing poe_identity unique_poe_ids={rows}")
            return
    LOG("START full POE identity scan")
    poe = csv_scan(MIMIC_ROOT / "hosp" / "poe.csv.gz")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE poe_identity AS
        SELECT
          poe_id,
          min(TRY_CAST(subject_id AS BIGINT)) AS subject_id,
          min(TRY_CAST(hadm_id AS BIGINT)) AS hadm_id,
          count(*) AS poe_rows_n,
          count(DISTINCT subject_id) AS subject_values_n,
          count(DISTINCT hadm_id) AS hadm_values_n,
          min(TRY_CAST(ordertime AS TIMESTAMP)) AS first_ordertime,
          max(TRY_CAST(ordertime AS TIMESTAMP)) AS last_ordertime
        FROM {poe}
        WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
        GROUP BY poe_id
        """
    )
    LOG(
        "DONE full POE identity scan "
        f"unique_poe_ids={scalar(con, 'SELECT count(*) FROM poe_identity')}"
    )


def full_emar_audit(con) -> dict[str, int | float]:
    if table_exists(con, "emar_event_txt_full_audit"):
        LOG("RESUME existing full eMAR event_txt and POE-link audit")
    else:
        LOG("START full eMAR event_txt and POE-link audit")
        emar = csv_scan(MIMIC_ROOT / "hosp" / "emar.csv.gz")
        con.execute(
            f"""
        CREATE OR REPLACE TABLE emar_event_txt_full_audit AS
        SELECT
          CASE
            WHEN e.event_txt IS NULL THEN '<NULL>'
            WHEN trim(e.event_txt) = '' THEN '<EMPTY>'
            ELSE e.event_txt
          END AS event_txt,
          count(*) AS rows_n,
          count(*) FILTER (
            WHERE e.poe_id IS NOT NULL AND trim(e.poe_id) <> ''
          ) AS poe_id_nonmissing_n,
          count(*) FILTER (
            WHERE p.poe_id IS NOT NULL
          ) AS poe_id_any_link_n,
          count(*) FILTER (
            WHERE p.poe_id IS NOT NULL
              AND p.subject_id = TRY_CAST(e.subject_id AS BIGINT)
              AND (
                p.hadm_id = TRY_CAST(e.hadm_id AS BIGINT)
                OR (p.hadm_id IS NULL AND e.hadm_id IS NULL)
              )
          ) AS poe_id_identity_link_n,
          count(*) FILTER (
            WHERE p.poe_id IS NOT NULL
              AND (
                p.subject_id <> TRY_CAST(e.subject_id AS BIGINT)
                OR (
                  p.hadm_id IS DISTINCT FROM TRY_CAST(e.hadm_id AS BIGINT)
                )
              )
          ) AS poe_id_identity_mismatch_n
        FROM {emar} e
        LEFT JOIN poe_identity p ON e.poe_id = p.poe_id
        GROUP BY 1
        ORDER BY rows_n DESC, event_txt
        """
        )
    audit = qdf(
        con,
        "SELECT * FROM emar_event_txt_full_audit "
        "ORDER BY rows_n DESC, event_txt",
    )
    write_csv(audit, TABLES / "emar_full_event_txt_distribution.csv")

    summary = qdf(
        con,
        """
        SELECT
          sum(rows_n)::BIGINT AS emar_rows_n,
          sum(poe_id_nonmissing_n)::BIGINT AS poe_id_nonmissing_n,
          sum(poe_id_any_link_n)::BIGINT AS poe_id_any_link_n,
          sum(poe_id_identity_link_n)::BIGINT AS poe_id_identity_link_n,
          sum(poe_id_identity_mismatch_n)::BIGINT
            AS poe_id_identity_mismatch_n,
          100.0 * sum(poe_id_nonmissing_n) / sum(rows_n)
            AS poe_id_nonmissing_pct,
          100.0 * sum(poe_id_any_link_n)
            / nullif(sum(poe_id_nonmissing_n), 0)
            AS poe_any_link_among_nonmissing_pct,
          100.0 * sum(poe_id_identity_link_n)
            / nullif(sum(poe_id_nonmissing_n), 0)
            AS poe_identity_link_among_nonmissing_pct
        FROM emar_event_txt_full_audit
        """,
    )
    write_csv(summary, TABLES / "emar_full_poe_link_summary.csv")
    values = summary.iloc[0].to_dict()
    values["distribution_sum_n"] = int(audit["rows_n"].sum())
    values["distribution_reconciles"] = bool(
        int(values["emar_rows_n"]) == int(values["distribution_sum_n"])
    )
    if not values["distribution_reconciles"]:
        raise RuntimeError("Full eMAR event_txt distribution did not reconcile")
    LOG(
        "DONE full eMAR audit "
        f"rows={int(values['emar_rows_n'])} "
        f"poe_nonmissing={int(values['poe_id_nonmissing_n'])} "
        f"identity_links={int(values['poe_id_identity_link_n'])}"
    )
    return values


def build_emar_medication_candidates(con, whitelist: pd.DataFrame) -> None:
    if table_exists(con, "emar_medication_candidates"):
        rows = scalar(con, "SELECT count(*) FROM emar_medication_candidates")
        if rows > 0:
            LOG(f"RESUME existing eMAR medication candidates rows={rows}")
            return
    LOG("START full eMAR frozen-name medication scan")
    emar = csv_scan(MIMIC_ROOT / "hosp" / "emar.csv.gz")
    text = "lower(trim(coalesce(e.medication, '')))"
    any_match = regex_sql_condition(text, whitelist)
    class_case = class_case_sql(text, whitelist, "drug_class")
    ingredient_case = ingredient_case_sql(text, whitelist, "ingredient")
    subclass_case = subclass_case_sql(text, whitelist, "subclass")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE emar_medication_candidates AS
        SELECT
          TRY_CAST(e.subject_id AS BIGINT) AS subject_id,
          TRY_CAST(e.hadm_id AS BIGINT) AS hadm_id,
          e.emar_id,
          TRY_CAST(e.emar_seq AS BIGINT) AS emar_seq,
          e.poe_id,
          e.pharmacy_id,
          TRY_CAST(e.charttime AS TIMESTAMP) AS charttime,
          TRY_CAST(e.scheduletime AS TIMESTAMP) AS scheduletime,
          e.medication,
          e.event_txt,
          {class_case},
          {ingredient_case},
          {subclass_case},
          'medication' AS name_match_source
        FROM {emar} e
        WHERE {any_match}
        """
    )
    LOG(
        "DONE frozen-name medication scan "
        f"rows={scalar(con, 'SELECT count(*) FROM emar_medication_candidates')}"
    )


def build_detail_and_product_candidates(
    con, whitelist: pd.DataFrame
) -> None:
    if table_exists(con, "emar_detail_relevant") and table_exists(
        con, "detail_product_candidates"
    ):
        relevant = scalar(con, "SELECT count(*) FROM emar_detail_relevant")
        products = scalar(
            con, "SELECT count(*) FROM detail_product_candidates"
        )
        if relevant > 0:
            LOG(
                "RESUME existing eMAR-detail candidates "
                f"relevant_rows={relevant} product_keys={products}"
            )
            return
    LOG("START full eMAR-detail scan for all medication/product candidates")
    detail = csv_scan(MIMIC_ROOT / "hosp" / "emar_detail.csv.gz")
    text = "lower(trim(coalesce(d.product_description, '')))"
    any_match = regex_sql_condition(text, whitelist)
    class_case = class_case_sql(text, whitelist, "product_drug_class")
    ingredient_case = ingredient_case_sql(
        text, whitelist, "product_ingredient"
    )
    subclass_case = subclass_case_sql(text, whitelist, "product_subclass")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE emar_detail_relevant AS
        SELECT
          TRY_CAST(d.subject_id AS BIGINT) AS subject_id,
          d.emar_id,
          TRY_CAST(d.emar_seq AS BIGINT) AS emar_seq,
          d.parent_field_ordinal,
          d.administration_type,
          d.pharmacy_id,
          d.barcode_type,
          d.reason_for_no_barcode,
          d.complete_dose_not_given,
          d.dose_due,
          d.dose_due_unit,
          d.dose_given,
          d.dose_given_unit,
          d.product_amount_given,
          d.product_unit,
          d.product_code,
          d.product_description,
          d.product_description_other,
          d.infusion_rate,
          d.infusion_rate_unit,
          d.route,
          d.infusion_complete,
          d.new_iv_bag_hung,
          d.continued_infusion_in_other_location,
          {class_case},
          {ingredient_case},
          {subclass_case}
        FROM {detail} d
        LEFT JOIN (
          SELECT DISTINCT emar_id, emar_seq
          FROM emar_medication_candidates
        ) e
          ON d.emar_id = e.emar_id
         AND TRY_CAST(d.emar_seq AS BIGINT) = e.emar_seq
        WHERE e.emar_id IS NOT NULL OR {any_match}
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE detail_product_candidates AS
        SELECT
          emar_id, emar_seq,
          arg_max(product_drug_class, parent_field_ordinal)
            FILTER (WHERE product_drug_class IS NOT NULL) AS drug_class,
          arg_max(product_ingredient, parent_field_ordinal)
            FILTER (WHERE product_ingredient IS NOT NULL) AS ingredient,
          arg_max(product_subclass, parent_field_ordinal)
            FILTER (WHERE product_subclass IS NOT NULL) AS subclass
        FROM emar_detail_relevant
        WHERE product_drug_class IS NOT NULL
        GROUP BY emar_id, emar_seq
        """
    )
    LOG(
        "DONE full eMAR-detail scan "
        f"relevant_rows={scalar(con, 'SELECT count(*) FROM emar_detail_relevant')} "
        "product_only_keys="
        f"{scalar(con, 'SELECT count(*) FROM detail_product_candidates')}"
    )


def build_final_emar_events(con) -> dict[str, int]:
    if table_exists(con, "emar_medication_events"):
        rows = scalar(con, "SELECT count(*) FROM emar_medication_events")
        if rows > 0:
            summary = {
                "medication_candidate_rows_n": scalar(
                    con, "SELECT count(*) FROM emar_medication_candidates"
                ),
                "product_candidate_rows_n": scalar(
                    con, "SELECT count(*) FROM emar_product_candidates"
                ),
                "whitelist_event_rows_n": rows,
            }
            LOG(f"RESUME existing event-level aggregation {summary}")
            return summary
    LOG("START product-only eMAR recovery and event-level detail aggregation")
    emar = csv_scan(MIMIC_ROOT / "hosp" / "emar.csv.gz")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE emar_product_candidates AS
        SELECT
          TRY_CAST(e.subject_id AS BIGINT) AS subject_id,
          TRY_CAST(e.hadm_id AS BIGINT) AS hadm_id,
          e.emar_id,
          TRY_CAST(e.emar_seq AS BIGINT) AS emar_seq,
          e.poe_id,
          e.pharmacy_id,
          TRY_CAST(e.charttime AS TIMESTAMP) AS charttime,
          TRY_CAST(e.scheduletime AS TIMESTAMP) AS scheduletime,
          e.medication,
          e.event_txt,
          p.drug_class,
          p.ingredient,
          p.subclass,
          'product_description' AS name_match_source
        FROM {emar} e
        JOIN detail_product_candidates p
          ON e.emar_id = p.emar_id
         AND TRY_CAST(e.emar_seq AS BIGINT) = p.emar_seq
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE emar_whitelist_base AS
        SELECT * EXCLUDE (rn)
        FROM (
          SELECT *,
            row_number() OVER (
              PARTITION BY emar_id, emar_seq, drug_class
              ORDER BY
                CASE name_match_source
                  WHEN 'medication' THEN 1 ELSE 2
                END
            ) AS rn
          FROM (
            SELECT * FROM emar_medication_candidates
            UNION ALL BY NAME
            SELECT * FROM emar_product_candidates
          )
          WHERE drug_class IS NOT NULL
        )
        WHERE rn = 1
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE emar_detail_event_agg AS
        SELECT
          b.emar_id,
          b.emar_seq,
          count(d.emar_id) AS detail_rows_n,
          bool_or(
            lower(trim(coalesce(d.complete_dose_not_given, ''))) = 'yes'
          ) AS any_complete_dose_not_given,
          max(TRY_CAST(d.dose_given AS DOUBLE)) FILTER (
            WHERE TRY_CAST(d.dose_given AS DOUBLE) > 0
          ) AS dose_given_num,
          arg_max(d.dose_given_unit, TRY_CAST(d.dose_given AS DOUBLE))
            FILTER (
              WHERE TRY_CAST(d.dose_given AS DOUBLE) > 0
                AND d.dose_given_unit IS NOT NULL
            ) AS dose_given_unit,
          max(TRY_CAST(d.dose_due AS DOUBLE)) FILTER (
            WHERE TRY_CAST(d.dose_due AS DOUBLE) > 0
          ) AS dose_due_num,
          arg_max(d.dose_due_unit, TRY_CAST(d.dose_due AS DOUBLE))
            FILTER (
              WHERE TRY_CAST(d.dose_due AS DOUBLE) > 0
                AND d.dose_due_unit IS NOT NULL
            ) AS dose_due_unit,
          max(TRY_CAST(d.product_amount_given AS DOUBLE)) FILTER (
            WHERE TRY_CAST(d.product_amount_given AS DOUBLE) > 0
          ) AS product_amount_given_num,
          arg_max(
            d.product_unit, TRY_CAST(d.product_amount_given AS DOUBLE)
          ) FILTER (
            WHERE TRY_CAST(d.product_amount_given AS DOUBLE) > 0
              AND d.product_unit IS NOT NULL
          ) AS product_unit,
          string_agg(DISTINCT d.route, ' || ') FILTER (
            WHERE d.route IS NOT NULL AND trim(d.route) <> ''
          ) AS route,
          string_agg(DISTINCT d.administration_type, ' || ') FILTER (
            WHERE d.administration_type IS NOT NULL
              AND trim(d.administration_type) <> ''
          ) AS administration_type,
          string_agg(DISTINCT d.barcode_type, ' || ') FILTER (
            WHERE d.barcode_type IS NOT NULL
              AND trim(d.barcode_type) <> ''
          ) AS barcode_type,
          string_agg(DISTINCT d.reason_for_no_barcode, ' || ') FILTER (
            WHERE d.reason_for_no_barcode IS NOT NULL
              AND trim(d.reason_for_no_barcode) <> ''
          ) AS reason_for_no_barcode,
          string_agg(DISTINCT d.product_description, ' || ') FILTER (
            WHERE d.product_description IS NOT NULL
              AND trim(d.product_description) <> ''
          ) AS product_description,
          string_agg(
            DISTINCT d.product_description_other, ' || '
          ) FILTER (
            WHERE d.product_description_other IS NOT NULL
              AND trim(d.product_description_other) <> ''
          ) AS product_description_other
        FROM emar_whitelist_base b
        LEFT JOIN emar_detail_relevant d
          ON b.emar_id = d.emar_id
         AND b.emar_seq = d.emar_seq
        GROUP BY b.emar_id, b.emar_seq
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE emar_medication_events AS
        SELECT
          b.*,
          d.* EXCLUDE (emar_id, emar_seq),
          CASE
            WHEN coalesce(d.any_complete_dose_not_given, false)
              THEN 'not_given'
            WHEN lower(trim(coalesce(b.event_txt, ''))) IN (
              'administered', 'delayed administered',
              'partial administered', 'applied', 'started'
            ) THEN 'given_strict'
            WHEN lower(trim(coalesce(b.event_txt, ''))) IN (
              'not given', 'held', 'refused'
            ) THEN 'not_given'
            WHEN lower(trim(coalesce(b.event_txt, ''))) = 'flushed'
              THEN 'flushed'
            WHEN lower(trim(coalesce(b.event_txt, ''))) = 'confirmed'
              THEN 'confirmed'
            WHEN b.event_txt IS NULL OR trim(b.event_txt) = ''
              THEN 'blank'
            ELSE 'other_excluded'
          END AS event_category,
          p.poe_id IS NOT NULL AS poe_id_any_link,
          (
            p.poe_id IS NOT NULL
            AND p.subject_id = b.subject_id
            AND (
              p.hadm_id = b.hadm_id
              OR (p.hadm_id IS NULL AND b.hadm_id IS NULL)
            )
          ) AS poe_id_identity_link
        FROM emar_whitelist_base b
        LEFT JOIN emar_detail_event_agg d
          ON b.emar_id = d.emar_id AND b.emar_seq = d.emar_seq
        LEFT JOIN poe_identity p ON b.poe_id = p.poe_id
        """
    )
    summary = {
        "medication_candidate_rows_n": scalar(
            con, "SELECT count(*) FROM emar_medication_candidates"
        ),
        "product_candidate_rows_n": scalar(
            con, "SELECT count(*) FROM emar_product_candidates"
        ),
        "whitelist_event_rows_n": scalar(
            con, "SELECT count(*) FROM emar_medication_events"
        ),
    }
    LOG(f"DONE event-level aggregation {summary}")
    return summary


def summarize_emar_detail(con) -> None:
    LOG("START eMAR class/event/detail summaries")
    event_counts = qdf(
        con,
        """
        SELECT
          drug_class,
          CASE
            WHEN event_txt IS NULL THEN '<NULL>'
            WHEN trim(event_txt) = '' THEN '<EMPTY>'
            ELSE event_txt
          END AS event_txt,
          event_category,
          count(*) AS events_n,
          count(DISTINCT subject_id) AS subjects_n,
          count(DISTINCT hadm_id) AS hadms_n,
          count(DISTINCT poe_id) FILTER (
            WHERE poe_id IS NOT NULL AND trim(poe_id) <> ''
          ) AS poe_ids_n,
          sum(poe_id_identity_link::INTEGER) AS identity_linked_events_n
        FROM emar_medication_events
        GROUP BY ALL
        ORDER BY drug_class, events_n DESC, event_txt
        """,
    )
    write_csv(event_counts, TABLES / "emar_event_semantics_by_class.csv")

    detail = qdf(
        con,
        """
        SELECT
          drug_class,
          event_category,
          count(*) AS events_n,
          sum((detail_rows_n > 0)::INTEGER) AS detail_linked_n,
          100.0 * avg((detail_rows_n > 0)::INTEGER)
            AS detail_linked_pct,
          sum((dose_given_num IS NOT NULL)::INTEGER)
            AS dose_given_available_n,
          100.0 * avg((dose_given_num IS NOT NULL)::INTEGER)
            AS dose_given_available_pct,
          sum((
            dose_given_num IS NOT NULL
            AND dose_given_unit IS NOT NULL
          )::INTEGER) AS dose_given_with_unit_n,
          100.0 * avg((
            dose_given_num IS NOT NULL
            AND dose_given_unit IS NOT NULL
          )::INTEGER) AS dose_given_with_unit_pct,
          sum((dose_due_num IS NOT NULL)::INTEGER)
            AS dose_due_available_n,
          sum((product_amount_given_num IS NOT NULL)::INTEGER)
            AS product_amount_available_n,
          sum((route IS NOT NULL)::INTEGER) AS route_available_n,
          sum((administration_type IS NOT NULL)::INTEGER)
            AS administration_type_available_n,
          sum((reason_for_no_barcode IS NOT NULL)::INTEGER)
            AS reason_for_no_barcode_available_n,
          sum(coalesce(any_complete_dose_not_given, false)::INTEGER)
            AS complete_dose_not_given_yes_n
        FROM emar_medication_events
        GROUP BY drug_class, event_category
        ORDER BY drug_class, event_category
        """,
    )
    write_csv(detail, TABLES / "emar_detail_availability_by_class.csv")

    reasons = qdf(
        con,
        """
        SELECT
          drug_class,
          event_category,
          CASE
            WHEN event_txt IS NULL THEN '<NULL>'
            WHEN trim(event_txt) = '' THEN '<EMPTY>'
            ELSE event_txt
          END AS event_txt,
          coalesce(
            cast(any_complete_dose_not_given AS VARCHAR), '<NULL>'
          ) AS complete_dose_not_given,
          coalesce(administration_type, '<NULL>') AS administration_type,
          coalesce(reason_for_no_barcode, '<NULL>')
            AS reason_for_no_barcode,
          coalesce(barcode_type, '<NULL>') AS barcode_type,
          coalesce(route, '<NULL>') AS route,
          count(*) AS events_n
        FROM emar_medication_events
        WHERE event_category = 'not_given'
        GROUP BY ALL
        ORDER BY drug_class, events_n DESC
        """,
    )
    write_csv(reasons, TABLES / "emar_not_given_reason_fields.csv")

    denominator = qdf(
        con,
        """
        SELECT
          drug_class,
          count(*) AS all_whitelist_events_n,
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
            )::INTEGER), 0) AS not_given_pct_decision_denominator
        FROM emar_medication_events
        GROUP BY drug_class
        ORDER BY drug_class
        """,
    )
    write_csv(
        denominator, TABLES / "emar_decision_denominator_by_class.csv"
    )
    LOG("DONE eMAR class/event/detail summaries")


def build_d_items_orphans(con) -> dict[str, object]:
    if table_exists(con, "d_items_all") and table_exists(
        con, "d_items_fact_counts"
    ):
        LOG("RESUME existing d_items-to-fact interface item counts")
    else:
        LOG("START full d_items-to-fact interface item counts")
        d_items = csv_scan(MIMIC_ROOT / "icu" / "d_items.csv.gz")
        con.execute(
            f"""
        CREATE OR REPLACE TABLE d_items_all AS
        SELECT
          TRY_CAST(itemid AS BIGINT) AS itemid,
          label,
          abbreviation,
          lower(trim(linksto)) AS linksto,
          category,
          unitname,
          param_type
        FROM {d_items}
        """
        )
        fact_tables = [
            "chartevents",
            "datetimeevents",
            "ingredientevents",
            "inputevents",
            "outputevents",
            "procedureevents",
        ]
        parts = []
        for table in fact_tables:
            scan = csv_scan(MIMIC_ROOT / "icu" / f"{table}.csv.gz")
            parts.append(
                f"""
            SELECT {repr(table)} AS linksto,
                   TRY_CAST(itemid AS BIGINT) AS itemid,
                   count(*)::BIGINT AS fact_rows_n
            FROM {scan}
            WHERE itemid IS NOT NULL
            GROUP BY TRY_CAST(itemid AS BIGINT)
            """
            )
        con.execute(
            "CREATE OR REPLACE TABLE d_items_fact_counts AS "
            + "\nUNION ALL\n".join(parts)
        )
    orphan = qdf(
        con,
        """
        SELECT
          d.linksto,
          d.itemid,
          d.label,
          d.abbreviation,
          d.category,
          d.unitname,
          d.param_type,
          coalesce(f.fact_rows_n, 0)::BIGINT AS fact_rows_n
        FROM d_items_all d
        LEFT JOIN d_items_fact_counts f
          ON d.linksto = f.linksto AND d.itemid = f.itemid
        WHERE d.linksto IN (
          'chartevents', 'datetimeevents', 'ingredientevents',
          'inputevents', 'outputevents', 'procedureevents'
        )
          AND coalesce(f.fact_rows_n, 0) = 0
        ORDER BY d.linksto, d.itemid
        """,
    )
    write_csv(orphan, TABLES / "d_items_zero_fact_rows_complete.csv")
    counts = qdf(
        con,
        """
        SELECT
          d.linksto,
          count(*) AS dictionary_items_n,
          sum((coalesce(f.fact_rows_n, 0) = 0)::INTEGER)
            AS zero_fact_items_n,
          sum(coalesce(f.fact_rows_n, 0))::HUGEINT AS fact_rows_n
        FROM d_items_all d
        LEFT JOIN d_items_fact_counts f
          ON d.linksto = f.linksto AND d.itemid = f.itemid
        WHERE d.linksto IN (
          'chartevents', 'datetimeevents', 'ingredientevents',
          'inputevents', 'outputevents', 'procedureevents'
        )
        GROUP BY d.linksto
        ORDER BY d.linksto
        """,
    )
    write_csv(counts, TABLES / "d_items_interface_reconciliation.csv")
    target = qdf(
        con,
        """
        SELECT
          d.linksto, d.itemid, d.label,
          coalesce(f.fact_rows_n, 0)::BIGINT AS fact_rows_n
        FROM d_items_all d
        LEFT JOIN d_items_fact_counts f
          ON d.linksto = f.linksto AND d.itemid = f.itemid
        WHERE d.linksto = 'inputevents' AND d.itemid = 225925
        """,
    )
    write_csv(target, TABLES / "inputevents_225925_reproduction.csv")
    reproduced = (
        len(target) == 1
        and int(target.iloc[0]["fact_rows_n"]) == 0
        and str(target.iloc[0]["label"]).strip().lower()
        == "potassium phosphate"
    )
    if not reproduced:
        raise RuntimeError("Failed to reproduce d_items/inputevents 225925")
    result = {
        "zero_fact_items_n": int(len(orphan)),
        "inputevents_225925_reproduced": bool(reproduced),
    }
    LOG(f"DONE d_items interface audit {result}")
    return result


def summarize_supplied_whitelists() -> dict[str, object]:
    LOG("START complete parse of supplied MIMIC/eICU whitelists")
    mimic = pd.read_csv(
        ND03_MIMIC_WHITELIST, dtype=str, keep_default_na=False
    )
    eicu = pd.read_csv(
        ND03_EICU_WHITELIST, dtype=str, keep_default_na=False
    )
    for column in ("rows_n", "stays_n", "positive_rows_n"):
        converted = pd.to_numeric(eicu[column], errors="coerce")
        if converted.isna().any():
            raise RuntimeError(
                f"Supplied eICU whitelist has nonnumeric {column}"
            )
        eicu[column] = converted.astype("int64")

    mimic_summary = (
        mimic.groupby(
            ["source_table", "role", "tier", "semantics"],
            dropna=False,
        )
        .size()
        .reset_index(name="labels_n")
        .sort_values(["source_table", "role", "tier"])
    )
    eicu_summary = (
        eicu.groupby(
            ["source_table", "role", "tier", "semantics"],
            dropna=False,
        )
        .agg(
            labels_n=("label", "size"),
            rows_n=("rows_n", "sum"),
            stays_n_sum=("stays_n", "sum"),
            positive_rows_n=("positive_rows_n", "sum"),
        )
        .reset_index()
        .sort_values(["source_table", "role", "tier"])
    )
    write_csv(mimic_summary, TABLES / "nd03_mimic_whitelist_summary.csv")
    write_csv(eicu_summary, TABLES / "eicu_interface_semantic_summary.csv")

    members = []
    with zipfile.ZipFile(EICU_ZIP) as archive:
        for info in archive.infolist():
            lower = info.filename.lower()
            if any(
                token in lower
                for token in (
                    "medication.csv.gz",
                    "infusiondrug.csv.gz",
                    "intakeoutput.csv.gz",
                    "treatment.csv.gz",
                    "patient.csv.gz",
                )
            ):
                members.append(
                    {
                        "member": info.filename,
                        "compressed_size": info.compress_size,
                        "uncompressed_size": info.file_size,
                    }
                )
    members_frame = pd.DataFrame(members).sort_values("member")
    write_csv(members_frame, TABLES / "eicu_relevant_zip_members.csv")
    result = {
        "mimic_whitelist_rows_n": int(len(mimic)),
        "eicu_whitelist_rows_n": int(len(eicu)),
        "eicu_relevant_zip_members_n": int(len(members)),
    }
    LOG(f"DONE supplied whitelist parse {result}")
    return result


def render_report(
    full_emar: dict[str, object],
    candidates: dict[str, int],
    d_items: dict[str, object],
    supplied: dict[str, object],
) -> str:
    full_dist = pd.read_csv(TABLES / "emar_full_event_txt_distribution.csv")
    poe = pd.read_csv(TABLES / "emar_full_poe_link_summary.csv")
    denominator = pd.read_csv(
        TABLES / "emar_decision_denominator_by_class.csv"
    )
    detail = pd.read_csv(TABLES / "emar_detail_availability_by_class.csv")
    orphan = pd.read_csv(TABLES / "d_items_zero_fact_rows_complete.csv")
    eicu = pd.read_csv(TABLES / "eicu_interface_semantic_summary.csv")
    return "\n".join(
        [
            "# 01 — Frozen-interface and mandatory full-table audit",
            "",
            "This report was generated after the contract and whitelist hashes",
            "were frozen and before any published-association outcome model.",
            "",
            "## Full eMAR event_txt distribution and POE linkage",
            "",
            f"- Full eMAR rows: {int(full_emar['emar_rows_n']):,}",
            f"- Distribution sum: {int(full_emar['distribution_sum_n']):,}",
            f"- Reconciles: {full_emar['distribution_reconciles']}",
            "",
            "```text",
            poe.to_string(index=False),
            "```",
            "",
            "```text",
            full_dist.to_string(index=False),
            "```",
            "",
            "## Frozen medication event semantics",
            "",
            "Flushed, Confirmed, and blank/null events remain separate and",
            "outside the given/not-given decision denominator.",
            "",
            "```text",
            denominator.to_string(index=False),
            "```",
            "",
            "## eMAR-detail availability",
            "",
            "`dose_given` is the administered-dose field. `dose_due` is",
            "reported but never substituted for actual dose. MIMIC-IV has no",
            "dedicated structured 'reason not given' field; the available",
            "proxies are event_txt, complete_dose_not_given,",
            "administration_type, barcode_type, and reason_for_no_barcode.",
            "",
            "```text",
            detail.to_string(index=False),
            "```",
            "",
            "## d_items entries with zero fact rows",
            "",
            f"- Complete zero-row list: {len(orphan):,} entries.",
            "- inputevents itemid 225925 Potassium Phosphate reproduced with",
            "  zero fact rows.",
            "",
            "## eICU semantic contrast",
            "",
            "eICU is summarized only as interface semantics, not external",
            "validation.",
            "",
            "```text",
            eicu.to_string(index=False),
            "```",
            "",
            "## Machine-readable audit summary",
            "",
            "```text",
            str(
                {
                    **full_emar,
                    **candidates,
                    **d_items,
                    **supplied,
                }
            ),
            "```",
            "",
        ]
    )


def main() -> None:
    started = time.time()
    ensure_dirs()
    freeze = verify_frozen_contract()
    write_csv(freeze, MANIFESTS / "frozen_contract_verification.csv")

    source_paths = [
        MIMIC_ROOT / "hosp" / "emar.csv.gz",
        MIMIC_ROOT / "hosp" / "emar_detail.csv.gz",
        MIMIC_ROOT / "hosp" / "poe.csv.gz",
        MIMIC_ROOT / "hosp" / "prescriptions.csv.gz",
        MIMIC_ROOT / "icu" / "d_items.csv.gz",
        MIMIC_ROOT / "icu" / "chartevents.csv.gz",
        MIMIC_ROOT / "icu" / "datetimeevents.csv.gz",
        MIMIC_ROOT / "icu" / "ingredientevents.csv.gz",
        MIMIC_ROOT / "icu" / "inputevents.csv.gz",
        MIMIC_ROOT / "icu" / "outputevents.csv.gz",
        MIMIC_ROOT / "icu" / "procedureevents.csv.gz",
        EICU_ZIP,
        ND03_MIMIC_WHITELIST,
        ND03_EICU_WHITELIST,
    ]
    before = source_stat(source_paths)
    write_csv(before, MANIFESTS / "source_stat_before_audit.csv")

    whitelist = load_whitelist("strict")
    class_count = whitelist["drug_class"].nunique()
    if class_count != 6:
        raise RuntimeError(f"Expected six strict classes, got {class_count}")

    con = connect_duckdb()
    build_poe_identity(con)
    full_emar = full_emar_audit(con)
    build_emar_medication_candidates(con, whitelist)
    build_detail_and_product_candidates(con, whitelist)
    candidates = build_final_emar_events(con)
    summarize_emar_detail(con)
    d_items = build_d_items_orphans(con)
    supplied = summarize_supplied_whitelists()
    con.close()

    after = source_stat(source_paths)
    write_csv(after, MANIFESTS / "source_stat_after_audit.csv")
    check = before.merge(after, on="path", suffixes=("_before", "_after"))
    check["unchanged"] = (
        check["size_bytes_before"].eq(check["size_bytes_after"])
        & check["mtime_ns_before"].eq(check["mtime_ns_after"])
    )
    write_csv(check, MANIFESTS / "source_immutability_audit.csv")
    if not check["unchanged"].all():
        raise RuntimeError("One or more read-only source stats changed")

    report = render_report(full_emar, candidates, d_items, supplied)
    (REPORTS / "01_full_interface_audit.md").write_text(
        report, encoding="utf-8"
    )
    metadata = script_metadata(started, SCRIPT)
    metadata.update(
        {
            **full_emar,
            **candidates,
            **d_items,
            **supplied,
            "strict_drug_classes_n": class_count,
            "source_stats_unchanged": bool(check["unchanged"].all()),
            "full_table_not_sample": True,
            "ignore_errors": False,
        }
    )
    write_json(metadata, MANIFESTS / "01_full_interface_audit.json")
    LOG(f"DONE full interface audit elapsed={metadata['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
