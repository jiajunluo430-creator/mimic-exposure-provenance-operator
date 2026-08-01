# Stage 02 v2 limited-range pilot

The frozen scientific contract was unchanged.
The pilot tests implementation shape only.

## Metrics

```text
 projected_rows_n  direct_rows_n  pharmacy_id_rows_n  pharmacy_poe_rows_n  candidate_union_rows_n  deduplicated_candidate_rows_n  duplicate_paths_removed_n
           250000          53770               67360                    0                  121130                          68789                      52341
```

## Gates

```text
                                table_name                                key  unique_keys_n  rows_n  max_rows_per_key  pass                                       gate_status  projected_rows_n  direct_rows_n  pharmacy_id_rows_n  pharmacy_poe_rows_n  candidate_union_rows_n  deduplicated_candidate_rows_n  duplicate_paths_removed_n  targeted_fallback_matches_n  targeted_fallback_source_rows_n
                      s02v2_ingredient_map                         ingredient             52      52                 1  True                                               NaN            250000          53770               67360                    0                  121130                          68789                      52341                            0                                0
                      s02v2_pharmacy_by_id     subject_id+hadm_id+pharmacy_id        3943333 3943333                 1  True                                               NaN            250000          53770               67360                    0                  121130                          68789                      52341                            0                                0
                     s02v2_pharmacy_by_poe          subject_id+hadm_id+poe_id        2846326 2846326                 1  True                                               NaN            250000          53770               67360                    0                  121130                          68789                      52341                            0                                0
             s02v2_pilot_candidates_250000 candidate_rows_not_above_projected          68789  250000                 1  True                                               NaN            250000          53770               67360                    0                  121130                          68789                      52341                            0                                0
             s02v2_pilot_candidates_250000           candidate_count_positive          68789   68789                 1  True                                               NaN            250000          53770               67360                    0                  121130                          68789                      52341                            0                                0
s02v2_pilot_missing_pharmacy_matches_50000        poe_fallback_path_exercised              0       0                 1  True not_applicable_no_missing_pharmacy_id_with_poe_id            250000          53770               67360                    0                  121130                          68789                      52341                            0                                0
```

All candidate-path joins use plans without
BLOCKWISE_NL_JOIN, NESTED_LOOP_JOIN, or CROSS_PRODUCT.
