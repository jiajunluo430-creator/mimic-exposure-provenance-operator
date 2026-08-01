# 14 — JAMIA analytic validation and story decision

**Analytic validation: PASS.**

The extension supports a JAMIA-facing story built around a time-varying
medication data-generating process. The evidence is not merely that orders
and administrations differ: observability changes sharply across deployment
eras, residual exposure discordance remains after implementation, and that
discordance propagates differently across two prespecified published-style
association anchors.

## Key validated findings

| finding                            | estimate                                                |
| ---------------------------------- | ------------------------------------------------------- |
| eMAR observability                 | 0.000% pre; 6.969% overlap; 93.519% post implementation |
| Order-to-administration conversion | 42.264%–69.643% across six frozen classes               |
| Insulin semantic sensitivity       | 13.115% versus 49.210% not-given                        |
| A1 post-implementation drift       | 2.190 to 2.101; 5.263%                                  |
| A2 post-implementation drift       | 1.855 to 1.233; 66.074%                                 |

## Validation checks

| check_id                                       | passed | evidence                                                                                   |
| ---------------------------------------------- | ------ | ------------------------------------------------------------------------------------------ |
| jamia_extension_contract_hashes                | True   | 3/3 files match                                                                            |
| required_analytic_assets                       | True   | all required assets present                                                                |
| deployment_observability_discontinuity         | True   | pre=0.000%; overlap=6.969%; post=93.519%; stays=94,444                                     |
| full_emar_reconciliation_retained              | True   | event_txt distribution sums to 42,808,593 eMAR rows                                        |
| six_class_post_implementation_conversion       | True   | classes=6/6; range=42.264%–69.643%; orders=403,104                                         |
| six_class_post_implementation_lag              | True   | classes=6/6; median range=1.182–6.287 hours                                                |
| semantic_sensitivity_complete                  | True   | 12 class-by-mapping cells; insulin not-given 13.115% primary versus 49.210% semantic audit |
| not_given_models_converged                     | True   | 4/4 converged                                                                              |
| anchor_same_cohort_pairs                       | True   | 12/12 paired variants have identical n/outcomes                                            |
| post_implementation_effect_sensitivity_pattern | True   | A1 primary change=5.263%; A2 primary change=66.074%; A2 material variants=4/4              |
| no_any_emar_outcome_selection                  | True   | model manifest records any_emar_used_for_outcome_selection=false                           |
| analytic_pilot_gates                           | True   | 8/8 PASS; decision=GO_JAMIA_ANALYTIC                                                       |
| implementation_failure_audit_retained          | True   | first-run gate-writer error retained as implementation audit                               |
| no_prohibited_methods_in_extension             | True   | no ML/SHAP/nomogram implementation                                                         |

## Decision

**GO_JAMIA_ANALYTIC.** The post-implementation A2 anchor meets the frozen material-change rule in the primary model and all three prespecified robustness variants, whereas A1 remains comparatively exposure-definition robust. This contrast is the central positive result: susceptibility to exposure provenance is study-question specific.

The retained first-run gate-writer error is retained as
implementation failures, not statistical failures. No eMAR-presence filter
was used in outcome models, and no causal drug-effect conclusion is supported.
