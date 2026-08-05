# medprov: machine-executable medication-exposure provenance operators

`medprov` is a lightweight, versioned, adapter-aware specification and Python
reference implementation for medication-exposure phenotyping in electronic
health records. It treats exposure as a deterministic five-dimensional
operator—source, identity, time, event semantics, and required metadata—rather
than as a table label.

The package provides:

- Draft 2020-12 JSON Schemas and seven contract-generated YAML operators;
- one CLI for validation, capability assessment, compilation, aggregate
  execution, comparison, and reporting validation;
- MIMIC native, MIMIC-IV-on-FHIR, OMOP, eICU, and synthetic adapter interfaces;
- explicit `exposed`, `unexposed`, `unresolved`, and `unmeasurable` states;
- an aggregate-only privacy guard and public synthetic test data;
- exact local parity tests against the frozen MIMIC-IV 3.1 reference analysis.

## Quickstart

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\medprov.exe validate-spec examples\mimic_strict_same_poe.yaml
.\.venv\Scripts\medprov.exe demo --out demo_output
```

See [the CLI guide](docs/CLI_QUICKSTART.md), the
[formal method specification](METHOD_SPECIFICATION.md), and the
[adapter guide](docs/ADAPTER_AUTHORING_GUIDE.md).

## Reference evaluation

The frozen MIMIC-IV 3.1 evaluation provides an exact-parity reference, not a
new causal medication study. Verified reference results include:

- 264,171 post-deployment order units;
- 170,890 (64.69%) strict same-POE conversions and 227,355 (86.06%) same-
  class/window sensitivity conversions;
- construct-required route present for 9,940/9,940 eligible A1 order units but
  0/87,569 strict VTE eMAR events, demonstrating a source-layer measurability
  boundary;
- A2 first-48-hour PPI exposure of 655/2,813 under the original order operator,
  776/2,813 under hospital-overlap eligibility, and 518/2,813 under strict
  administration identity;
- a 40-study reporting audit in which 7 studies named a native source, 2
  supplied executable identity, and none reported a complete executable
  operator.

These results quantify exposure-definition propagation. They are not estimates
of drug efficacy, harm, optimal treatment, or external clinical validation.

## Data boundary

No MIMIC-IV/eICU raw data, identifiers, stay-level rows, or patient-level
cohorts are distributed. Credentialed users obtain data directly from
PhysioNet. The public executor emits aggregate outputs only. See
[SECURITY_PRIVACY.md](SECURITY_PRIVACY.md).

For licensed local reproduction, define the source/cache paths and run the
reference pipeline under `scripts/`. The original frozen analysis remains in
place as a reference pipeline; `medprov` does not rewrite its scientific
contract.

## Repository layout

- `schemas/`, `examples/`: versioned specification and generated operators;
- `src/medprov/`: compiler, executor, validator, reports, and adapters;
- `tests/`: synthetic, schema, CLI, capability, privacy, and local parity tests;
- `contracts/`, `config/`: frozen scientific and implementation definitions;
- `scripts/`: generator and original reproducible reference pipeline;
- `outputs/`, `reports/`, `figures/`: patient-free aggregate evidence;
- `docs/`: CLI and adapter documentation.

Repository: https://github.com/jiajunluo430-creator/mimic-exposure-provenance-operator
