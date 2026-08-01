# 17 — JAMIA observability v1.1 post-2016 models

**Decision: GO_JAMIA_ANALYTIC.**

The original frozen outputs remain preserved. Models below use the same
classes, exposure definitions, windows, cohorts, outcomes, covariates,
model families, and material-change rule. The complete-cohort repair changes
only stay-level calendar alignment; the post-implementation analysis is the
versioned observability sensitivity.

## Corrected and post-implementation not-given correlates

```text
       analysis_population              event_mapping
 all_periods_corrected_era             frozen_primary
 all_periods_corrected_era             frozen_primary
 all_periods_corrected_era             frozen_primary
 all_periods_corrected_era             frozen_primary
 all_periods_corrected_era             frozen_primary
       post_implementation             frozen_primary
       post_implementation             frozen_primary
       post_implementation             frozen_primary
       post_implementation             frozen_primary
       post_implementation             frozen_primary
 all_periods_corrected_era audit_semantic_sensitivity
 all_periods_corrected_era audit_semantic_sensitivity
 all_periods_corrected_era audit_semantic_sensitivity
 all_periods_corrected_era audit_semantic_sensitivity
 all_periods_corrected_era audit_semantic_sensitivity
       post_implementation audit_semantic_sensitivity
       post_implementation audit_semantic_sensitivity
       post_implementation audit_semantic_sensitivity
       post_implementation audit_semantic_sensitivity
       post_implementation audit_semantic_sensitivity
            locked_correlate                        term adjusted_or    ci_low
                OASIS per SD                     oasis_z   0.9569979 0.9401462
      Night versus day shift        shiftnight_1900_0659   0.8044447 0.7876429
 Active invasive ventilation invasive_ventilation_active   0.8000506 0.7727363
          Active vasopressor          vasopressor_active   1.2214821 1.1775528
                  Active RRT                  rrt_active   0.7113803 0.6519229
                OASIS per SD                     oasis_z   0.9547641 0.9356446
      Night versus day shift        shiftnight_1900_0659   0.7657021 0.7472568
 Active invasive ventilation invasive_ventilation_active   0.7771662 0.7473041
          Active vasopressor          vasopressor_active   1.2261311 1.1739985
                  Active RRT                  rrt_active   0.6863535 0.6244193
                OASIS per SD                     oasis_z   1.0021793 0.9802265
      Night versus day shift        shiftnight_1900_0659   0.9569661 0.9441274
 Active invasive ventilation invasive_ventilation_active   0.8187815 0.7892236
          Active vasopressor          vasopressor_active   1.0722188 1.0310712
                  Active RRT                  rrt_active   0.7463895 0.6834478
                OASIS per SD                     oasis_z   0.9929873 0.9680261
      Night versus day shift        shiftnight_1900_0659   0.9542341 0.9397707
 Active invasive ventilation invasive_ventilation_active   0.8032381 0.7699603
          Active vasopressor          vasopressor_active   1.0689564 1.0208149
                  Active RRT                  rrt_active   0.7215940 0.6528640
   ci_high         beta cluster_robust_se     z_value       p_value
 0.9741517 -0.043954031       0.009064356  -4.8491068  1.240186e-06
 0.8216049 -0.217603056       0.010769293 -20.2058822  8.690285e-91
 0.8283305 -0.223080289       0.017723379 -12.5867809  2.496484e-36
 1.2670503  0.200064994       0.018687399  10.7058772  9.552166e-27
 0.7762604 -0.340548145       0.044531891  -7.6472869  2.052641e-14
 0.9742744 -0.046290935       0.010320918  -4.4851565  7.286044e-06
 0.7846027 -0.266962123       0.012441205 -21.4578984 3.853313e-102
 0.8082216 -0.252101061       0.019991227 -12.6105849  1.846178e-36
 1.2805786  0.203863732       0.022167880   9.1963567  3.702921e-20
 0.7544308 -0.376362426       0.048251243  -7.8000566  6.187942e-15
 1.0246239  0.002176963       0.011300527   0.1926426  8.472389e-01
 0.9699795 -0.043987261       0.006891388  -6.3829318  1.737293e-10
 0.8494463 -0.199938075       0.018759278 -10.6580898  1.598467e-26
 1.1150084  0.069730121       0.019965585   3.4925158  4.784933e-04
 0.8151277 -0.292507712       0.044948388  -6.5076351  7.634307e-11
 1.0185922 -0.007037376       0.012989430  -0.5417771  5.879721e-01
 0.9689200 -0.046846301       0.007792501  -6.0117158  1.835700e-09
 0.8379541 -0.219104110       0.021588231 -10.1492387  3.339585e-24
 1.1193683  0.066682888       0.023511477   2.8361846  4.565605e-03
 0.7975594 -0.326292687       0.051069163  -6.3892312  1.667219e-10
    bh_q_value
  1.240186e-06
  4.345142e-90
  6.241210e-36
  1.592028e-26
  2.565801e-14
  7.286044e-06
 1.926656e-101
  4.615445e-36
  6.171534e-20
  7.734927e-15
  8.472389e-01
  2.895488e-10
  7.992337e-26
  5.981166e-04
  1.908577e-10
  5.879721e-01
  3.059500e-09
  1.669792e-23
  5.707006e-03
  4.168047e-10
```

