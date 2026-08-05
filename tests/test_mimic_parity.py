from __future__ import annotations

import pytest

from medprov.executor import execute_operator_file

STRICT_BY_CLASS = {
    "electrolyte_replacement": (113854, 57408),
    "insulin": (56081, 38758),
    "intra_abdominal_antibiotics": (49119, 40705),
    "prokinetic": (2329, 1855),
    "stress_ulcer_prophylaxis": (24655, 18730),
    "vte_prophylaxis": (18133, 13434),
}


def _require_cache(local_cache):
    needed = [
        local_cache / "jamia_pre_submission_v1_0.duckdb",
        local_cache / "jamia_prereview_upgrade_v1_0.duckdb",
        local_cache / "n1_validity.duckdb",
    ]
    if not all(path.is_file() for path in needed):
        pytest.skip("private aggregate MIMIC reference cache is not available")


def test_six_class_strict_parity(repo_root, local_cache):
    _require_cache(local_cache)
    result = execute_operator_file(
        repo_root / "examples" / "mimic_strict_same_poe.yaml",
        adapter_name="mimic_native",
        data_root=local_cache,
    )
    assert result.counts["analysis_units"] == 264171
    assert result.counts["exposed"] == 170890
    observed = {
        row["medication_class"]: (row["analysis_units"], row["exposed"])
        for row in result.counts["by_class"]
    }
    assert observed == STRICT_BY_CLASS


@pytest.mark.parametrize(
    ("example", "analysis_units", "exposed"),
    [
        ("a1_vte_order.yaml", 20248, 7047),
        ("a2_ppi_original_order.yaml", 2813, 655),
        ("a2_ppi_hospital_overlap_order.yaml", 2813, 776),
        ("a2_ppi_strict_admin.yaml", 2813, 518),
    ],
)
def test_anchor_exposure_parity(repo_root, local_cache, example, analysis_units, exposed):
    _require_cache(local_cache)
    result = execute_operator_file(
        repo_root / "examples" / example,
        adapter_name="mimic_native",
        data_root=local_cache,
    )
    assert result.counts["analysis_units"] == analysis_units
    assert result.counts["exposed"] == exposed
