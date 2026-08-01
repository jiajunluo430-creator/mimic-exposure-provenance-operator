# 04 — Prespecified published-association cohorts

Both anchors were frozen before these cohorts were extracted.
Within each anchor, order-defined and administration-defined
exposures use exactly the same cohort, outcome, and covariates.
This is an exposure-definition sensitivity analysis, not a new
causal efficacy or safety study.

## Frozen anchors

- A1: Muchintala R, et al. *Cureus*. 2025;17:e86370.
  PMID 40688991; PMCID PMC12276787;
  DOI 10.7759/cureus.86370.
- A2: Ma C, et al. *Front Pharmacol*. 2025;16:1545533.
  PMID 40612738; PMCID PMC12223537;
  DOI 10.3389/fphar.2025.1545533.

## Cohort flow

```text
anchor_id                                                  step  rows_n
       A1                                       adult ICU stays 94444.0
       A1                      exactly one ICU stay per subject 49114.0
       A1                  valid hospital outcome; final cohort 49114.0
       A2                      adult first ICU stay per subject 65355.0
       A2                                      ICD-coded sepsis  9637.0
       A2 after active acid-indication exclusions; final cohort  6625.0
       A2                               48-hour landmark cohort  6000.0
```

## Exposure prevalence

```text
anchor_id  cohort_n  order_exposed_n  order_exposed_pct  administration_exposed_n  administration_exposed_pct  discordant_pct  outcomes_n
       A1     49114          14965.0          30.469927                    6581.0                   13.399438       17.070489      6057.0
       A2      6625           1678.0          25.328302                    1103.0                   16.649057       20.332075      2591.0
```

## Exposure cross-classification

```text
anchor_id  order_exposure  administration_exposure  patients_n  outcomes_n  outcome_pct
       A1               0                        0       34149      3114.0     9.118861
       A1               1                        0        8384      1679.0    20.026240
       A1               1                        1        6581      1264.0    19.206807
       A2               0                        0        4561      1581.0    34.663451
       A2               0                        1         386       108.0    27.979275
       A2               1                        0         961       505.0    52.549428
       A2               1                        1         717       397.0    55.369596
```

## Anchor-class eMAR-to-POE identity linkage

```text
anchor_id  strict_given_events_n  poe_nonmissing_n  poe_any_link_n  poe_identity_link_n  poe_identity_link_pct
       A1                 218831          218831.0        218299.0             218299.0              99.756890
       A2                 105759          105759.0        105450.0             105450.0              99.707826
```

A1 administration exposure is documented strict eMAR delivery
linked to an eligible subcutaneous prophylactic UFH/enoxaparin
order. A2 administration exposure is any strict PPI eMAR
administration in the first 48 hours. The A2 ICD cohort is the
frozen transparent operational re-estimation and is not claimed
to reproduce the publication's Sepsis-3 cohort exactly.

## Machine-readable summary

```text
{'A1_cohort_n': 49114, 'A2_cohort_n': 6625, 'A1_order_exposed_n': 14965, 'A1_administration_exposed_n': 6581, 'A2_order_exposed_n': 1678, 'A2_administration_exposed_n': 1103, 'A2_landmark_48h_n': 6000}
```
