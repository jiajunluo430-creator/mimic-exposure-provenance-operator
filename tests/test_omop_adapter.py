from __future__ import annotations

from copy import deepcopy

from medprov.adapters import get_adapter
from medprov.schema import load_document


def strict_administration_spec(repo_root):
    spec = deepcopy(
        load_document(repo_root / "examples" / "transport" / "omop_demo_ppi.yaml")
    )
    spec["operator_id"] = "test.omop_strict_administration"
    spec["target_event"] = "documented_administration"
    spec["source_layer"]["source_type"] = "administration"
    spec["event_semantics_map"] = {
        "positive": ["administered", "delayed administered", "partial administered"],
        "negative": ["not given", "held", "refused"],
        "excluded": ["flushed", "confirmed", "<blank>"],
        "unresolved": ["<all_other>"],
        "precedence": "source_priority",
        "normalization": {"trim": True, "lowercase": True, "null_token": "<blank>"},
    }
    spec["required_metadata"]["status"] = "required"
    return spec


def test_omop_extension_preserves_four_state_classification(repo_root, fixture_dir):
    spec = strict_administration_spec(repo_root)
    source = fixture_dir / "omop" / "drug_exposure_with_extension.csv"

    result = get_adapter("omop").execute(spec, source)

    assert result.status == "executed"
    assert result.counts == {
        "analysis_units": 4,
        "exposed": 1,
        "unexposed": 1,
        "unresolved": 1,
        "unmeasurable": 1,
    }
    assert result.metrics["event_state_available_rows"] == 3


def test_omop_extension_ablation_is_unmeasurable_not_unexposed(repo_root, fixture_dir):
    spec = strict_administration_spec(repo_root)
    source = fixture_dir / "omop" / "drug_exposure_without_extension.csv"

    result = get_adapter("omop").execute(spec, source)

    assert result.status == "unmeasurable"
    assert result.executable is False
    assert result.counts == {
        "analysis_units": 4,
        "exposed": 0,
        "unexposed": 0,
        "unresolved": 0,
        "unmeasurable": 4,
    }
