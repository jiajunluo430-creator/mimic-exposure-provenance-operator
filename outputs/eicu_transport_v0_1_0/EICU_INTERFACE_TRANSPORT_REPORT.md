# eICU interface-semantic transport report

## Decision

**EXECUTED_INTERFACE_SEMANTIC_COMPARISON**

This is a cross-hospital interface and source-observability comparison. It is not external validation, clinical adherence assessment, or an effectiveness/safety analysis.

## Main findings

- Full ZIP streaming completed with frozen strict labels and no patient-level output.
- Classes passing all five pre-specified feasibility gates (3): intra_abdominal_antibiotics, stress_ulcer_prophylaxis, vte_prophylaxis.
- Classes failing at least one gate (3): electrolyte_replacement, insulin, prokinetic.
- Native medication-to-infusion identity remained unavailable by design; all performed reconciliation used `same stay × same class × frozen time window`.
- `treatment` remained documentation-only and `intakeOutput` remained excluded; neither was promoted to administration.

## Class results

- `stress_ulcer_prophylaxis`: 3696/167806 converted (2.202543%).
- `vte_prophylaxis`: 7491/134102 converted (5.586046%).
- `intra_abdominal_antibiotics`: 224/88816 converted (0.252207%).
- `electrolyte_replacement`: not reconciled; failed frozen gate(s): identity_unambiguous.
- `prokinetic`: not reconciled; failed frozen gate(s): admin_like_events_ge_100, hospitals_with_both_ge_10.
- `insulin`: not reconciled; failed frozen gate(s): identity_unambiguous.

## Frozen identity ambiguities

- `infusionDrug`: `D30W/85 meq KCL/60 units insulin (ml/hr)` matched `electrolyte_replacement|insulin` (3 rows).

Ambiguous composite labels were excluded and caused the affected class gate(s) to fail; they were not reassigned or used to tune the frozen whitelist.

## Engineering audit

The production implementation performed one sequential scan per required gzip member inside the read-only ZIP. Medication and infusion rows were filtered by the frozen label prefilter before retained units were stored. Reconciliation operated only on the reduced stay×class objects. The 100-order, 10-hospital regression test passed before this full run; no full-table many-to-many SQL join was used.

## Interpretation boundary

Hospital/unit variation is source observability heterogeneity. It must not be interpreted as hospital quality, medication adherence, effectiveness, or safety. Cells with fewer than 10 eligible order units were suppressed.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\54_build_eicu_transport.py
```
