from __future__ import annotations

from medprov.validator import load_reporting_records, validate_reporting_records


def test_frozen_40_study_structured_validator_parity(repo_root):
    records = load_reporting_records(
        repo_root
        / "outputs"
        / "literature_validator_v0_1_0"
        / "published_operator_reporting_records.jsonl"
    )
    result = validate_reporting_records(records)
    assert result["valid_records_n"] == 40
    assert result["invalid_records_n"] == 0
    assert result["dimension_counts"]["source_layer"]["reported"] == 7
    assert result["dimension_counts"]["identity_rule"]["reported"] == 2
    assert result["dimension_counts"]["time_origin_window"]["reported"] == 35
    assert result["dimension_counts"]["event_semantics_map"]["reported"] == 0
    assert result["dimension_counts"]["required_metadata"]["reported"] == 30
    assert result["operational_indicator_counts"]["complete_executable_operator"] == 0
    assert result["text_assist_used_for_primary_results"] is False
