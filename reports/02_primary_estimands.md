# 02 — Six-class order-to-administration primary estimands

All six classes use the pre-result frozen strict whitelist. Low
counts are labeled; no class is selected or removed.

## Order-to-administration conversion

```text
                 drug_class  eligible_orders_n  converted_orders_n  conversion_pct  negative_lag_n  lag_0_24h_n  lag_24h_7d_n  lag_over_7d_n  not_converted_n  conversion_ci_low_pct  conversion_ci_high_pct       count_status
   stress_ulcer_prophylaxis              71623               24046       33.573014              35        23575           432              4            47577              33.228052               33.919738 primary_estimation
            vte_prophylaxis              37738               16132       42.747363              16        15616           500              0            21606              42.248999               43.247204 primary_estimation
intra_abdominal_antibiotics             116654               51379       44.043925              99        50554           726              0            65275              43.759244               44.328998 primary_estimation
    electrolyte_replacement             287225               76344       26.579859             726        65885          9164            569           210881              26.418618               26.741727 primary_estimation
                 prokinetic              10366                2380       22.959676              10         2341            28              1             7986              22.160155               23.779231 primary_estimation
                    insulin             109475               48700       44.485042             935        45987          1738             40            60775              44.190865               44.779607 primary_estimation
```

## First-dose lag

Negative documentation-timing anomalies and lags over seven days
are retained in the audit table but excluded from the inferential
lag distribution.

```text
                 drug_class  converted_nonnegative_le7d_n  p10_hours  p25_hours  median_hours  p75_hours  p90_hours  p95_hours  over_24h_pct
    electrolyte_replacement                         75049   0.271944   0.664444      2.045833   8.900000  29.004167  48.815444     12.210689
                    insulin                         47725   0.233889   0.658056      2.856944   7.735556  20.912000  22.538278      3.641697
intra_abdominal_antibiotics                         51280   0.494444   1.092500      2.865556   7.229514  13.185611  18.710861      1.415757
                 prokinetic                          2369   0.198889   0.421667      1.175556   3.207778   6.275722   9.168556      1.181933
   stress_ulcer_prophylaxis                         24007   0.613333   1.750694      6.280000  11.315000  18.873222  21.749472      1.799475
            vte_prophylaxis                         16116   0.930972   2.195000      5.117361   8.948819  11.977639  19.341042      3.102507
```

## Held/not-given crude proportions

Flushed, Confirmed, blank, and other event text remain outside the
decision denominator.

```text
                 drug_class  assigned_events_n  given_n  not_given_n  flushed_n  confirmed_n  blank_n  other_excluded_n  not_given_pct
    electrolyte_replacement             227689 167054.0       6033.0        7.0        146.0  51268.0            3181.0       3.485530
                    insulin             535944 239238.0      36150.0        0.0      47483.0   3462.0          209611.0      13.126934
intra_abdominal_antibiotics             243334 234478.0       6127.0        0.0          0.0    970.0            1759.0       2.546497
                 prokinetic              15856  14710.0       1081.0        0.0          0.0     10.0              55.0       6.845672
   stress_ulcer_prophylaxis             205710 193499.0      10447.0        0.0        650.0     48.0            1066.0       5.122434
            vte_prophylaxis             330521 218831.0       8704.0      114.0      79414.0    227.0           23231.0       3.825346
```

## Order POE-link coverage

```text
                 drug_class  prescription_candidate_rows_n  poe_id_nonmissing_n  poe_any_link_n  poe_identity_link_n  poe_id_nonmissing_pct  identity_link_among_nonmissing_pct
    electrolyte_replacement                        1005997            1005997.0       1005997.0            1005872.0                  100.0                           99.987575
                    insulin                         178392             178392.0        178392.0             178376.0                  100.0                           99.991031
intra_abdominal_antibiotics                         230167             230167.0        230167.0             230139.0                  100.0                           99.987835
                 prokinetic                          10553              10553.0         10553.0              10553.0                  100.0                          100.000000
   stress_ulcer_prophylaxis                         108391             108391.0        108391.0             108372.0                  100.0                           99.982471
            vte_prophylaxis                         134279             134279.0        134279.0             134263.0                  100.0                           99.988085
```

## Machine-readable summary

```text
{'adult_stays_n': 94444, 'prescription_candidate_rows_n': 5464963, 'eligible_order_clusters_n': 633081, 'converted_order_clusters_n': 218981, 'six_classes_retained': True, 'all_conversion_gt97': False}
```
