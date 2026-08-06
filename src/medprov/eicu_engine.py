"""Streaming eICU same-class/window reconciliation under the frozen contract."""

from __future__ import annotations

import csv
import gzip
import io
import math
import re
import statistics
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from medprov.identity import classify_strings, load_name_rules

CLASSES = (
    "stress_ulcer_prophylaxis",
    "vte_prophylaxis",
    "intra_abdominal_antibiotics",
    "electrolyte_replacement",
    "prokinetic",
    "insulin",
)


@dataclass(frozen=True)
class OrderUnit:
    order_id: str
    stay_id: str
    medication_class: str
    start: float | None
    stop: float | None
    hospital_id: str
    unit_type: str
    route_available: bool
    dose_available: bool
    frequency_available: bool

    @property
    def valid_interval(self) -> bool:
        return self.start is not None and self.stop is not None and self.stop >= self.start


@dataclass(frozen=True)
class AdministrationEvent:
    event_id: str
    stay_id: str
    medication_class: str
    offset: float
    hospital_id: str
    unit_type: str
    value_fields_available_n: int


class FrozenClassifier:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.rules = load_name_rules(spec)
        expression = "|".join(f"(?:{rule.positive.pattern})" for rule in self.rules)
        self.prefilter = re.compile(expression, flags=re.IGNORECASE)

    def classify(self, value: object) -> tuple[str | None, str, set[str]]:
        text = str(value or "").strip()
        if not text or not self.prefilter.search(text):
            return None, "unmapped", set()
        matched: set[str] = set()
        for rule in self.rules:
            if rule.positive.search(text) and not (
                rule.negative is not None and rule.negative.search(text)
            ):
                matched.add(rule.medication_class)
        medication_class, state = classify_strings([text], self.rules)
        return medication_class, state, matched


