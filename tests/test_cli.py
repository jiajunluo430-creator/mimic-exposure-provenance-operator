from __future__ import annotations

import json

from medprov.cli import EXIT_INVALID, EXIT_OK, main


def test_validate_spec_cli(repo_root, capsys):
    code = main(["validate-spec", str(repo_root / "examples" / "mimic_strict_same_poe.yaml")])
    captured = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert captured["syntactically_valid"] is True
    assert captured["reproducible_traceable"] is True


def test_demo_cli_writes_three_format_bundle(tmp_path, capsys):
    code = main(["demo", "--out", str(tmp_path)])
    captured = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert captured["counts"]["analysis_units"] == 4
    assert captured["counts"]["exposed"] == 1
    assert captured["counts"]["unexposed"] == 1
    assert captured["counts"]["unresolved"] == 1
    assert captured["counts"]["unmeasurable"] == 1
    assert {path.suffix for path in tmp_path.iterdir()} == {".json", ".md", ".html"}


def test_invalid_cli_path_returns_invalid(capsys):
    code = main(["validate-spec", "does-not-exist.yaml"])
    assert code == EXIT_INVALID
    assert "invalid" in capsys.readouterr().err
