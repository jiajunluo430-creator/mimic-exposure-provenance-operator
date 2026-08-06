# OMOP capability and semantic-loss report

## Decisions

- Synthetic adapter gate: **PASS_DETERMINISTIC_SEMANTIC_ABLATION**
- Real demo gate: **EXECUTED_CAPABILITY_SMOKE_TEST**

This is an adapter smoke test and semantic-loss demonstration. It is not OMOP validation, external validation, or a treatment-effect analysis.

## Main findings

1. The official 100-patient OMOP demo contained 18,229 `DRUG_EXPOSURE` rows. The frozen PPI operator matched 48 rows and collapsed them to 37 person×visit×class units.
2. Record-existence exposure was executable: all 37 PPI units were classified as documented drug exposure.
3. Strict documented administration was structurally unmeasurable: `medprov_event_state` was present in 0 rows, so all 37 PPI units became `unmeasurable`, not unexposed.
4. On the same synthetic fixture, the ATLAS-style record-existence operator classified 4 units as exposed. The provenance extension separated them into 1 exposed, 1 unexposed, 1 unresolved, and 1 unmeasurable. Removing the extension made all 4 units unmeasurable.
5. This demonstrates complementarity rather than replacement: OMOP/ATLAS expresses reusable drug-record cohorts; medprov makes source role and event semantics executable and auditable when those distinctions matter.

## Official source boundary

The evaluated v0.9 demo documents that `DRUG_EXPOSURE` is built from `prescriptions` and `pharmacy`; it does not add `emar`/`emar_detail` medication detail and does not incorporate ICU `inputevents`. A `DRUG_EXPOSURE` row therefore cannot be relabeled as documented administration without additional provenance.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\53_build_omop_evaluation.py
```

Only aggregate public-demo and fully synthetic results are released.