## Published-style anchor effects

```text
       analysis_population anchor_id exposure_definition effect_measure     n
 all_periods_corrected_era        A1               order             OR 49114
 all_periods_corrected_era        A1      administration             OR 49114
 all_periods_corrected_era        A2               order             HR  6625
 all_periods_corrected_era        A2      administration             HR  6625
       post_implementation        A1               order             OR 20248
       post_implementation        A1      administration             OR 20248
       post_implementation        A2               order             HR  2813
       post_implementation        A2      administration             HR  2813
 outcomes_n exposed_n   effect   ci_low  ci_high
       6057     14965 2.430056 2.298067 2.569624
       6057      6581 2.145048 1.998438 2.302413
       2591      1678 1.938699 1.787132 2.103121
       2591      1103 1.241905 1.119055 1.378242
       2530      7047 1.868346 1.714602 2.035876
       2530      5538 1.953035 1.787892 2.133432
       1169       655 1.903852 1.683004 2.153680
       1169       870 1.207799 1.070320 1.362936
```

## Effect-change estimands

```text
       analysis_population anchor_id effect_measure effect_order
 all_periods_corrected_era        A1             OR     2.430056
 all_periods_corrected_era        A2             HR     1.938699
       post_implementation        A1             OR     1.868346
       post_implementation        A2             HR     1.903852
 effect_administration absolute_log_effect_change
              2.145048                 0.12475224
              1.241905                 0.44537050
              1.953035                 0.04433102
              1.207799                 0.45507957
 relative_absolute_log_effect_change_pct ratio_of_effects_admin_to_order
                               14.050035                       0.8827156
                               67.274753                       0.6405869
                                7.092355                       1.0453283
                               70.677796                       0.6343975
 direction_reversal material_effect_change
              FALSE                  FALSE
              FALSE                   TRUE
              FALSE                  FALSE
              FALSE                   TRUE
```

## Same-cohort verification

```text
       analysis_population anchor_id           model_variant definitions_n
 all_periods_corrected_era        A1 published_style_minimal             2
 all_periods_corrected_era        A1                enriched             2
 all_periods_corrected_era        A2 published_style_minimal             2
 all_periods_corrected_era        A2                enriched             2
 all_periods_corrected_era        A2    landmark_48h_minimal             2
 all_periods_corrected_era        A2   landmark_48h_enriched             2
       post_implementation        A1 published_style_minimal             2
       post_implementation        A1                enriched             2
       post_implementation        A2 published_style_minimal             2
       post_implementation        A2                enriched             2
       post_implementation        A2    landmark_48h_minimal             2
       post_implementation        A2   landmark_48h_enriched             2
 n_min n_max outcomes_min outcomes_max identical_n_and_outcomes
 49114 49114         6057         6057                     TRUE
 49114 49114         6057         6057                     TRUE
  6625  6625         2591         2591                     TRUE
  6625  6625         2591         2591                     TRUE
  6000  6000         2023         2023                     TRUE
  6000  6000         2023         2023                     TRUE
 20248 20248         2530         2530                     TRUE
 20248 20248         2530         2530                     TRUE
  2813  2813         1169         1169                     TRUE
  2813  2813         1169         1169                     TRUE
  2544  2544          916          916                     TRUE
  2544  2544          916          916                     TRUE
```

## JAMIA pilot gates

```text
 gate_id                   status
     J01                     PASS
     J02                     PASS
     J03                     PASS
     J04                     PASS
     J05                     PASS
     J06                     PASS
     J07                     PASS
     J08                     PASS
     J09          PENDING_TEXT_QA
     J10 PENDING_FINAL_VALIDATION
                                                                    evidence
   94444 unique adult stays; interval ordering and missingness checks passed
 42808593 full eMAR keys reconcile; coverage denominators sum to 94444 stays
                                      6 post-implementation classes retained
                                    4/4 corrected not-given models converged
      A1: n=20248, order=7047, admin=5538 | A2: n=2813, order=655, admin=870
                             12/12 paired variants have identical n/outcomes
                                  Material post-implementation anchor(s): A2
   Outcome models used deployment_era inputs only; any_emar was not a filter
                             Claim-boundary scan follows manuscript revision
                     Model assets complete; final package validation pending
```

`any_emar_in_admission` was not used to select an outcome-model cohort.
The estimates remain exposure-definition sensitivity analyses and are not
new causal drug-effect estimates.

