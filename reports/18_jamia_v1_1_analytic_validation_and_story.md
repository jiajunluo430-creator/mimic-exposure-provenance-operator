# 18 — JAMIA v1.1 analytic validation and story decision

**Analytic validation: PASS.**

The extension supports a JAMIA-facing story built around a time-varying
medication data-generating process. The evidence is not merely that orders
and administrations differ: observability changes sharply across deployment
eras, residual exposure discordance remains after implementation, and that
discordance propagates differently across two prespecified published-style
association anchors.

## Key validated findings

| finding                            | estimate                                                 |
| ---------------------------------- | -------------------------------------------------------- |
| eMAR observability                 | 0.812% pre; 71.898% overlap; 98.176% post implementation |
| Order-to-administration conversion | 50.422%–82.870% across six frozen classes                |
| Insulin semantic sensitivity       | 11.985% versus 48.563% not-given                         |
| A1 post-implementation drift       | 1.868 to 1.953; 7.092%                                   |
| A2 post-implementation drift       | 1.904 to 1.208; 70.678%                                  |

## Validation checks

| check_id                                       | passed | evidence                                                                                   |
| ---------------------------------------------- | ------ | ------------------------------------------------------------------------------------------ |
| jamia_extension_contract_hashes                | True   | 3/3 files match                                                                            |
| required_analytic_assets                       | True   | all required assets present                                                                |
| deployment_observability_discontinuity         | True   | pre=0.812%; overlap=71.898%; post=98.176%; stays=94,444                                    |
| full_emar_reconciliation_retained              | True   | event_txt distribution sums to 42,808,593 eMAR rows                                        |
| six_class_post_implementation_conversion       | True   | classes=6/6; range=50.422%–82.870%; orders=264,171                                         |
| six_class_post_implementation_lag              | True   | classes=6/6; median range=1.208–6.506 hours                                                |
| semantic_sensitivity_complete                  | True   | 12 class-by-mapping cells; insulin not-given 11.985% primary versus 48.563% semantic audit |
| not_given_models_converged                     | True   | 4/4 converged                                                                              |
| anchor_same_cohort_pairs                       | True   | 12/12 paired variants have identical n/outcomes                                            |
| post_implementation_effect_sensitivity_pattern | True   | A1 primary change=7.092%; A2 primary change=70.678%; A2 material variants=4/4              |
| no_any_emar_outcome_selection                  | True   | model manifest records any_emar_used_for_outcome_selection=false                           |
| analytic_pilot_gates                           | True   | 8/8 PASS; decision=GO_JAMIA_ANALYTIC                                                       |
| implementation_failure_audit_retained          | True   | v1.0 gate-writer and source-definition failures retained; v1.1 isolated                    |
| no_prohibited_methods_in_extension             | True   | no ML/SHAP/nomogram implementation                                                         |

## Decision

**GO_JAMIA_ANALYTIC.** The post-implementation A2 anchor meets the frozen material-change rule in the primary model and all three prespecified robustness variants, whereas A1 remains comparatively exposure-definition robust. This contrast is the central positive result: susceptibility to exposure provenance is study-question specific.

The v1.0 gate-writer and deployment-source errors are retained as
implementation failures, not statistical failures. No eMAR-presence filter
was used in outcome models, and no causal drug-effect conclusion is supported.
