# Contributing

Contributions are welcome when they preserve the scientific and privacy
contracts.

1. Create a focused branch and add or update tests.
2. Do not change frozen example definitions to improve empirical results.
3. Regenerate examples with `scripts/46_generate_operator_specs.py`; never edit
   generated YAML manually.
4. Run `ruff check src tests scripts/46_generate_operator_specs.py`,
   `mypy src/medprov`, `pytest`, and `python -m build`.
5. Confirm that no patient-level data, credentials, absolute local paths, or
   restricted identifiers enter the proposed public artifact.
6. Document adapter source roles, version gates, unsupported dimensions, and
   semantic loss explicitly.

Clinical-effectiveness claims, outcome-driven operator selection, and changes
to the six frozen medication classes are outside the scope of this repository.
