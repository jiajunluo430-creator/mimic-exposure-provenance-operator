# medprov software validation report

**PASS_SOFTWARE_RELEASE_VALIDATION**

All 10/10 local release checks passed. The suite ran 61 tests with 0 failures and measured 86.03% branch-aware code coverage. The wheel and sdist built successfully; a fresh virtual environment installed the wheel, resolved a bundled operator's contract/code-list/generator hashes, and reproduced the deterministic four-state demo.

Adapter evidence includes exact licensed-local MIMIC parity, matched-demo native/FHIR functional execution, OMOP capability and semantic-loss execution, and aggregate-only full eICU interface-semantic execution. These levels are intentionally not labelled uniformly as external validation.

Known limitations are recorded in `software_validation_summary.json`; independent second coding and hosted CI execution remain external actions.
