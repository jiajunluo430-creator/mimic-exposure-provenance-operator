from __future__ import annotations

from copy import deepcopy

import pytest

from medprov.schema import load_document, validate_operator
from medprov.validator import validate_specification_file


def test_all_generated_examples_are_valid_and_traceable(repo_root):
    examples = sorted((repo_root / "examples").glob("*.yaml"))
    assert [path.name for path in examples] == [
        "a1_vte_admin_route_required.yaml",
        "a1_vte_order.yaml",
        "a2_ppi_hospital_overlap_order.yaml",
        "a2_ppi_original_order.yaml",
        "a2_ppi_strict_admin.yaml",
        "mimic_broad_same_class.yaml",
        "mimic_strict_same_poe.yaml",
    ]
    for path in examples:
        result = validate_specification_file(path)
        assert result.syntactically_valid, (path.name, result.errors)
        assert result.reproducible_traceable, (path.name, result.warnings)


def test_missing_core_dimension_is_rejected(repo_root):
    document = load_document(repo_root / "examples" / "mimic_strict_same_poe.yaml")
    invalid = deepcopy(document)
    invalid.pop("event_semantics_map")
    errors = validate_operator(invalid)
    assert errors
    assert any("event_semantics_map" in message for message in errors)


@pytest.mark.parametrize(
    "field",
    [
        "source_layer",
        "identity_rule",
        "time_origin_window",
        "event_semantics_map",
        "required_metadata",
    ],
)
def test_five_dimensions_are_independently_required(repo_root, field):
    document = load_document(repo_root / "examples" / "a2_ppi_strict_admin.yaml")
    document.pop(field)
    assert validate_operator(document)
