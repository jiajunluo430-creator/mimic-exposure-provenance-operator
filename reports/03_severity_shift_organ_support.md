# 03 — Severity, shift, and organ-support alignment

OASIS uses the official MIMIC Code v3.0.0 component cutpoints,
vital-sign item mappings, GCS handling, and urine-output item set.
The implementation is frozen and independent of medication
outcomes.

Official source: MIT-LCP MIMIC Code `oasis.sql`, `gcs.sql`,
`first_day_*`, `ventilator_setting.sql`,
`oxygen_delivery.sql`, and `ventilation.sql` (repository main
branch inspected 2026-07-29).

## OASIS component coverage

```text
 adult_stays_n  gcs_available_n  hr_available_n  mbp_available_n  rr_available_n  temperature_available_n  urine_available_n  oasis_mean  oasis_median  oasis_p25  oasis_p75  mean_missing_components
         94444          93792.0         94341.0          94230.0         94197.0                  91741.0            89428.0   30.801904          30.0       24.0       36.0                 0.094606
```

## Organ-support intervals

```text
        support_type  intervals_n  stays_n
invasive_ventilation        44445    35813
                 rrt         5399     2274
         vasopressor       830003    28483
```

## Class-specific decision-event rates

```text
                 drug_class  decision_events_n  not_given_n  not_given_pct  stays_n
    electrolyte_replacement             173087       6033.0       3.485530    30783
                    insulin             275388      36150.0      13.126934    22899
intra_abdominal_antibiotics             240605       6127.0       2.546497    21737
                 prokinetic              15791       1081.0       6.845672     2391
   stress_ulcer_prophylaxis             203946      10447.0       5.122434    32203
            vte_prophylaxis              91677       4125.0       4.499493    12743
```

## Pre-model semantic-audit sensitivity

The original literal mapping remains primary. The separately
hashed pre-model addendum adds only exact `Hold Dose` and the
`Not Given per Sliding Scale*` vendor subtype. It cannot alter
pilot gates or the final stop-loss decision.

```text
                 drug_class  decision_events_n  not_given_n  not_given_pct  stays_n
    electrolyte_replacement             175212       8158.0       4.656074    30864
                    insulin             471050     231812.0      49.211761    26038
intra_abdominal_antibiotics             240910       6432.0       2.669877    21739
                 prokinetic              15835       1125.0       7.104515     2391
   stress_ulcer_prophylaxis             204520      11021.0       5.388715    32212
            vte_prophylaxis              91984       4432.0       4.818229    12762
```

## Prespecified crude stratification

```text
                  dimension           level  decision_events_n  not_given_n  not_given_pct
invasive_ventilation_active               0             619465      44381.0       7.164408
invasive_ventilation_active               1             381029      19582.0       5.139241
             oasis_quartile               1             250124      18035.0       7.210424
             oasis_quartile               2             250124      16640.0       6.652700
             oasis_quartile               3             250123      15623.0       6.246127
             oasis_quartile               4             250123      13665.0       5.463312
                 rrt_active               0             940756      61081.0       6.492757
                 rrt_active               1              59738       2882.0       4.824400
                      shift   day_0700_1859             577782      41213.0       7.132967
                      shift night_1900_0659             422712      22750.0       5.381915
         vasopressor_active               0             786250      50880.0       6.471224
         vasopressor_active               1             214244      13083.0       6.106589
```

The adjusted clustered logistic model is fitted by the locked R
script after this extraction; these crude rates are not used to
select classes or covariates.

## Machine-readable summary

```text
{'oasis_rows_n': 94444, 'not_given_decision_events_n': 1000494, 'not_given_events_n': 63963, 'not_given_model_aggregated_rows_n': 285794, 'not_given_audit_sensitivity_decision_events_n': 1199511, 'not_given_audit_sensitivity_events_n': 262980}
```
