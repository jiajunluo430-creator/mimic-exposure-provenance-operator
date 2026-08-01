# 05 — Prespecified models and exposure-definition effect change

All models were specified in the frozen contract. No drug class, anchor,
covariate, or analysis window was selected by statistical significance.
Estimates quantify exposure-definition sensitivity and are not interpreted
as new causal efficacy or safety conclusions.

## Held/not-given correlates

The grouped-binomial implementation is algebraically equivalent to the locked event-level logistic score for identical covariate patterns. HC0 standard errors are clustered by ICU stay. OASIS was standardized using the event-weighted SD (8.7898).

```text
            locked_correlate                        term adjusted_or    ci_low
                OASIS per SD                     oasis_z   0.9569721 0.9400835
      Night versus day shift        shiftnight_1900_0659   0.8053258 0.7885242
 Active invasive ventilation invasive_ventilation_active   0.7980154 0.7707136
          Active vasopressor          vasopressor_active   1.2300951 1.1858368
                  Active RRT                  rrt_active   0.7099980 0.6503553
   ci_high        beta cluster_robust_se    z_value      p_value   bh_q_value
 0.9741640 -0.04398108       0.009084588  -4.841285 1.290025e-06 1.290025e-06
 0.8224855 -0.21650831       0.010757295 -20.126650 4.311761e-90 2.155880e-89
 0.8262844 -0.22562735       0.017761111 -12.703448 5.658079e-37 1.414520e-36
 1.2760052  0.20709148       0.018695629  11.077000 1.622172e-28 2.703620e-28
 0.7751103 -0.34249315       0.044767781  -7.650438 2.002952e-14 2.503690e-14
```

- Meaningful locked OASIS association: FALSE (OR per SD outside 0.87–1.15 and 95% CI excludes 1).

### Audit-semantic sensitivity

The separately hashed pre-model addendum adds only exact `Hold Dose`
and `Not Given per Sliding Scale*`. The frozen literal model above
remains primary and governs every gate.

```text
            locked_correlate                        term adjusted_or    ci_low
                OASIS per SD                     oasis_z   1.0001783 0.9782589
      Night versus day shift        shiftnight_1900_0659   0.9566025 0.9437278
 Active invasive ventilation invasive_ventilation_active   0.8110782 0.7814640
          Active vasopressor          vasopressor_active   1.0868674 1.0449903
                  Active RRT                  rrt_active   0.7470146 0.6831989
   ci_high         beta cluster_robust_se      z_value      p_value
 1.0225889  0.000178283       0.011305937   0.01576897 9.874187e-01
 0.9696529 -0.044367329       0.006913499  -6.41749274 1.385370e-10
 0.8418146 -0.209390833       0.018977553 -11.03360544 2.631013e-28
 1.1304227  0.083299613       0.020047305   4.15515276 3.250703e-05
 0.8167912 -0.291670485       0.045561421  -6.40169853 1.536578e-10
   bh_q_value
 9.874187e-01
 2.560964e-10
 1.315507e-27
 4.063379e-05
 2.560964e-10
```

## Published-style primary model pairs

```text
 anchor_id exposure_definition effect_measure     n outcomes_n exposed_n
        A1               order             OR 49114       6057     14965
        A1      administration             OR 49114       6057      6581
        A2               order             HR  6625       2591      1678
        A2      administration             HR  6625       2591      1103
   effect   ci_low  ci_high      beta       p_value converged model_error
 2.430056 2.298067 2.569624 0.8879141 3.452554e-213      TRUE        <NA>
 2.145048 1.998438 2.302413 0.7631619  4.402428e-99      TRUE        <NA>
 1.936480 1.785368 2.100382 0.6608720  3.211795e-57      TRUE        <NA>
 1.231414 1.111819 1.363873 0.2081629  6.512381e-05      TRUE        <NA>
 model_warnings
               
               
               
               
```

## Primary effect-change estimands

```text
 anchor_id effect_measure effect_order ci_low_order ci_high_order
        A1             OR     2.430056     2.298067      2.569624
        A2             HR     1.936480     1.785368      2.100382
 effect_administration ci_low_administration ci_high_administration
              2.145048              1.998438               2.302413
              1.231414              1.111819               1.363873
 log_effect_change_admin_minus_order relative_absolute_log_effect_change_pct
                          -0.1247522                                14.05003
                          -0.4527090                                68.50178
 ratio_of_effects_admin_to_order direction_reversal
                       0.8827156              FALSE
                       0.6359031              FALSE
 material_absolute_log_change material_relative_log_change
                        FALSE                        FALSE
                         TRUE                         TRUE
 material_effect_change
                  FALSE
                   TRUE
```

A material change is locked as a direction reversal, an absolute log-effect
change of at least log(1.25), or a relative absolute log-effect change of
at least 25%. Statistical significance is not a selection rule.

## Same-cohort verification and sensitivities

```text
 anchor_id           model_variant definitions_n n_min n_max outcomes_min
        A1 published_style_minimal             2 49114 49114         6057
        A1                enriched             2 49114 49114         6057
        A2 published_style_minimal             2  6625  6625         2591
        A2                enriched             2  6625  6625         2591
        A2    landmark_48h_minimal             2  6000  6000         2023
        A2   landmark_48h_enriched             2  6000  6000         2023
 outcomes_max identical_n_and_outcomes
         6057                     TRUE
         6057                     TRUE
         2591                     TRUE
         2591                     TRUE
         2023                     TRUE
         2023                     TRUE
```

Enriched OASIS/organ-support models and the A2 48-hour landmark diagnostic
are retained in the machine-readable tables. They do not replace the
published-style primary model pair.

