"""Frozen medication-name classification shared by transport adapters.

The helper deliberately returns an explicit resolution state.  Adapters must
not convert an ambiguous or unmapped source string into a negative exposure.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class NameRule:
    medication_class: str
    ingredient: str
    positive: re.Pattern[str]
    negative: re.Pattern[str] | None


def resolve_code_list(spec: dict[str, Any]) -> Path:
    """Resolve a specification-relative code list without using data roots."""

    raw = Path(str(spec["identity_rule"]["code_list"]["path"]))
    candidates = [raw]
    if not raw.is_absolute():
        candidates.extend(
            [
                Path.cwd() / raw,
                Path(__file__).resolve().parents[2] / raw,
            ]
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Frozen medication code list is unavailable: {raw}")


def load_name_rules(spec: dict[str, Any]) -> list[NameRule]:
    """Load only the predeclared tier and classes from the frozen CSV."""

    path = resolve_code_list(spec)
    tier = str(spec["identity_rule"]["code_list"].get("tier", "strict"))
    allowed_classes = {str(item) for item in spec["identity_rule"]["class_filter"]}
    rules: list[NameRule] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("tier") != tier or row.get("drug_class") not in allowed_classes:
                continue
            positive_text = str(row.get("name_regex", "")).strip()
            if not positive_text:
                continue
            negative_text = str(row.get("negative_regex", "")).strip()
            rules.append(
                NameRule(
                    medication_class=str(row["drug_class"]),
                    ingredient=str(row.get("ingredient", "")),
                    positive=re.compile(positive_text, flags=re.IGNORECASE),
                    negative=(
                        re.compile(negative_text, flags=re.IGNORECASE)
                        if negative_text
                        else None
                    ),
                )
            )
    if not rules:
        raise ValueError("The frozen code list produced no applicable medication-name rules")
    return rules


def classify_strings(values: Iterable[object], rules: Iterable[NameRule]) -> tuple[str | None, str]:
    """Return one class plus ``resolved``, ``unmapped``, or ``ambiguous``."""

    text = " | ".join(str(value).strip() for value in values if str(value).strip())
    if not text:
        return None, "unmapped"
    classes: set[str] = set()
    for rule in rules:
        if rule.positive.search(text) and not (
            rule.negative is not None and rule.negative.search(text)
        ):
            classes.add(rule.medication_class)
    if len(classes) == 1:
        return next(iter(classes)), "resolved"
    if len(classes) > 1:
        return None, "ambiguous"
    return None, "unmapped"
