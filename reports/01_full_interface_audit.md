# 01 — Frozen-interface and mandatory full-table audit

This report was generated after the contract and whitelist hashes
were frozen and before any published-association outcome model.

## Full eMAR event_txt distribution and POE linkage

- Full eMAR rows: 42,808,593
- Distribution sum: 42,808,593
- Reconciles: True

```text
 emar_rows_n  poe_id_nonmissing_n  poe_id_any_link_n  poe_id_identity_link_n  poe_id_identity_mismatch_n  poe_id_nonmissing_pct  poe_any_link_among_nonmissing_pct  poe_identity_link_among_nonmissing_pct
    42808593             42808593           41211672                41176690                       34982                  100.0                          96.269625                               96.187908
```

```text
                                       event_txt   rows_n  poe_id_nonmissing_n  poe_id_any_link_n  poe_id_identity_link_n  poe_id_identity_mismatch_n
                                    Administered 28419780             28419780           27329393                27308094                       21299
                                         Flushed  3350325              3350325            3292667                 3290384                        2283
                                       Not Given  2978274              2978274            2895524                 2891372                        4152
                                       Confirmed  1852934              1852934            1819727                 1818851                         876
                                     Not Flushed  1444424              1444424            1418605                 1416842                        1763
                     Not Given per Sliding Scale   943457               943457             922950                  922478                         472
                                         Started   808052               808052             707397                  707039                         358
                                        Assessed   582474               582474             571760                  571410                         350
                                         Stopped   517092               517092             434334                  433871                         463
                                          <NULL>   446102               446102             430021                  429729                         292
                                         Applied   232117               232117             217081                  216764                         317
                                         Removed   195372               195372             189492                  189104                         388
                           Stopped - Unscheduled   169925               169925             165997                  165833                         164
                            Delayed Administered   152898               152898             150106                  149959                         147
                                       Hold Dose   108624               108624             106665                  106509                         156
                                     Not Applied    72204                72204              69328                   69175                         153
                         Infusion Reconciliation    68286                68286              67382                   67351                          31
                               in Other Location    54914                54914              52431                   52278                         153
                                       Restarted    50544                50544              48773                   48743                          30
                 Administered Bolus from IV Drip    50484                50484              49641                   49427                         214
                                     Not Started    43798                43798              42073                   42058                          15
                                   Not Confirmed    41316                41316              40685                   40634                          51
                       Stopped in Other Location    37452                37452              34659                   34560                          99
                  Administered in Other Location    29113                29113              27590                   27460                         130
                             Stopped As Directed    21467                21467              20845                   20843                           2
                        Pain score re-assessment    20867                20867                  0                       0                           0
                                     Not Stopped    20135                20135              18736                   18717                          19
                  Removed Existing / Applied New    16070                16070              15692                   15658                          34
                                     Rate Change     9579                 9579               9347                    9344                           3
                       Flushed in Other Location     8638                 8638               8520                    8512                           8
                                        Delayed      7210                 7210               7199                    7190                           9
                                    Not Assessed     6898                 6898               6729                    6670                          59
                                     Not Removed     6627                 6627               6422                    6378                          44
                       Started in Other Location     6155                 6155               5836                    5754                          82
                                 Delayed Started     6059                 6059               5909                    5901                           8
                            Partial Administered     5832                 5832               5806                    5805                           1
                   Pain score re-assess not done     5167                 5167                  0                       0                           0
                                 Delayed Flushed     3951                 3951               3908                    3904                           4
                               Delayed Confirmed     2499                 2499               2470                    2469                           1
                      Documented in O.R. Holding     2433                 2433               1291                    1288                           3
                     Confirmed in Other Location     2108                 2108               1999                    1993                           6
                       Applied in Other Location     1666                 1666               1517                    1196                         321
         Stopped - Unscheduled in Other Location      797                  797                789                     787                           2
                Infusion Reconciliation Not Done      730                  730                727                     727                           0
                                 Delayed Stopped      678                  678                650                     649                           1
                      Assessed in Other Location      584                  584                574                     567                           7
                                 Delayed Removed      536                  536                526                     523                           3
                                            Read      462                  462                453                     453                           0
                                Delayed Assessed      321                  321                320                     319                           1
                       Removed in Other Location      168                  168                165                     160                           5
                   Not Started per Sliding Scale      167                  167                164                     163                           1
                            TPN Rate Not Changed      143                  143                136                     136                           0
                   Not Stopped per Sliding Scale      130                  130                123                     123                           0
                             Delayed Not Applied      104                  104                104                     104                           0
Removed Existing / Applied New in Other Location      101                  101                 96                      94                           2
                                 Delayed Applied       94                   94                 84                      84                           0
                             Delayed Not Flushed       72                   72                 72                      72                           0
                           Removed - Unscheduled       44                   44                 44                      44                           0
                             Delayed Not Started       35                   35                 35                      35                           0
                                        Not Read       24                   24                 24                      24                           0
                           Delayed Not Confirmed       22                   22                 22                      22                           0
                             Delayed Not Removed       11                   11                 11                      11                           0
                               Delayed Restarted       10                   10                  9                       9                           0
                     Restarted in Other Location        9                    9                  8                       8                           0
                             Delayed Rate Change        7                    7                  7                       7                           0
                   Rate Change in Other Location        6                    6                  6                       6                           0
                          Read in Other Location        5                    5                  5                       5                           0
                                        Partial         4                    4                  4                       4                           0
   Not Given per Sliding Scale in Other Location        3                    3                  3                       3                           0
                            Delayed Not Assessed        1                    1                  1                       1                           0
                             Delayed Not Stopped        1                    1                  1                       1                           0
                     Delayed Stopped As Directed        1                    1                  1                       1                           0
       Infusion Reconciliation in Other Location        1                    1                  1                       1                           0
```

