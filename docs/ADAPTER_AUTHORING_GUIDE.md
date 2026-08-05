# Adapter authoring guide

An adapter translates a five-dimensional medprov specification to a concrete
data representation without changing the clinical operator.

## Required interface

Subclass `medprov.adapters.base.BaseAdapter` and implement:

1. `inspect_source(spec, data_root)` returning available logical/native fields,
   source status, and explicit reasons;
2. `compile(spec, data_root)` returning a `QueryPlan`;
3. `execute(spec, data_root)` returning an aggregate-only `ExecutionResult`.

Register the adapter in `medprov.adapters.get_adapter` and add capability,
synthetic, path-portability, and privacy tests.

## Mapping rules

- Preserve the five core dimensions independently.
- Report absent construct-required metadata as `unmeasurable`; do not silently
  convert it to `unexposed`.
- Keep order, dispense, administration, reconciliation, and documentation
  roles distinct.
- State whether native record/order identity and revision chains survive the
  mapping.
- Compile exact-key and same-class/window identity as different plans.
- Map literal event states before any convenience collapse.
- Retain provenance extensions when a target model lacks a native field.

## Version gates

Exact cross-representation parity requires matched source releases. An adapter
must refuse or downgrade execution when versions are not comparable. The FHIR
adapter, for example, does not treat native MIMIC-IV 3.1 and FHIR 2.1 derived
from native 2.2 as an exact pair.

## Privacy contract

All public results must pass `medprov.utils.assert_public_aggregate`. Never add
patient, encounter, stay, native order, pharmacy, or eMAR identifiers to an
`ExecutionResult`. Local record traces require a separate restricted workflow
outside the public release builder.

## Minimum test matrix

- schema-valid supported spec;
- unsupported dimension or version;
- required field present and absent;
- missing data root;
- deterministic synthetic execution;
- aggregate leak guard;
- Windows and POSIX path construction;
- an exact reference result when licensed local data permit it.
