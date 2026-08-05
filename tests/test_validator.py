from __future__ import annotations

from copy import deepcopy

import pytest

from medprov.schema import load_document
from medprov.utils import assert_public_aggregate
from medprov.validator import load_reporting_records, validate_reporting_records


def test_structured_reporting_validator(fixture_dir):
    records = load_reporting_records(fixture_dir / "reporting_record.json")
    result = validate_reporting_records(records)
    assert result["records_n"] == 1
    assert result["valid_records_n"] == 1
    assert result["dimension_counts"]["source_layer"]["reported"] == 1
    assert result["dimension_counts"]["event_semantics_map"]["missing"] == 1
    assert result["operational_indicator_counts"] == {
        "named_native_source": 1,
        "executable_identity": 1,
        "complete_executable_operator": 0,
    }


def test_reporting_validator_rejects_missing_operational_indicators(fixture_dir):
    record = deepcopy(load_document(fixture_dir / "reporting_record.json"))
    record.pop("operational_indicators")
    result = validate_reporting_records([record])
    assert result["invalid_records_n"] == 1


def test_public_aggregate_guard_blocks_native_identifiers():
    with pytest.raises(ValueError, match="restricted key"):
        assert_public_aggregate({"counts": {"subject_id": 123}})
    assert_public_aggregate({"counts": {"analysis_units": 123, "exposed": 40}})