## Frozen medication event semantics

Flushed, Confirmed, and blank/null events remain separate and
outside the given/not-given decision denominator.

```text
                 drug_class  all_whitelist_events_n   given_n  not_given_n  flushed_n  confirmed_n  blank_n  other_excluded_n  not_given_pct_decision_denominator
    electrolyte_replacement                  941900  701114.0      44267.0        9.0       2872.0 174963.0           18675.0                            5.938842
                    insulin                 2614086 1391290.0     178807.0        3.0      58581.0  18555.0          966850.0                           11.388277
intra_abdominal_antibiotics                 1312435 1213438.0      36474.0        0.0         29.0   5045.0           57449.0                            2.918125
                 prokinetic                  136985  120548.0      15704.0        0.0          0.0     91.0             642.0                           11.525702
   stress_ulcer_prophylaxis                 1241812 1178149.0      52688.0        0.0       1744.0    633.0            8598.0                            4.280664
            vte_prophylaxis                 2181347 1648497.0     134406.0      223.0     294570.0    906.0          102745.0                            7.538604
```

## eMAR-detail availability

`dose_given` is the administered-dose field. `dose_due` is
reported but never substituted for actual dose. MIMIC-IV has no
dedicated structured 'reason not given' field; the available
proxies are event_txt, complete_dose_not_given,
administration_type, barcode_type, and reason_for_no_barcode.

