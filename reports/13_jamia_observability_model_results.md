# 13 — JAMIA observability corrected and post-implementation models

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
                OASIS per SD                     oasis_z   0.9572922 0.9403971
      Night versus day shift        shiftnight_1900_0659   0.8042066 0.7873744
 Active invasive ventilation invasive_ventilation_active   0.7993217 0.7719769
          Active vasopressor          vasopressor_active   1.2219146 1.1778706
                  Active RRT                  rrt_active   0.7117876 0.6522780
                OASIS per SD                     oasis_z   1.0021793 0.9802265
      Night versus day shift        shiftnight_1900_0659   0.9569661 0.9441274
 Active invasive ventilation invasive_ventilation_active   0.8187815 0.7892236
          Active vasopressor          vasopressor_active   1.0722188 1.0310712
                  Active RRT                  rrt_active   0.7463895 0.6834478
                OASIS per SD                     oasis_z   1.0021274 0.9801224
      Night versus day shift        shiftnight_1900_0659   0.9572234 0.9443565
 Active invasive ventilation invasive_ventilation_active   0.8188461 0.7892265
          Active vasopressor          vasopressor_active   1.0726973 1.0314432
                  Active RRT                  rrt_active   0.7461560 0.6831849
   ci_high         beta cluster_robust_se     z_value      p_value   bh_q_value
 0.9741517 -0.043954031       0.009064356  -4.8491068 1.240186e-06 1.240186e-06
 0.8216049 -0.217603056       0.010769293 -20.2058822 8.690285e-91 4.345142e-90
 0.8283305 -0.223080289       0.017723379 -12.5867809 2.496484e-36 6.241210e-36
 1.2670503  0.200064994       0.018687399  10.7058772 9.552166e-27 1.592028e-26
 0.7762604 -0.340548145       0.044531891  -7.6472869 2.052641e-14 2.565801e-14
 0.9744908 -0.043646626       0.009085060  -4.8042199 1.553560e-06 1.553560e-06
 0.8213987 -0.217899057       0.010792224 -20.1903762 1.189553e-90 5.947765e-90
 0.8276351 -0.223991774       0.017759925 -12.6122028 1.808662e-36 4.521654e-36
 1.2676056  0.200418990       0.018730343  10.7002307 1.015251e-26 1.692085e-26
 0.7767264 -0.339975751       0.044546065  -7.6320042 2.311319e-14 2.889149e-14
 1.0246239  0.002176963       0.011300527   0.1926426 8.472389e-01 8.472389e-01
 0.9699795 -0.043987261       0.006891388  -6.3829318 1.737293e-10 2.895488e-10
 0.8494463 -0.199938075       0.018759278 -10.6580898 1.598467e-26 7.992337e-26
 1.1150084  0.069730121       0.019965585   3.4925158 4.784933e-04 5.981166e-04
 0.8151277 -0.292507712       0.044948388  -6.5076351 7.634307e-11 1.908577e-10
 1.0246264  0.002125147       0.011328243   0.1875972 8.511924e-01 8.511924e-01
 0.9702656 -0.043718506       0.006904755  -6.3316522 2.425497e-10 4.042495e-10
 0.8495774 -0.199859070       0.018797712 -10.6320956 2.113101e-26 1.056551e-25
 1.1156013  0.070176274       0.020009190   3.5072021 4.528450e-04 5.660563e-04
 0.8149314 -0.292820531       0.044985119  -6.5092754 7.551415e-11 1.887854e-10
```

## Published-style anchor effects

```text
       analysis_population anchor_id exposure_definition effect_measure     n
 all_periods_corrected_era        A1               order             OR 49114
 all_periods_corrected_era        A1      administration             OR 49114
 all_periods_corrected_era        A2               order             HR  6625
 all_periods_corrected_era        A2      administration             HR  6625
       post_implementation        A1               order             OR 31299
       post_implementation        A1      administration             OR 31299
       post_implementation        A2               order             HR  4301
       post_implementation        A2      administration             HR  4301
 outcomes_n exposed_n   effect   ci_low  ci_high
       6057     14965 2.430056 2.298067 2.569624
       6057      6581 2.145048 1.998438 2.302413
       2591      1678 1.938699 1.787132 2.103121
       2591      1103 1.241905 1.119055 1.378242
       3876     10205 2.189582 2.042515 2.347238
       3876      6574 2.101104 1.948336 2.265849
       1740       977 1.854616 1.674856 2.053668
       1740      1101 1.233127 1.110775 1.368956
```

## Effect-change estimands

```text
       analysis_population anchor_id effect_measure effect_order
 all_periods_corrected_era        A1             OR     2.430056
 all_periods_corrected_era        A2             HR     1.938699
       post_implementation        A1             OR     2.189582
       post_implementation        A2             HR     1.854616
 effect_administration absolute_log_effect_change
              2.145048                 0.12475224
              1.241905                 0.44537050
              2.101104                 0.04124771
              1.233127                 0.40812420
 relative_absolute_log_effect_change_pct ratio_of_effects_admin_to_order
                               14.050035                       0.8827156
                               67.274753                       0.6405869
                                5.263131                       0.9595914
                               66.074003                       0.6648963
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
 31299 31299         3876         3876                     TRUE
 31299 31299         3876         3876                     TRUE
  4301  4301         1740         1740                     TRUE
  4301  4301         1740         1740                     TRUE
  3899  3899         1372         1372                     TRUE
  3899  3899         1372         1372                     TRUE
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
    A1: n=31299, order=10205, admin=6574 | A2: n=4301, order=977, admin=1101
                             12/12 paired variants have identical n/outcomes
                                  Material post-implementation anchor(s): A2
   Outcome models used deployment_era inputs only; any_emar was not a filter
                             Claim-boundary scan follows manuscript revision
                     Model assets complete; final package validation pending
```

`any_emar_in_admission` was not used to select an outcome-model cohort.
The estimates remain exposure-definition sensitivity analyses and are not
new causal drug-effect estimates.

