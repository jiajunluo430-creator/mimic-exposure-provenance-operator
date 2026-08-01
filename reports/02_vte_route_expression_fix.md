# Stage 02 VTE route-expression implementation audit

The frozen semantic rule remains SC/SQ/subcutaneous route
plus heparin 5,000/7,500 units or enoxaparin 20–60 mg.

DuckDB 1.5.3 returned zero matches for the legacy
`SIMILAR TO '%(sc|sq|subcut)%'` implementation even though
the source route distribution contains `SC`. The v2
implementation therefore uses `regexp_matches` to express
the same pre-frozen contains rule. No route or dose category
was added, removed, or selected from outcome results.

```text
 identity_linked_vte_clusters_n  legacy_similar_to_matches_n  frozen_route_rule_matches_n  frozen_dose_rule_matches_n  frozen_joint_rule_matches_n
                          83670                            0                        39170                       40757                        37738
```

```text
       route  rows_n
          SC   39170
          IV   31799
       DWELL    9514
      DIALYS    2940
        LOCK     151
FEMORAL VEIN      44
          IP      22
     IMPELLA      12
     IV DRIP       7
    IV BOLUS       3
 IV INFUSION       2
          AC       1
      DLPICC       1
          IA       1
          IN       1
          PO       1
          TP       1
```