```text
                 drug_class event_category  events_n  detail_linked_n  detail_linked_pct  dose_given_available_n  dose_given_available_pct  dose_given_with_unit_n  dose_given_with_unit_pct  dose_due_available_n  product_amount_available_n  route_available_n  administration_type_available_n  reason_for_no_barcode_available_n  complete_dose_not_given_yes_n
    electrolyte_replacement          blank    174963         174963.0              100.0                174638.0                 99.814246                174633.0                 99.811389              174355.0                    167279.0             5893.0                         174686.0                             7352.0                            0.0
    electrolyte_replacement      confirmed      2872           2872.0              100.0                   102.0                  3.551532                   102.0                  3.551532                2609.0                      1697.0                0.0                           2705.0                              180.0                            0.0
    electrolyte_replacement        flushed         9              9.0              100.0                     9.0                100.000000                     9.0                100.000000                   9.0                         9.0                0.0                              9.0                                0.0                            0.0
    electrolyte_replacement   given_strict    701114         701114.0              100.0                698575.0                 99.637862                698429.0                 99.617038              680293.0                    678037.0           166757.0                         691978.0                            21228.0                            0.0
    electrolyte_replacement      not_given     44267          44267.0              100.0                 16230.0                 36.663881                 16230.0                 36.663881               42066.0                     15678.0              313.0                          44227.0                              551.0                        10757.0
    electrolyte_replacement other_excluded     18675          18675.0              100.0                 10892.0                 58.323963                 10892.0                 58.323963               16266.0                      9666.0               70.0                          18611.0                             3857.0                            0.0
                    insulin          blank     18555          18555.0              100.0                 18117.0                 97.639450                 18104.0                 97.569388               14461.0                     13253.0                0.0                          18553.0                             1181.0                            0.0
                    insulin      confirmed     58581          58581.0              100.0                   301.0                  0.513818                   301.0                  0.513818               23231.0                        11.0                0.0                          58450.0                             3903.0                            0.0
                    insulin        flushed         3              3.0              100.0                     3.0                100.000000                     3.0                100.000000                   2.0                         1.0                0.0                              3.0                                0.0                            0.0
                    insulin   given_strict   1391290        1391290.0              100.0               1375867.0                 98.891460               1375243.0                 98.846610             1291422.0                    467768.0                0.0                        1391141.0                            78569.0                            0.0
                    insulin      not_given    178807         178807.0              100.0                  5362.0                  2.998764                  5349.0                  2.991494               85518.0                      2624.0                0.0                         178785.0                              501.0                         1696.0
                    insulin other_excluded    966850         966850.0              100.0                   405.0                  0.041889                   401.0                  0.041475               18920.0                       110.0                0.0                         966834.0                             3033.0                            0.0
intra_abdominal_antibiotics          blank      5045           5045.0              100.0                  5034.0                 99.781962                  5034.0                 99.781962                5030.0                      4845.0               52.0                           5032.0                              184.0                            0.0
intra_abdominal_antibiotics      confirmed        29             29.0              100.0                    20.0                 68.965517                    20.0                 68.965517                  29.0                        23.0                0.0                             29.0                                6.0                            0.0
intra_abdominal_antibiotics   given_strict   1213438        1213438.0              100.0               1207081.0                 99.476117               1206700.0                 99.444718             1204152.0                   1161407.0           203340.0                        1212087.0                            31913.0                            0.0
intra_abdominal_antibiotics      not_given     36474          36474.0              100.0                  4740.0                 12.995558                  4740.0                 12.995558               35304.0                      4547.0                8.0                          36465.0                              131.0                          105.0
intra_abdominal_antibiotics other_excluded     57449          57449.0              100.0                 47910.0                 83.395707                 47910.0                 83.395707               56572.0                     40757.0              172.0                          57432.0                            14664.0                            0.0
                 prokinetic          blank        91             91.0              100.0                    91.0                100.000000                    91.0                100.000000                  82.0                        80.0               13.0                             91.0                               11.0                            0.0
                 prokinetic   given_strict    120548         120548.0              100.0                120533.0                 99.987557                120533.0                 99.987557              119786.0                    117269.0            47283.0                         120538.0                             3225.0                            0.0
                 prokinetic      not_given     15704          15704.0              100.0                   492.0                  3.132960                   492.0                  3.132960               15523.0                       480.0                1.0                          15703.0                               14.0                           12.0
                 prokinetic other_excluded       642            642.0              100.0                    24.0                  3.738318                    24.0                  3.738318                 511.0                        23.0               14.0                            642.0                                1.0                            0.0
   stress_ulcer_prophylaxis          blank       633            633.0              100.0                   630.0                 99.526066                   630.0                 99.526066                 629.0                       586.0               67.0                            632.0                               41.0                            0.0
   stress_ulcer_prophylaxis      confirmed      1744           1744.0              100.0                     0.0                  0.000000                     0.0                  0.000000                1641.0                       586.0                0.0                           1744.0                               74.0                            0.0
   stress_ulcer_prophylaxis   given_strict   1178149        1178149.0              100.0               1176733.0                 99.879811               1176639.0                 99.871833             1176247.0                   1152197.0           331764.0                        1177229.0                            22677.0                            0.0
   stress_ulcer_prophylaxis      not_given     52688          52688.0              100.0                  5479.0                 10.398952                  5479.0                 10.398952               50197.0                      5387.0                8.0                          52678.0                              102.0                          113.0
   stress_ulcer_prophylaxis other_excluded      8598           8598.0              100.0                  2609.0                 30.344266                  2607.0                 30.321005                5615.0                      2326.0               92.0                           8596.0                             1098.0                            0.0
            vte_prophylaxis          blank       906            906.0              100.0                   148.0                 16.335541                   148.0                 16.335541                 836.0                       117.0                0.0                            896.0                               22.0                            0.0
            vte_prophylaxis      confirmed    294570         294570.0              100.0                   775.0                  0.263095                   755.0                  0.256306              268495.0                     43683.0                0.0                         294327.0                            22642.0                            0.0
            vte_prophylaxis        flushed       223            223.0              100.0                   222.0                 99.551570                   222.0                 99.551570                   0.0                       211.0                0.0                              0.0                                0.0                            0.0
            vte_prophylaxis   given_strict   1648497        1648497.0              100.0               1588820.0                 96.379915               1586882.0                 96.262353             1605724.0                   1549988.0                5.0                        1646685.0                            55105.0                            0.0
            vte_prophylaxis      not_given    134406         134406.0              100.0                 14026.0                 10.435546                 14023.0                 10.433314              131212.0                     13733.0                0.0                         134369.0                              524.0                           52.0
            vte_prophylaxis other_excluded    102745         102745.0              100.0                   358.0                  0.348435                   357.0                  0.347462               98476.0                      6457.0                0.0                         102684.0                            11411.0                            0.0
```

