# Medication-exposure provenance operator specification

Version: 1.0.0  
Software reference implementation: `medprov` 0.1.0  
Frozen evaluation contract: `contracts/UPGRADE_MASTER_CONTRACT_v1.0_2026-08-05.md`

## 1. Purpose

A medication exposure in an electronic health record is not identified by a
table name alone. It is the result of a deterministic operator that states
which clinical-data layer is observed, how medication identity is established,
which time origin and window apply, how native event states are interpreted,
and which dose/route metadata the clinical construct requires.

The operator is written

\[
O=(S,I,T,E,M), \qquad C_u = O(R_u),
\]

where `R_u` is the set of source records eligible for analysis unit `u` and
`C_u` is one of `exposed`, `unexposed`, `unresolved`, or `unmeasurable`.
The five required dimensions are:

1. `source_layer` (`S`): source resources, clinical role, and observability;
2. `identity_rule` (`I`): vocabulary, code list, native keys, deduplication,
   revision handling, and match mode;
3. `time_origin_window` (`T`): origin, assignment timestamp, boundaries,
   grace periods, and censoring;
4. `event_semantics_map` (`E`): literal positive, negative, excluded, and
   unresolved states plus precedence rules;
5. `required_metadata` (`M`): route, dose, unit, frequency, status, constraints,
   and missing-data policy.

The envelope fields (schema and operator versions, construct, analysis unit,
target event, adapter, output profile, and provenance) describe execution but
do not add a sixth scientific dimension.

## 2. Inputs and canonical intermediate representation

An adapter reads native records and maps them locally to a canonical event
representation. The complete local representation may include:

`subject_key`, `encounter_key`, `analysis_unit_key`, `medication_class`,
`ingredient`, `source_layer`, `native_record_id`, `native_order_id`,
`event_time`, `event_state`, `dose`, `unit`, `route`, `frequency`,
`provenance_flags`, and `classification`.

Identifiers are local-only. The public executor is aggregate-only and rejects
payloads containing native patient, encounter, stay, order, pharmacy, or eMAR
keys. Public fixtures contain synthetic identifiers only.

## 3. Deterministic classification

For each eligible analysis unit `u`, an adapter evaluates the following gates
in order.

### 3.1 Source observability gate

`G_S(u)` asks whether the required source layer was deployed and observable for
the unit. A failed gate returns the configured failure state, normally
`unmeasurable`; it does not return `unexposed`.

### 3.2 Identity predicate

`P_I(r,u)` is true when record `r` matches the frozen class/ingredient rule and
native identity rule for `u`. Exact-key matching and same-class/window matching
are distinct operators. Revisions are collapsed only at the declared
deduplication unit.

### 3.3 Time predicate

`P_T(r,u)` applies the declared time origin, assignment field, closed/open
boundaries, grace periods, and censoring. A change from ICU-window to
hospital-overlap eligibility is therefore an operator change, even if the drug
class and source table are unchanged.

### 3.4 Event-semantic predicate

`P_E(r)` maps normalized literal native states to positive, negative, excluded,
or unresolved. Source detail may override an event header when the specification
declares `detail_override`. In the frozen MIMIC implementation, `flushed`,
`confirmed`, and blank eMAR states remain separate excluded categories and do
not enter the given/not-given denominator.

### 3.5 Metadata predicate

`P_M(r)` evaluates required route, dose, unit, frequency, and status fields and
construct-specific constraints. If a required field is unavailable at the
source level, the construct is `unmeasurable`. If the field exists but the
record cannot be resolved, the configured unresolved/exclusion policy applies.

### 3.6 Output states

- `exposed`: at least one deduplicated record satisfies
  `P_I ∧ P_T ∧ P_E(positive) ∧ P_M` after `G_S` passes;
- `unexposed`: the source is observable and the analysis unit is eligible, but
  no qualifying positive record exists under the declared operator;
- `unresolved`: source records exist but identity, event state, or record-level
  metadata cannot be deterministically classified;
- `unmeasurable`: the source, adapter, deployment interval, or a construct-
  required field is unavailable, so exposure cannot be evaluated.

For an order-to-administration conversion operator, `unexposed` means “no
qualifying documented administration linked under this operator,” not proof of
no biological exposure.

## 4. Validation states

The implementation reports five separate judgments:

- `syntactically_valid`: the YAML/JSON conforms to the Draft 2020-12 schema;
- `adapter_supported`: the adapter understands all five requested dimensions;
- `measurable`: the selected dataset contains the required source and fields;
- `executable`: a classification can be generated in the current environment;
- `reproducible_traceable`: contract, code list, and generator paths resolve and
  their SHA-256 values match.

These states must not be collapsed. For example, the A1 route-required
administration operator is syntactically valid and adapter-supported, but is
unmeasurable in the evaluated MIMIC eMAR representation because route is 0%
populated among qualifying events.

## 5. Provenance trace

Every generated example stores the operator/schema version, source model and
version, author/date, binding contract path and SHA-256, code-list path and
SHA-256, and generator path and SHA-256. Execution results add the canonical
specification hash, adapter version, evaluation level, and aggregate-only flag.
The seven committed MIMIC examples are generated by
`scripts/46_generate_operator_specs.py`; manual edits are prohibited.

## 6. Why this differs from selecting a table

“Exposure from eMAR” specifies only part of `S`. It does not define medication
identity across product and ingredient fields, ICU versus hospital timing,
whether `Held`, `Confirmed`, or blank events count, whether route is required,
or what to do when the source is not deployed. Two studies can name the same
table but implement different operators; conversely, equivalent constructs can
be compiled across representations only when each dimension is explicitly
mapped and measurable.

## 7. Reference implementation boundary

MIMIC-IV native 3.1 is the exact-parity reference implementation. MIMIC-IV-on-
FHIR execution is version-gated to matched native 2.2/FHIR 2.1 or an explicitly
matched demonstration. OMOP is evaluated as a capability/semantic-loss smoke
test unless a complete eligible instance is supplied. eICU has no native
cross-source medication key and therefore cannot support exact order-to-
administration identity reconciliation. None of these evaluations constitutes
clinical external validation or a causal medication analysis.
