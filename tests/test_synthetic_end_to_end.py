from __future__ import annotations

from medprov.cli import _demo_spec
from medprov.comparison import compare_results
from medprov.compiler import compile_operator
from medprov.executor import execute_operator


def test_synthetic_compile_and_execute(fixture_dir):
    spec = _demo_spec()
    plan = compile_operator(spec, adapter_name="synthetic", data_root=fixture_dir)
    assert plan.aggregate_only is True
    assert plan.adapter == "synthetic"
    result = execute_operator(spec, adapter_name="synthetic", data_root=fixture_dir)
    assert result.status == "executed"
    assert result.counts["analysis_units"] == 4
    assert result.counts["exposed"] == 1
    assert result.counts["unexposed"] == 1
    assert result.counts["unresolved"] == 1
    assert result.counts["unmeasurable"] == 1


def test_aggregate_compare_is_explicit_about_patient_metrics(fixture_dir):
    result = execute_operator(
        _demo_spec(), adapter_name="synthetic", data_root=fixture_dir
    ).to_dict()
    comparison = compare_results(result, result)
    assert comparison["aggregate_differences"]["exposed"] == 0
    assert comparison["patient_level_metrics"]["available"] is False