def parse_number(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def percentile(values: list[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def find_member(archive: zipfile.ZipFile, basename: str) -> str:
    target = basename.lower()
    matches = [name for name in archive.namelist() if Path(name).name.lower() == target]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected exactly one {basename} in eICU ZIP; found {len(matches)}")
    return matches[0]


def iter_nested_gzip_csv(
    archive: zipfile.ZipFile, basename: str
) -> tuple[list[str], Iterable[dict[str, str]]]:
    member = find_member(archive, basename)
    raw = archive.open(member)
    compressed = gzip.GzipFile(fileobj=raw)
    text = io.TextIOWrapper(compressed, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text)

    def rows() -> Iterable[dict[str, str]]:
        try:
            yield from reader
        finally:
            text.close()
            compressed.close()
            raw.close()

    return list(reader.fieldnames or []), rows()


def emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def stream_patient_map(
    archive: zipfile.ZipFile, progress: Callable[[str], None] | None
) -> tuple[dict[str, tuple[str, str]], dict[str, Any]]:
    started = time.perf_counter()
    fields, rows = iter_nested_gzip_csv(archive, "patient.csv.gz")
    mapping: dict[str, tuple[str, str]] = {}
    total = 0
    missing_hospital = 0
    for row in rows:
        total += 1
        stay = str(row.get("patientunitstayid", "")).strip()
        hospital = str(row.get("hospitalid", "")).strip()
        unit_type = str(row.get("unittype", "")).strip() or "<blank>"
        if not hospital:
            missing_hospital += 1
        if stay:
            mapping[stay] = (hospital, unit_type)
    emit(progress, f"CHECKPOINT patient rows={total} stays={len(mapping)}")
    return mapping, {
        "source": "patient",
        "rows_n": total,
        "unique_units_n": len(mapping),
        "class_mapped_rows_n": "not_applicable",
        "ambiguous_identity_rows_n": "not_applicable",
        "unresolved_numeric_rows_n": "not_applicable",
        "missing_hospital_rows_n": missing_hospital,
        "fields_n": len(fields),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }


def stream_orders(
    archive: zipfile.ZipFile,
    patient_map: dict[str, tuple[str, str]],
    classifier: FrozenClassifier,
    progress: Callable[[str], None] | None,
) -> tuple[
    dict[tuple[str, str], OrderUnit],
    dict[str, Any],
    Counter[str],
    Counter[tuple[str, str]],
]:
    started = time.perf_counter()
    fields, rows = iter_nested_gzip_csv(archive, "medication.csv.gz")
    units: dict[tuple[str, str], OrderUnit] = {}
    total = 0
    mapped = 0
    ambiguous = 0
    duplicate_units = 0
    ambiguous_by_class: Counter[str] = Counter()
    ambiguous_labels: Counter[tuple[str, str]] = Counter()
    for row in rows:
        total += 1
        if total % 500_000 == 0:
            emit(progress, f"CHECKPOINT medication rows={total} retained_units={len(units)}")
        medication_class, identity_state, matched_classes = classifier.classify(
            row.get("drugname", "")
        )
        if medication_class is None:
            if identity_state == "ambiguous":
                ambiguous += 1
                for item in matched_classes:
                    ambiguous_by_class[item] += 1
                ambiguous_labels[
                    (str(row.get("drugname", "")).strip(), "|".join(sorted(matched_classes)))
                ] += 1
            continue
        mapped += 1
        order_id = str(row.get("medicationid", "")).strip() or f"row-{total}"
        stay = str(row.get("patientunitstayid", "")).strip()
        hospital, unit_type = patient_map.get(stay, ("", "<unknown>"))
        start = parse_number(row.get("drugstartoffset"))
        if start is None:
            start = parse_number(row.get("drugorderoffset"))
        stop = parse_number(row.get("drugstopoffset"))
        unit = OrderUnit(
            order_id=order_id,
            stay_id=stay,
            medication_class=medication_class,
            start=start,
            stop=stop,
            hospital_id=hospital,
            unit_type=unit_type,
            route_available=bool(str(row.get("routeadmin", "")).strip()),
            dose_available=bool(str(row.get("dosage", "")).strip()),
            frequency_available=bool(str(row.get("frequency", "")).strip()),
        )
        key = (order_id, medication_class)
        if key in units:
            duplicate_units += 1
            previous = units[key]
            starts = [value for value in (previous.start, unit.start) if value is not None]
            stops = [value for value in (previous.stop, unit.stop) if value is not None]
            units[key] = OrderUnit(
                order_id=previous.order_id,
                stay_id=previous.stay_id or unit.stay_id,
                medication_class=medication_class,
                start=min(starts) if starts else None,
                stop=max(stops) if stops else None,
                hospital_id=previous.hospital_id or unit.hospital_id,
                unit_type=(
                    previous.unit_type if previous.unit_type != "<unknown>" else unit.unit_type
                ),
                route_available=previous.route_available or unit.route_available,
                dose_available=previous.dose_available or unit.dose_available,
                frequency_available=previous.frequency_available or unit.frequency_available,
            )
        else:
            units[key] = unit
    emit(progress, f"CHECKPOINT medication COMPLETE rows={total} retained_units={len(units)}")
    return units, {
        "source": "medication",
        "rows_n": total,
        "unique_units_n": len(units),
        "class_mapped_rows_n": mapped,
        "ambiguous_identity_rows_n": ambiguous,
        "duplicate_units_collapsed_n": duplicate_units,
        "unresolved_numeric_rows_n": "not_applicable",
        "missing_hospital_rows_n": sum(not unit.hospital_id for unit in units.values()),
        "fields_n": len(fields),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }, ambiguous_by_class, ambiguous_labels


def stream_administrations(
    archive: zipfile.ZipFile,
    patient_map: dict[str, tuple[str, str]],
    classifier: FrozenClassifier,
    progress: Callable[[str], None] | None,
) -> tuple[
    dict[tuple[str, str], AdministrationEvent],
    dict[str, Any],
    Counter[str],
    Counter[str],
    Counter[tuple[str, str]],
]:
    started = time.perf_counter()
    fields, rows = iter_nested_gzip_csv(archive, "infusionDrug.csv.gz")
    events: dict[tuple[str, str], AdministrationEvent] = {}
    total = 0
    mapped = 0
    ambiguous = 0
    failed_numeric_gate = 0
    duplicate_events = 0
    ambiguous_by_class: Counter[str] = Counter()
    unresolved_by_class: Counter[str] = Counter()
    ambiguous_labels: Counter[tuple[str, str]] = Counter()
    for row in rows:
        total += 1
        if total % 500_000 == 0:
            emit(progress, f"CHECKPOINT infusionDrug rows={total} retained_events={len(events)}")
        medication_class, identity_state, matched_classes = classifier.classify(
            row.get("drugname", "")
        )
        if medication_class is None:
            if identity_state == "ambiguous":
                ambiguous += 1
                for item in matched_classes:
                    ambiguous_by_class[item] += 1
                ambiguous_labels[
                    (str(row.get("drugname", "")).strip(), "|".join(sorted(matched_classes)))
                ] += 1
            continue
        mapped += 1
        stay = str(row.get("patientunitstayid", "")).strip()
        offset = parse_number(row.get("infusionoffset"))
        values = [
            parse_number(row.get(field))
            for field in ("drugrate", "infusionrate", "drugamount", "volumeoffluid")
        ]
        positive_values = [value for value in values if value is not None and value > 0]
        if not stay or offset is None or not positive_values:
            failed_numeric_gate += 1
            unresolved_by_class[medication_class] += 1
            continue
        event_id = str(row.get("infusiondrugid", "")).strip() or f"row-{total}"
        hospital, unit_type = patient_map.get(stay, ("", "<unknown>"))
        event = AdministrationEvent(
            event_id=event_id,
            stay_id=stay,
            medication_class=medication_class,
            offset=offset,
            hospital_id=hospital,
            unit_type=unit_type,
            value_fields_available_n=sum(value is not None for value in values),
        )
        key = (event_id, medication_class)
        if key in events:
            duplicate_events += 1
        else:
            events[key] = event
    emit(progress, f"CHECKPOINT infusionDrug COMPLETE rows={total} retained_events={len(events)}")
    return events, {
        "source": "infusionDrug",
        "rows_n": total,
        "unique_units_n": len(events),
        "class_mapped_rows_n": mapped,
        "ambiguous_identity_rows_n": ambiguous,
        "duplicate_units_collapsed_n": duplicate_events,
        "unresolved_numeric_rows_n": failed_numeric_gate,
        "missing_hospital_rows_n": sum(not event.hospital_id for event in events.values()),
        "fields_n": len(fields),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }, ambiguous_by_class, unresolved_by_class, ambiguous_labels


def stream_documentation_sources(
    archive: zipfile.ZipFile, progress: Callable[[str], None] | None
) -> list[dict[str, Any]]:
    results = []
    for source in ("hospital.csv.gz", "treatment.csv.gz"):
        started = time.perf_counter()
        fields, rows = iter_nested_gzip_csv(archive, source)
        total = sum(1 for _ in rows)
        role = "lookup_only" if source.startswith("hospital") else "documentation_only"
        results.append(
            {
                "source": source.removesuffix(".csv.gz"),
                "rows_n": total,
                "unique_units_n": "not_applicable",
                "class_mapped_rows_n": "not_evaluated_by_contract",
                "ambiguous_identity_rows_n": "not_applicable",
                "unresolved_numeric_rows_n": "not_applicable",
                "missing_hospital_rows_n": "not_applicable",
                "fields_n": len(fields),
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "source_role": role,
            }
        )
        emit(progress, f"CHECKPOINT {source} COMPLETE rows={total} role={role}")
    results.append(
        {
            "source": "intakeOutput",
            "rows_n": "not_scanned",
            "unique_units_n": "not_applicable",
            "class_mapped_rows_n": "not_evaluated_by_contract",
            "ambiguous_identity_rows_n": "not_applicable",
            "unresolved_numeric_rows_n": "not_applicable",
            "missing_hospital_rows_n": "not_applicable",
            "fields_n": "not_scanned",
            "elapsed_seconds": 0,
            "source_role": "excluded_no_frozen_construct",
        }
    )
    return results


def order_metadata_rows(orders: Iterable[OrderUnit]) -> list[dict[str, Any]]:
    grouped: dict[str, list[OrderUnit]] = defaultdict(list)
    for order in orders:
        grouped[order.medication_class].append(order)
    rows = []
    for medication_class in CLASSES:
        subset = grouped[medication_class]
        n = len(subset)
        metrics = {
            "start_offset": sum(order.start is not None for order in subset),
            "stop_offset": sum(order.stop is not None for order in subset),
            "valid_interval": sum(order.valid_interval for order in subset),
            "route": sum(order.route_available for order in subset),
            "dose": sum(order.dose_available for order in subset),
            "frequency": sum(order.frequency_available for order in subset),
        }
        for dimension, available in metrics.items():
            rows.append(
                {
                    "source": "medication",
                    "medication_class": medication_class,
                    "dimension": dimension,
                    "units_n": n,
                    "available_n": available,
                    "available_pct": round(100 * available / n, 6) if n else "not_evaluable",
                }
            )
    return rows


def administration_metadata_rows(
    events: Iterable[AdministrationEvent], unresolved_by_class: Counter[str]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[AdministrationEvent]] = defaultdict(list)
    for event in events:
        grouped[event.medication_class].append(event)
    rows = []
    for medication_class in CLASSES:
        subset = grouped[medication_class]
        n = len(subset)
        for dimension, available in (
            ("valid_offset", n),
            ("positive_rate_or_value", n),
            ("any_numeric_value_field", sum(e.value_fields_available_n > 0 for e in subset)),
        ):
            rows.append(
                {
                    "source": "infusionDrug",
                    "medication_class": medication_class,
                    "dimension": dimension,
                    "units_n": n,
                    "available_n": available,
                    "available_pct": round(100 * available / n, 6) if n else "not_evaluable",
                    "class_mapped_but_unresolved_numeric_n": unresolved_by_class[medication_class],
                }
            )
    return rows


def build_gates(
    orders: Iterable[OrderUnit],
    events: Iterable[AdministrationEvent],
    order_ambiguity: Counter[str],
    event_ambiguity: Counter[str],
) -> list[dict[str, Any]]:
    order_groups: dict[str, list[OrderUnit]] = defaultdict(list)
    event_groups: dict[str, list[AdministrationEvent]] = defaultdict(list)
    for order in orders:
        order_groups[order.medication_class].append(order)
    for event in events:
        event_groups[event.medication_class].append(event)
    rows = []
    for medication_class in CLASSES:
        class_orders = order_groups[medication_class]
        valid_orders = [order for order in class_orders if order.valid_interval]
        class_events = event_groups[medication_class]
        hospitals = {order.hospital_id for order in valid_orders if order.hospital_id} & {
            event.hospital_id for event in class_events if event.hospital_id
        }
        interval_pct = 100 * len(valid_orders) / len(class_orders) if class_orders else 0.0
        ambiguous = order_ambiguity[medication_class] + event_ambiguity[medication_class]
        gates = {
            "valid_orders_ge_100": len(valid_orders) >= 100,
            "admin_like_events_ge_100": len(class_events) >= 100,
            "hospitals_with_both_ge_10": len(hospitals) >= 10,
            "valid_interval_ge_80pct": interval_pct >= 80,
            "identity_unambiguous": ambiguous == 0,
        }
        rows.append(
            {
                "medication_class": medication_class,
                "class_mapped_orders_n": len(class_orders),
                "time_valid_orders_n": len(valid_orders),
                "valid_interval_pct": round(interval_pct, 6),
                "administration_like_events_n": len(class_events),
                "hospitals_with_both_n": len(hospitals),
                "ambiguous_identity_rows_n": ambiguous,
                **gates,
                "gate_pass": all(gates.values()),
            }
        )
    return rows


def reconcile(
    orders: Iterable[OrderUnit],
    events: Iterable[AdministrationEvent],
    gates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    gate_pass = {row["medication_class"]: bool(row["gate_pass"]) for row in gates}
    order_groups: dict[tuple[str, str], list[OrderUnit]] = defaultdict(list)
    event_groups: dict[tuple[str, str], list[AdministrationEvent]] = defaultdict(list)
    all_orders: dict[str, list[OrderUnit]] = defaultdict(list)
    all_events: dict[str, list[AdministrationEvent]] = defaultdict(list)
    for order in orders:
        all_orders[order.medication_class].append(order)
        if order.valid_interval:
            order_groups[(order.stay_id, order.medication_class)].append(order)
    for event in events:
        all_events[event.medication_class].append(event)
        event_groups[(event.stay_id, event.medication_class)].append(event)

    class_rows: list[dict[str, Any]] = []
    time_rows: list[dict[str, Any]] = []
    hospital_rows: list[dict[str, Any]] = []
    total_counts = {
        "analysis_units": 0,
        "exposed": 0,
        "unexposed": 0,
        "unresolved": 0,
        "unmeasurable": 0,
    }
    for medication_class in CLASSES:
        class_orders = all_orders[medication_class]
        valid_orders = [order for order in class_orders if order.valid_interval]
        class_events = all_events[medication_class]
        total_counts["analysis_units"] += len(class_orders)
        if not gate_pass[medication_class]:
            total_counts["unmeasurable"] += len(class_orders)
            class_rows.append(
                {
                    "medication_class": medication_class,
                    "gate_pass": False,
                    "eligible_time_valid_orders_n": len(valid_orders),
                    "converted_orders_n": "not_evaluated_gate_failed",
                    "unmatched_orders_n": "not_evaluated_gate_failed",
                    "conversion_pct": "not_evaluated_gate_failed",
                    "administration_like_events_n": len(class_events),
                    "assigned_events_n": "not_evaluated_gate_failed",
                    "unmatched_events_n": "not_evaluated_gate_failed",
                    "ambiguous_tie_events_n": "not_evaluated_gate_failed",
                }
            )
            continue

        assigned: dict[str, list[AdministrationEvent]] = defaultdict(list)
        unmatched_events = 0
        ambiguous_ties = 0
        for (stay, event_class), stay_events in event_groups.items():
            if event_class != medication_class:
                continue
            candidates_orders = order_groups.get((stay, event_class), [])
            for event in stay_events:
                candidates = [
                    order
                    for order in candidates_orders
                    if order.start is not None
                    and order.stop is not None
                    and order.start - 120 <= event.offset <= order.stop + 360
                ]
                if not candidates:
                    unmatched_events += 1
                    continue
                if len(candidates) == 1:
                    chosen = candidates[0]
                else:
                    nonfuture = [
                        order
                        for order in candidates
                        if order.start is not None and order.start <= event.offset
                    ]
                    if not nonfuture:
                        ambiguous_ties += 1
                        continue
                    closest_start = max(order.start for order in nonfuture if order.start is not None)
                    closest = [order for order in nonfuture if order.start == closest_start]
                    if len(closest) != 1:
                        ambiguous_ties += 1
                        continue
                    chosen = closest[0]
                assigned[chosen.order_id].append(event)
        converted = [order for order in valid_orders if assigned.get(order.order_id)]
        unconverted = len(valid_orders) - len(converted)
        invalid = len(class_orders) - len(valid_orders)
        total_counts["exposed"] += len(converted)
        total_counts["unexposed"] += unconverted
        total_counts["unmeasurable"] += invalid
        assigned_event_ids = {
            event.event_id
            for order_events in assigned.values()
            for event in order_events
        }
        delays = [
            min(event.offset for event in assigned[order.order_id]) - float(order.start)
            for order in converted
            if order.start is not None
        ]
        class_rows.append(
            {
                "medication_class": medication_class,
                "gate_pass": True,
                "eligible_time_valid_orders_n": len(valid_orders),
                "converted_orders_n": len(converted),
                "unmatched_orders_n": unconverted,
                "conversion_pct": round(100 * len(converted) / len(valid_orders), 6),
                "administration_like_events_n": len(class_events),
                "assigned_events_n": len(assigned_event_ids),
                "unmatched_events_n": unmatched_events,
                "ambiguous_tie_events_n": ambiguous_ties,
            }
        )
        time_rows.append(
            {
                "medication_class": medication_class,
                "converted_orders_with_time_n": len(delays),
                "median_first_event_minus_order_start_minutes": (
                    round(statistics.median(delays), 6) if delays else "not_evaluable"
                ),
                "q1_minutes": (
                    round(value, 6)
                    if (value := percentile(delays, 0.25)) is not None
                    else "not_evaluable"
                ),
                "q3_minutes": (
                    round(value, 6)
                    if (value := percentile(delays, 0.75)) is not None
                    else "not_evaluable"
                ),
                "negative_delay_n": sum(value < 0 for value in delays),
                "beyond_stop_but_within_grace_n": sum(
                    min(event.offset for event in assigned[order.order_id]) > float(order.stop)
                    for order in converted
                    if order.stop is not None
                ),
            }
        )

        hospital_orders: dict[tuple[str, str], list[OrderUnit]] = defaultdict(list)
        for order in valid_orders:
            hospital_orders[(order.hospital_id, order.unit_type)].append(order)
        suppressed = 0
        for (hospital_id, unit_type), subset in sorted(hospital_orders.items()):
            if not hospital_id or len(subset) < 10:
                suppressed += 1
                continue
            converted_n = sum(bool(assigned.get(order.order_id)) for order in subset)
            hospital_rows.append(
                {
                    "medication_class": medication_class,
                    "hospital_id": hospital_id,
                    "unit_type": unit_type,
                    "eligible_orders_n": len(subset),
                    "converted_orders_n": converted_n,
                    "conversion_pct": round(100 * converted_n / len(subset), 6),
                    "cell_suppression_threshold": 10,
                }
            )
        hospital_rows.append(
            {
                "medication_class": medication_class,
                "hospital_id": "SUPPRESSED_CELLS_SUMMARY",
                "unit_type": "all",
                "eligible_orders_n": "not_released",
                "converted_orders_n": "not_released",
                "conversion_pct": "not_released",
                "cell_suppression_threshold": 10,
                "suppressed_hospital_unit_cells_n": suppressed,
            }
        )
    return class_rows, time_rows, hospital_rows, total_counts


def run_eicu_reconciliation(
    data_root: str | Path,
    spec: dict[str, Any],
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    path = Path(data_root)
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise FileNotFoundError(f"Frozen eICU ZIP is unavailable: {path}")
    classifier = FrozenClassifier(spec)
    emit(progress, f"CHECKPOINT START zip_bytes={path.stat().st_size}")
    with zipfile.ZipFile(path) as archive:
        patient_map, patient_source = stream_patient_map(archive, progress)
        orders, order_source, order_ambiguity, order_ambiguous_labels = stream_orders(
            archive, patient_map, classifier, progress
        )
        (
            events,
            event_source,
            event_ambiguity,
            unresolved_by_class,
            event_ambiguous_labels,
        ) = stream_administrations(archive, patient_map, classifier, progress)
        documentation = stream_documentation_sources(archive, progress)
    gates = build_gates(orders.values(), events.values(), order_ambiguity, event_ambiguity)
    class_results, time_results, hospital_results, counts = reconcile(
        orders.values(), events.values(), gates
    )
    metadata = order_metadata_rows(orders.values()) + administration_metadata_rows(
        events.values(), unresolved_by_class
    )
    source_rows = [patient_source, order_source, event_source, *documentation]
    ambiguous_labels = [
        {
            "source": source,
            "raw_label": label,
            "matched_classes": matched_classes,
            "rows_n": count,
        }
        for source, counter in (
            ("medication", order_ambiguous_labels),
            ("infusionDrug", event_ambiguous_labels),
        )
        for (label, matched_classes), count in sorted(counter.items())
    ]
    gate_by_class = {row["medication_class"]: bool(row["gate_pass"]) for row in gates}
    result: dict[str, Any] = {
        "status": "executed",
        "aggregate_only": True,
        "claim_boundary": "interface semantic comparison; not external validation",
        "counts": counts,
        "metrics": {
            "classes_passed_n": sum(gate_by_class.values()),
            "classes_failed_n": len(gate_by_class) - sum(gate_by_class.values()),
            "classes_passed": sorted(key for key, value in gate_by_class.items() if value),
            "native_cross_source_key": False,
            "match_mode": "same_class_window",
            "elapsed_seconds": round(time.perf_counter() - started, 6),
        },
        "source_observability": source_rows,
        "metadata_availability": metadata,
        "feasibility_gates": gates,
        "class_reconciliation": class_results,
        "time_displacement": time_results,
        "hospital_unit_heterogeneity": hospital_results,
        "ambiguous_identity_labels": ambiguous_labels,
    }
    emit(
        progress,
        "CHECKPOINT COMPLETE "
        f"classes_passed={result['metrics']['classes_passed_n']} "
        f"elapsed_seconds={result['metrics']['elapsed_seconds']}",
    )
    return result
