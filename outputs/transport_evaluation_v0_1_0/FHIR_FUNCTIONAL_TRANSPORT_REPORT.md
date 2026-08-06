# Matched-demo native/FHIR functional transport report

## Decision

**PASS_FUNCTIONAL_CROSS_SCHEMA**

This is a functional cross-schema evaluation on the official matched 100-patient public demos. It is not full-dataset transport validation and not clinical external validation.

## Main findings

1. **Dispense identity and six-class counts transported exactly.** Native `pharmacy` and FHIR `MedicationDispense` produced 3,870 class-mapped units, with 3,870 exact retained `pharmacy_id × medication-class` matches.
2. **Administration semantics were relocated, not preserved in the top-level status.** All 6,697 class-mapped FHIR administrations were positive under top-level `status`, whereas `dosage.method` recovered 5,740 strict-positive events; native eMAR yielded 5,696. Thus `status=completed` alone cannot reproduce the native strict event operator.
3. **Administration record identity was transformed.** FHIR omitted native `emar_id`, but its `request` reference retained an order link to `pharmacy_id`; the pre-specified pharmacy/class/time/semantic composite matched 5,220 events. This is composite concordance, not native-record-ID retention.
4. **The FHIR Request timestamp carried pharmacy-entry provenance.** Across all 2,249 deterministically paired frozen-class units, `MedicationRequest.authoredOn` exactly equaled native `pharmacy.entertime` (2,249/2,249), while differing from prescription `starttime` and usually from POE `ordertime`. First administration time was also identical in 1,347/1,353 linked order units. The exact distributions are in `fhir_time_displacement.csv`.
5. **Request transport was partial rather than silently forced to parity.** Frozen six-class units numbered 3,903 in native prescriptions and 2,726 in FHIR MedicationRequest. No whitelist or mapping rule was tuned after observing this difference.

## Interpretation

The same clinical label does not guarantee that source, identity, time, event semantics, and dose/route metadata survive a representation change together. The strongest positive result is constructive: a frozen, executable provenance operator can identify exact transport (dispense), explicit transformation (request), semantic relocation (administration), and non-evaluable native-record identity without changing the clinical definition.

## Files

- `fhir_data_integrity.csv`: official SHA-256 gate.
- `fhir_role_class_metrics.csv`: per-role and per-class counts.
- `fhir_pairing_metrics.csv`: native-ID pairing.
- `fhir_administration_composite_pairing.csv`: order/time/semantic composite concordance.
- `fhir_exposure_jaccard.csv`: subject- and encounter-class overlap.
- `fhir_metadata_availability.csv`: metadata availability by role, representation, and class.
- `fhir_administration_semantic_relocation.csv`: native `event_txt`, FHIR top-level status, and FHIR `dosage.method` distributions.
- `fhir_time_displacement.csv`: deterministic time comparisons.
- `fhir_dimension_transport.csv`: five-dimensional transport classification.
- `fhir_transport_summary.json`: machine-readable decision and provenance.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\52_build_fhir_transport.py
```

Only aggregate outputs are written. No patient, encounter, `pharmacy_id`, `poe_id`, or `emar_id` is released.
