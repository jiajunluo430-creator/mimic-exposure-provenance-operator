# 12 — JAMIA observability pre-model audit

The original frozen analyses remain preserved. This report implements the
versioned stay-level calendar repair and observability extension before
any corrected-era or post-implementation outcome model.

## Calendar and eMAR observability

```text
        deployment_era  adult_stays_n  adult_stays_with_any_emar_n  adult_stays_with_any_emar_pct  adult_admissions_n  adult_admissions_with_any_emar_n  adult_admissions_with_any_emar_pct
    pre_implementation          10920                            0                       0.000000                9952                                 0                            0.000000
implementation_overlap          24981                         1741                       6.969297               22785                              1559                            6.842221
   post_implementation          58543                        54749                      93.519294               52512                             48979                           93.272014
```

## Post-implementation class conversion

```text
                 drug_class  eligible_orders_n  converted_orders_n  conversion_pct
    electrolyte_replacement             180041               76093       42.264262
                 prokinetic               4802                2376       49.479384
   stress_ulcer_prophylaxis              39961               23970       59.983484
                    insulin              78811               48575       61.634797
            vte_prophylaxis              25958               16098       62.015564
intra_abdominal_antibiotics              73531               51209       69.642736
```

## Post-implementation anchor reclassification

```text
     analysis_scope anchor_id  cohort_n  outcomes_n  order_positive_n  administration_positive_n  both_positive_n  order_only_n  administration_only_n  neither_positive_n  discordant_n  discordant_pct  order_only_among_order_positive_pct  observed_agreement  cohen_kappa  jaccard_agreement
post_implementation        A1     31299        3876             10205                       6574             6574          3631                      0               21094          3631       11.601010                            35.580598            0.883990     0.709337           0.644194
post_implementation        A2      4301        1740               977                       1101              716           261                    385                2939           646       15.019763                            26.714432            0.849802     0.590570           0.525698
```

## Model boundary

`any_emar_in_admission` is descriptive only and does not select either
outcome-model cohort. Corrected all-period and post-implementation model
inputs were written only after the contract hash passed.

## Pre-model gates

```text
gate_id                   status                                                                                              evidence
    J01                     PASS                             94444 unique adult stays; interval ordering and missingness checks passed
    J02                     PASS                           42808593 full eMAR keys reconcile; coverage denominators sum to 94444 stays
    J03                     PASS                                                                6 post-implementation classes retained
    J04            PENDING_MODEL                                           Corrected all-period and post-implementation inputs written
    J05                     PASS                              A1: n=31299, order=10205, admin=6574 | A2: n=4301, order=977, admin=1101
    J06            PENDING_MODEL                                                   Paired-model same-cohort verification awaits R fits
    J07            PENDING_MODEL                                              Post-implementation material effect change not inspected
    J08                     PASS Outcome-model inputs select deployment_era only; any_emar_in_admission retained as descriptive column
    J09          PENDING_TEXT_QA                                           Claim-boundary scan follows results and manuscript revision
    J10 PENDING_FINAL_VALIDATION                                                          Pre-model reproducibility assets are present
```