## d_items entries with zero fact rows

- Complete zero-row list: 1,037 entries.
- inputevents itemid 225925 Potassium Phosphate reproduced with
  zero fact rows.

## eICU semantic contrast

eICU is summarized only as interface semantics, not external
validation.

```text
source_table                  role                       tier                                             semantics  labels_n  rows_n  stays_n_sum  positive_rows_n
infusionDrug             nutrition            exclude_or_zero                   rate/amount chart at infusionoffset        17    1053          214              201
infusionDrug             nutrition strict_administration_like                   rate/amount chart at infusionoffset        25   24091          525            24091
infusionDrug phosphate_replacement            exclude_or_zero                   rate/amount chart at infusionoffset         9      24            9                6
infusionDrug phosphate_replacement strict_administration_like                   rate/amount chart at infusionoffset        11      87           11               87
intakeOutput             nutrition            exclude_or_zero            positive documented intake at event offset     23401  573592       188270           524693
intakeOutput             nutrition strict_administration_like            positive documented intake at event offset     16281  487533        48798           487533
intakeOutput phosphate_replacement            exclude_or_zero            positive documented intake at event offset        10      95           20                0
intakeOutput phosphate_replacement strict_administration_like            positive documented intake at event offset       398    3763          989             3763
  medication             nutrition      exclude_non_nutrition order/route text; not actual nutrition administration      1015   13137         7553                0
  medication             nutrition           order_audit_only order/route text; not actual nutrition administration       212   20841         2376                0
  medication phosphate_replacement     exclude_false_positive        order/planned start; not actual administration       152    3064         2766                0
  medication phosphate_replacement           order_audit_only        order/planned start; not actual administration       692   32736        21717                0
   treatment             nutrition         documentation_only            treatment documentation; not actual intake        35   57882        11350                0
   treatment phosphate_replacement         documentation_only    treatment documentation; not actual administration        18    4110          857                0
```

## Machine-readable audit summary

```text
{'emar_rows_n': 42808593.0, 'poe_id_nonmissing_n': 42808593.0, 'poe_id_any_link_n': 41211672.0, 'poe_id_identity_link_n': 41176690.0, 'poe_id_identity_mismatch_n': 34982.0, 'poe_id_nonmissing_pct': 100.0, 'poe_any_link_among_nonmissing_pct': 96.26962511942403, 'poe_identity_link_among_nonmissing_pct': 96.18790788101819, 'distribution_sum_n': 42808593, 'distribution_reconciles': True, 'medication_candidate_rows_n': 8413891, 'product_candidate_rows_n': 4423666, 'whitelist_event_rows_n': 8428565, 'zero_fact_items_n': 1037, 'inputevents_225925_reproduced': True, 'mimic_whitelist_rows_n': 168, 'eicu_whitelist_rows_n': 42276, 'eicu_relevant_zip_members_n': 5}
```
