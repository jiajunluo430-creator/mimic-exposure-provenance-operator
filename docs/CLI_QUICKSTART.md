# CLI quickstart

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\medprov.exe --version
```

On POSIX systems, replace `.venv\Scripts` with `.venv/bin`.

## Public synthetic demonstration

```powershell
medprov demo --out demo_output
```

The command writes aggregate JSON, Markdown, and HTML. Expected synthetic
counts are one exposed, one unexposed, one unresolved, and one unmeasurable
analysis unit.

## Specification validation

```powershell
medprov validate-spec examples/mimic_strict_same_poe.yaml
```

This checks schema conformance and verifies contract, code-list, and generator
hashes. It does not require MIMIC data.

## Capability and compilation

```powershell
medprov capability --spec examples/a1_vte_admin_route_required.yaml `
  --adapter mimic_native --data-root D:\path\to\local\cache

medprov compile --spec examples/mimic_strict_same_poe.yaml `
  --adapter mimic_native --data-root D:\path\to\local\cache `
  --out query_plan.json
```

Capability output keeps `adapter_supported`, `measurable`, and `executable`
separate. Compilation emits an aggregate query plan without executing it.

## Aggregate execution and comparison

```powershell
medprov execute --spec examples/mimic_strict_same_poe.yaml `
  --adapter mimic_native --data-root D:\path\to\local\cache `
  --aggregate-out strict_result

medprov compare --left strict_result/mimic.strict_same_poe.json `
  --right broad_result/mimic.broad_same_class.json --out comparison.json
```

The public CLI has no patient-level output option. Comparison reports patient-
level agreement only if a prespecified aggregate cross-classification matrix is
present; otherwise it states that the metric is unavailable.

## Reporting validator

```powershell
medprov validate-reporting structured_records/ --out reporting_report
```

Inputs are human-coded JSON/YAML records conforming to
`schemas/medication_exposure_reporting.schema.json`. The primary validator does
not infer reporting quality from article prose.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | completed successfully |
| 2 | invalid specification, input, or path |
| 3 | adapter/data combination is not executable |
| 4 | unexpected runtime failure |
