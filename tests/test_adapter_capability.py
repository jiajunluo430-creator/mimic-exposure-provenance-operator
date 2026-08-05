from __future__ import annotations

import pytest

from medprov.adapters import get_adapter
from medprov.schema import load_document


def test_a1_route_construct_is_unmeasurable_not_unexposed(repo_root, local_cache):
    if not (local_cache / "n1_validity.duckdb").is_file():
        pytest.skip("private aggregate MIMIC reference cache is not available")
    spec = load_document(repo_root / "examples" / "a1_vte_admin_route_required.yaml")
    capability = get_adapter("mimic_native").capability(spec, local_cache)
    assert capability.supported is True
    assert capability.measurable is False
    assert capability.executable is False
    assert capability.dimension_status["required_metadata"] == "unmeasurable"
    assert capability.source_status["required_route_nonmissing_n"] == 0
    assert "route" in capability.missing_fields


@pytest.mark.parametrize("adapter", ["mimic_fhir", "omop", "eicu"])
def test_missing_transport_data_is_reported_not_silently_executed(repo_root, adapter):
    spec = load_document(repo_root / "examples" / "a2_ppi_strict_admin.yaml")
    spec["data_model"]["model_name"] = {
        "mimic_fhir": "MIMIC-IV-on-FHIR",
        "omop": "OMOP CDM",
        "eicu": "eICU-CRD",
    }[adapter]
    spec["data_model"]["model_version"] = "2.1" if adapter == "mimic_fhir" else "demo"
    capability = get_adapter(adapter).capability(spec, None)
    assert capability.executable is False
    assert capability.source_status["data_available"] is False
