# Upgrade state audit

Audit date: 2026-08-05. Branch: `codex/executable-provenance-method-upgrade`.

## Repository decision

The parent analysis directory is not used as a new Git repository. The existing patient-free repository under `release/mimic-exposure-provenance-operator` is the upgrade repository because it already contains commit `294b93a`, the pushed JAMIA-era artifacts, a clean worktree, and the public-release validation history. Local branch `archive/jamia-submitted-2026-08-01` and annotated tag `jamia-submitted-2026-08-01` freeze the baseline. No external push was performed.

## Data and implementation gates

| Component | Status | Evidence/decision |
|---|---|---|
| JAMIA portal package | PRESENT | Frozen outside this public repository; retained unchanged |
| Patient-free reproducibility release | PRESENT | Validator passed: 352 files, 351 manifest entries, zero failures |
| Existing frozen scripts/contracts/aggregate outputs | PRESENT | Native audit, A1/A2, POE timing, literature landscape available |
| scripts 39–45 | PARTIAL | Parent project has 39–45; public release intentionally contains validator and reproducible analysis subset |
| Formal operator JSON Schema/YAML examples | MISSING | Required Phase 1 output |
| Installable Python package and unified CLI | MISSING | Required Phase 1 output |
| Adapter API and canonical intermediate representation | MISSING | Required Phase 1 output |
| Automated test suite/CI/build artifacts | MISSING | Required Phase 1/8 output |
| MIMIC-IV 3.1 native data | PRESENT | Read-only local source and materialized DuckDB reference pipeline |
| eICU-CRD 2.0 | PRESENT | Read-only local ZIP |
| Matched MIMIC-IV native 2.2 | MISSING | Blocks exact FHIR parity |
| MIMIC-IV-on-FHIR 2.1 | MISSING | Adapter/synthetic tests only unless obtained |
| Matched native/FHIR demo | MISSING | Adapter/synthetic tests only unless obtained |
| MIMIC-IV OMOP demo v0.9 | MISSING | Synthetic capability/semantic-loss test remains possible |
| Independent second-coder results | MISSING | Blank packet only; agreement cannot be reported |
| Python/R runtime | PRESENT | Python 3.13 with DuckDB/pandas/matplotlib; R 4.5.2 |
| Disk headroom | PARTIAL | Approximately 16 GB at audit; discourages unplanned large downloads/materializations |

## Already-complete evidence

- 264,171 post-deployment order units.
- 170,890 strict same-POE conversions.
- 227,355 broad same-class/window conversions.
- 183/183 primary POE units linked to raw POE.
- Median prescription-POE minus first administration: +97.18 h.
- Median eMAR-POE minus first administration: -5.68 h.
- Median prescription-POE minus eMAR-POE: +106.10 h.
- Independent recoding remains `AUTHOR_ACTION_REQUIRED_SECOND_CODER`.

Status: Phase 0 audit complete; new-result execution remains prohibited until the master contract hash is recorded.

