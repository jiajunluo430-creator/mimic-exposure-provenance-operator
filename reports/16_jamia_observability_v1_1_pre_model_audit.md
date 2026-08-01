# 16 — JAMIA observability v1.1 pre-model audit

The original frozen analyses remain preserved. This report implements the
versioned stay-level calendar repair and observability extension before
any corrected-era or post-implementation outcome model.

Version 1.1 uses the source-corrected MIMIC-IV eMAR deployment
interval (2014–2016): pre-implementation intervals end by 2013,
implementation-overlap intervals intersect 2014–2016, and
post-implementation intervals begin in 2017 or later.

## Calendar and eMAR observability

```text
        deployment_era  adult_stays_n  adult_stays_with_any_emar_n  adult_stays_with_any_emar_pct  adult_admissions_n  adult_admissions_with_any_emar_n  adult_admissions_with_any_emar_pct
    pre_implementation          29815                          242                       0.811672               27221                               210                            0.771463
implementation_overlap          27407                        19705                      71.897690               24823                             17749                           71.502236
   post_implementation          37222                        36543                      98.175810               33216                             32585                           98.100313
```

## Post-implementation class conversion

```text
                 drug_class  eligible_orders_n  converted_orders_n  conversion_pct
    electrolyte_replacement             113854               57408       50.422471
                    insulin              56081               38758       69.110751
            vte_prophylaxis              18133               13434       74.085921
   stress_ulcer_prophylaxis              24655               18730       75.968363
                 prokinetic               2329                1855       79.647918
intra_abdominal_antibiotics              49119               40705       82.870172
```

## Post-implementation anchor reclassification

```text
     analysis_scope anchor_id  cohort_n  outcomes_n  order_positive_n  administration_positive_n  both_positive_n  order_only_n  administration_only_n  neither_positive_n  discordant_n  discordant_pct  order_only_among_order_positive_pct  observed_agreement  cohen_kappa  jaccard_agreement
post_implementation        A1     20248        2530              7047                       5538             5538          1509                      0               13201          1509        7.452588                            21.413367            0.925474     0.827151           0.785866
post_implementation        A2      2813        1169               655                        870              574            81                    296                1862           377       13.402062                            12.366412            0.865979     0.663346           0.603575
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
    J05                     PASS                                A1: n=20248, order=7047, admin=5538 | A2: n=2813, order=655, admin=870
    J06            PENDING_MODEL                                                   Paired-model same-cohort verification awaits R fits
    J07            PENDING_MODEL                                              Post-implementation material effect change not inspected
    J08                     PASS Outcome-model inputs select deployment_era only; any_emar_in_admission retained as descriptive column
    J09          PENDING_TEXT_QA                                           Claim-boundary scan follows results and manuscript revision
    J10 PENDING_FINAL_VALIDATION                                                          Pre-model reproducibility assets are present
```
