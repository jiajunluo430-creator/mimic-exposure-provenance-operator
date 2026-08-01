# Stage 02 implementation-failure diagnostic

This is an implementation audit, not a statistical result.
The frozen scientific contract was not changed.

## Committed checkpoint inventory

```text
                  table_name  row_count  column_count                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           columns
                 adult_stays      94444            28                                                                                                              subject_id:BIGINT|hadm_id:BIGINT|stay_id:BIGINT|first_careunit:VARCHAR|last_careunit:VARCHAR|intime:TIMESTAMP|outtime:TIMESTAMP|icu_los_days:DOUBLE|gender:VARCHAR|anchor_age:INTEGER|anchor_year:INTEGER|anchor_year_group:VARCHAR|dod:DATE|admittime:TIMESTAMP|dischtime:TIMESTAMP|deathtime:TIMESTAMP|admission_type:VARCHAR|admission_location:VARCHAR|discharge_location:VARCHAR|race:VARCHAR|hospital_expire_flag:INTEGER|age_at_icu:BIGINT|subject_stay_order:BIGINT|hadm_stay_order:BIGINT|subject_icu_stays_n:BIGINT|hadm_icu_stays_n:BIGINT|emergency_admission:INTEGER|anchor_era:VARCHAR
                 d_items_all       4095             7                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             itemid:BIGINT|label:VARCHAR|abbreviation:VARCHAR|linksto:VARCHAR|category:VARCHAR|unitname:VARCHAR|param_type:VARCHAR
         d_items_fact_counts       3058             3                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  linksto:VARCHAR|itemid:BIGINT|fact_rows_n:BIGINT
   detail_product_candidates    4423666             5                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            emar_id:VARCHAR|emar_seq:BIGINT|drug_class:VARCHAR|ingredient:VARCHAR|subclass:VARCHAR
       emar_detail_event_agg    8427956            16                                                                                                                                                                                                                                                                                                                  emar_id:VARCHAR|emar_seq:BIGINT|detail_rows_n:BIGINT|any_complete_dose_not_given:BOOLEAN|dose_given_num:DOUBLE|dose_given_unit:VARCHAR|dose_due_num:DOUBLE|dose_due_unit:VARCHAR|product_amount_given_num:DOUBLE|product_unit:VARCHAR|route:VARCHAR|administration_type:VARCHAR|barcode_type:VARCHAR|reason_for_no_barcode:VARCHAR|product_description:VARCHAR|product_description_other:VARCHAR
        emar_detail_relevant   16145446            27                             subject_id:BIGINT|emar_id:VARCHAR|emar_seq:BIGINT|parent_field_ordinal:VARCHAR|administration_type:VARCHAR|pharmacy_id:VARCHAR|barcode_type:VARCHAR|reason_for_no_barcode:VARCHAR|complete_dose_not_given:VARCHAR|dose_due:VARCHAR|dose_due_unit:VARCHAR|dose_given:VARCHAR|dose_given_unit:VARCHAR|product_amount_given:VARCHAR|product_unit:VARCHAR|product_code:VARCHAR|product_description:VARCHAR|product_description_other:VARCHAR|infusion_rate:VARCHAR|infusion_rate_unit:VARCHAR|route:VARCHAR|infusion_complete:VARCHAR|new_iv_bag_hung:VARCHAR|continued_infusion_in_other_location:VARCHAR|product_drug_class:VARCHAR|product_ingredient:VARCHAR|product_subclass:VARCHAR
   emar_event_txt_full_audit         73             6                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               event_txt:VARCHAR|rows_n:BIGINT|poe_id_nonmissing_n:BIGINT|poe_id_any_link_n:BIGINT|poe_id_identity_link_n:BIGINT|poe_id_identity_mismatch_n:BIGINT
  emar_medication_candidates    8413891            14                                                                                                                                                                                                                                                                                                                                                                                                                                              subject_id:BIGINT|hadm_id:BIGINT|emar_id:VARCHAR|emar_seq:BIGINT|poe_id:VARCHAR|pharmacy_id:VARCHAR|charttime:TIMESTAMP|scheduletime:TIMESTAMP|medication:VARCHAR|event_txt:VARCHAR|drug_class:VARCHAR|ingredient:VARCHAR|subclass:VARCHAR|name_match_source:VARCHAR
      emar_medication_events    8428565            31 subject_id:BIGINT|hadm_id:BIGINT|emar_id:VARCHAR|emar_seq:BIGINT|poe_id:VARCHAR|pharmacy_id:VARCHAR|charttime:TIMESTAMP|scheduletime:TIMESTAMP|medication:VARCHAR|event_txt:VARCHAR|drug_class:VARCHAR|ingredient:VARCHAR|subclass:VARCHAR|name_match_source:VARCHAR|detail_rows_n:BIGINT|any_complete_dose_not_given:BOOLEAN|dose_given_num:DOUBLE|dose_given_unit:VARCHAR|dose_due_num:DOUBLE|dose_due_unit:VARCHAR|product_amount_given_num:DOUBLE|product_unit:VARCHAR|route:VARCHAR|administration_type:VARCHAR|barcode_type:VARCHAR|reason_for_no_barcode:VARCHAR|product_description:VARCHAR|product_description_other:VARCHAR|event_category:VARCHAR|poe_id_any_link:BOOLEAN|poe_id_identity_link:BOOLEAN
     emar_product_candidates    4423666            14                                                                                                                                                                                                                                                                                                                                                                                                                                              subject_id:BIGINT|hadm_id:BIGINT|emar_id:VARCHAR|emar_seq:BIGINT|poe_id:VARCHAR|pharmacy_id:VARCHAR|charttime:TIMESTAMP|scheduletime:TIMESTAMP|medication:VARCHAR|event_txt:VARCHAR|drug_class:VARCHAR|ingredient:VARCHAR|subclass:VARCHAR|name_match_source:VARCHAR
         emar_whitelist_base    8428565            14                                                                                                                                                                                                                                                                                                                                                                                                                                              subject_id:BIGINT|hadm_id:BIGINT|emar_id:VARCHAR|emar_seq:BIGINT|poe_id:VARCHAR|pharmacy_id:VARCHAR|charttime:TIMESTAMP|scheduletime:TIMESTAMP|medication:VARCHAR|event_txt:VARCHAR|drug_class:VARCHAR|ingredient:VARCHAR|subclass:VARCHAR|name_match_source:VARCHAR
    pharmacy_name_candidates    3943333            14                                                                                                                                                                                                                                                                                                                                                                                                   subject_id:BIGINT|hadm_id:BIGINT|pharmacy_id:VARCHAR|poe_id:VARCHAR|pharmacy_starttime:TIMESTAMP|pharmacy_stoptime:TIMESTAMP|pharmacy_medication:VARCHAR|pharmacy_status:VARCHAR|pharmacy_route:VARCHAR|pharmacy_frequency:VARCHAR|sliding_scale:VARCHAR|drug_class:VARCHAR|ingredient:VARCHAR|subclass:VARCHAR
                poe_identity   52212109             8                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 poe_id:VARCHAR|subject_id:BIGINT|hadm_id:BIGINT|poe_rows_n:BIGINT|subject_values_n:BIGINT|hadm_values_n:BIGINT|first_ordertime:TIMESTAMP|last_ordertime:TIMESTAMP
prescription_name_dictionary      14614             2                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             name_key:VARCHAR|source_rows_n:BIGINT
       prescription_name_map      14614             3                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   name_key:VARCHAR|source_rows_n:BIGINT|direct_ingredient:VARCHAR
```

The interrupted transaction did not commit
`prescription_prefilter`; the active statement was its
`CREATE OR REPLACE TABLE ... AS` query.

## Legacy execution plan

EXPLAIN binding elapsed: 16.234 seconds.
High-risk join operators: BLOCKWISE_NL_JOIN.

```text
physical_plan
┌───────────────────────────┐
│         PROJECTION        │
│    ────────────────────   │
│         subject_id        │
│          hadm_id          │
│        pharmacy_id        │
│           poe_id          │
│          poe_seq          │
│         starttime         │
│          stoptime         │
│         drug_type         │
│            drug           │
│     formulary_drug_cd     │
│            gsn            │
│            ndc            │
│       prod_strength       │
│        dose_val_rx        │
│        dose_unit_rx       │
│      doses_per_24_hrs     │
│           route           │
│     direct_ingredient     │
│                           │
│      ~5,774,272 rows      │
└─────────────┬─────────────┘
┌─────────────┴─────────────┐
│         PROJECTION        │
│    ────────────────────   │
│             #0            │
│             #1            │
│             #2            │
│             #3            │
│             #4            │
│             #5            │
│             #6            │
│             #7            │
│             #8            │
│             #9            │
│            #10            │
│            #11            │
│            #12            │
│            #13            │
│            #14            │
│            #15            │
│            #16            │
│            #17            │
│                           │
│      ~5,774,272 rows      │
└─────────────┬─────────────┘
┌─────────────┴─────────────┐
│           FILTER          │
│    ────────────────────   │
│ ((direct_ingredient IS NOT│
│  NULL) OR (pharmacy_id IS │
│   NOT NULL) OR (poe_id IS │
│         NOT NULL))        │
│                           │
│      ~5,774,272 rows      │
└─────────────┬─────────────┘
┌─────────────┴─────────────┐
│     BLOCKWISE_NL_JOIN     │
│    ────────────────────   │
│      Join Type: LEFT      │
│                           │
│         Condition:        │
│ ((((((TRY_CAST(subject_id │
│  AS BIGINT) = subject_id) │
│  AND (TRY_CAST(hadm_id AS ├────────────────────────────────────────────────────────────────────────┐
│  BIGINT) = hadm_id)) AND  │                                                                        │
│  (poe_id = poe_id)) AND ( │                                                                        │
│ (pharmacy_id IS NULL) OR (│                                                                        │
│ "trim"(pharmacy_id) = ''))│                                                                        │
│ ) AND (poe_id IS NOT NULL)│                                                                        │
│ ) AND ("trim"(poe_id) != '│                                                                        │
│            '))            │                                                                        │
└─────────────┬─────────────┘                                                                        │
┌─────────────┴─────────────┐                                                          ┌─────────────┴─────────────┐
│     BLOCKWISE_NL_JOIN     │                                                          │         PROJECTION        │
│    ────────────────────   │                                                          │    ────────────────────   │
│      Join Type: LEFT      │                                                          │__internal_decompress_integ│
│                           │                                                          │  ral_bigint(#0, 10000032) │
│         Condition:        │                                                          │__internal_decompress_integ│
│  (((((TRY_CAST(subject_id │                                                          │  ral_bigint(#1, 20000019) │
│  AS BIGINT) = subject_id) ├───────────────────────────────────────────┐              │__internal_decompress_strin│
│  AND (TRY_CAST(hadm_id AS │                                           │              │           g(#2)           │
│  BIGINT) = hadm_id)) AND  │                                           │              │                           │
│ (pharmacy_id = pharmacy_id│                                           │              │                           │
│ )) AND (pharmacy_id IS NOT│                                           │              │                           │
│     NULL)) AND ("trim"    │                                           │              │                           │
│   (pharmacy_id) != ''))   │                                           │              │       ~788,666 rows       │
└─────────────┬─────────────┘                                           │              └─────────────┬─────────────┘
┌─────────────┴─────────────┐                             ┌─────────────┴─────────────┐┌─────────────┴─────────────┐
│         HASH_JOIN         │                             │         PROJECTION        ││       HASH_GROUP_BY       │
│    ────────────────────   │                             │    ────────────────────   ││    ────────────────────   │
│      Join Type: LEFT      │                             │__internal_decompress_integ││          Groups:          │
│                           │                             │  ral_bigint(#0, 10000032) ││             #0            │
│        Conditions:        │                             │__internal_decompress_integ││             #1            │
│  lower("trim"(((COALESCE  │                             │  ral_bigint(#1, 20000019) ││             #2            │
│   (drug, '') || ' ') ||   ├──────────────┐              │__internal_decompress_strin││                           │
│          COALESCE         │              │              │           g(#2)           ││                           │
│ (formulary_drug_cd, ''))))│              │              │                           ││                           │
│         = name_key        │              │              │                           ││                           │
│                           │              │              │                           ││                           │
│      ~5,774,272 rows      │              │              │       ~788,666 rows       ││       ~788,666 rows       │
└─────────────┬─────────────┘              │              └─────────────┬─────────────┘└─────────────┬─────────────┘
┌─────────────┴─────────────┐┌─────────────┴─────────────┐┌─────────────┴─────────────┐┌─────────────┴─────────────┐
│       READ_CSV_AUTO       ││          SEQ_SCAN         ││       HASH_GROUP_BY       ││         PROJECTION        │
│    ────────────────────   ││    ────────────────────   ││    ────────────────────   ││    ────────────────────   │
│         Function:         ││           Table:          ││          Groups:          ││         subject_id        │
│       READ_CSV_AUTO       ││      n1_validity.main     ││             #0            ││          hadm_id          │
│                           ││   .prescription_name_map  ││             #1            ││           poe_id          │
│        Projections:       ││                           ││             #2            ││                           │
│            drug           ││   Type: Sequential Scan   ││                           ││                           │
│     formulary_drug_cd     ││                           ││                           ││                           │
│         subject_id        ││        Projections:       ││                           ││                           │
│          hadm_id          ││          name_key         ││                           ││                           │
│        pharmacy_id        ││     direct_ingredient     ││                           ││                           │
│           poe_id          ││                           ││                           ││                           │
│          poe_seq          ││                           ││                           ││                           │
│         starttime         ││                           ││                           ││                           │
│          stoptime         ││                           ││                           ││                           │
│         drug_type         ││                           ││                           ││                           │
│            gsn            ││                           ││                           ││                           │
│            ndc            ││                           ││                           ││                           │
│       prod_strength       ││                           ││                           ││                           │
│        dose_val_rx        ││                           ││                           ││                           │
│        dose_unit_rx       ││                           ││                           ││                           │
│      doses_per_24_hrs     ││                           ││                           ││                           │
│           route           ││                           ││                           ││                           │
│                           ││                           ││                           ││                           │
│      ~5,774,272 rows      ││        ~14,614 rows       ││       ~788,666 rows       ││       ~788,666 rows       │
└───────────────────────────┘└───────────────────────────┘└─────────────┬─────────────┘└─────────────┬─────────────┘
                                                          ┌─────────────┴─────────────┐┌─────────────┴─────────────┐
                                                          │         PROJECTION        ││         PROJECTION        │
                                                          │    ────────────────────   ││    ────────────────────   │
                                                          │         subject_id        ││__internal_compress_integra│
                                                          │          hadm_id          ││  l_uinteger(#0, 10000032) │
                                                          │        pharmacy_id        ││__internal_compress_integra│
                                                          │                           ││  l_uinteger(#1, 20000019) │
                                                          │                           ││__internal_compress_string_│
                                                          │                           ││        uhugeint(#2)       │
                                                          │                           ││                           │
                                                          │       ~788,666 rows       ││       ~788,666 rows       │
                                                          └─────────────┬─────────────┘└─────────────┬─────────────┘
                                                          ┌─────────────┴─────────────┐┌─────────────┴─────────────┐
                                                          │         PROJECTION        ││         PROJECTION        │
                                                          │    ────────────────────   ││    ────────────────────   │
                                                          │__internal_compress_integra││         subject_id        │
                                                          │  l_uinteger(#0, 10000032) ││          hadm_id          │
                                                          │__internal_compress_integra││           poe_id          │
                                                          │  l_uinteger(#1, 20000019) ││                           │
                                                          │__internal_compress_string_││                           │
                                                          │        uhugeint(#2)       ││                           │
                                                          │                           ││                           │
                                                          │       ~788,666 rows       ││       ~788,666 rows       │
                                                          └─────────────┬─────────────┘└─────────────┬─────────────┘
                                                          ┌─────────────┴─────────────┐┌─────────────┴─────────────┐
                                                          │         PROJECTION        ││          SEQ_SCAN         │
                                                          │    ────────────────────   ││    ────────────────────   │
                                                          │         subject_id        ││           Table:          │
                                                          │          hadm_id          ││      n1_validity.main     │
                                                          │        pharmacy_id        ││ .pharmacy_name_candidates │
                                                          │                           ││                           │
                                                          │                           ││   Type: Sequential Scan   │
                                                          │                           ││                           │
                                                          │                           ││        Projections:       │
                                                          │                           ││           poe_id          │
                                                          │                           ││         subject_id        │
                                                          │                           ││          hadm_id          │
                                                          │                           ││                           │
                                                          │                           ││          Filters:         │
                                                          │                           ││ (poe_id IS NOT NULL) AND (│
                                                          │                           ││   "trim"(poe_id) != '')   │
                                                          │                           ││                           │
                                                          │       ~788,666 rows       ││       ~788,666 rows       │
                                                          └─────────────┬─────────────┘└───────────────────────────┘
                                                          ┌─────────────┴─────────────┐
                                                          │          SEQ_SCAN         │
                                                          │    ────────────────────   │
                                                          │           Table:          │
                                                          │      n1_validity.main     │
                                                          │ .pharmacy_name_candidates │
                                                          │                           │
                                                          │   Type: Sequential Scan   │
                                                          │                           │
                                                          │        Projections:       │
                                                          │        pharmacy_id        │
                                                          │         subject_id        │
                                                          │          hadm_id          │
                                                          │                           │
                                                          │          Filters:         │
                                                          │ (pharmacy_id IS NOT NULL) │
                                                          │  AND ("trim"(pharmacy_id) │
                                                          │           != '')          │
                                                          │                           │
                                                          │       ~788,666 rows       │
                                                          └───────────────────────────┘

```

## Existing materialized-table key cardinality

```text
              table_name  total_rows                                       key  nonmissing_rows_n  unique_nonmissing_keys_n  max_rows_per_key  mean_rows_per_nonmissing_key  same_key_self_join_rows_n  duplicate_excess_rows_n  elapsed_seconds
pharmacy_name_candidates     3943333                                subject_id            3943333                    178615              2353                     22.077278                  493308791                  3764718            0.046
pharmacy_name_candidates     3943333                                   hadm_id            3943333                    419601              1337                      9.397816                  127903219                  3523732            0.040
pharmacy_name_candidates     3943333                                    poe_id            3909737                   2846326                21                      1.373608                    7748379                  1063411            0.177
pharmacy_name_candidates     3943333                               pharmacy_id            3943333                   3943333                 1                      1.000000                    3943333                        0            0.188
pharmacy_name_candidates     3943333                 subject_id+hadm_id+poe_id            3909737                   2846326                21                      1.373608                    7748379                  1063411            0.211
pharmacy_name_candidates     3943333            subject_id+hadm_id+pharmacy_id            3943333                   3943333                 1                      1.000000                    3943333                        0            0.214
            poe_identity    52212109                                subject_id           52212109                    222121             20457                    235.061561                52448679751                 51989988            0.563
            poe_identity    52212109                                   hadm_id           52212109                    538616              6126                     96.937538                13870662759                 51673493            0.964
            poe_identity    52212109                                    poe_id           52212109                  52212109                 1                      1.000000                   52212109                        0            2.785
  emar_medication_events     8428565                                subject_id            8428565                    130980              9796                     64.350015                 4091326507                  8297585            0.070
  emar_medication_events     8428565                                   hadm_id            8218421                    246614              6775                     33.325038                 1397342329                  7971807            0.078
  emar_medication_events     8428565                                    poe_id            8428565                   1834757               817                      4.593832                  155732069                  6593808            0.149
  emar_medication_events     8428565                               pharmacy_id            6686970                   1681436               590                      3.976940                  103312718                  5005534            0.196
  emar_medication_events     8428565                         poe_id+drug_class            8428565                   1834888               817                      4.593504                  155715003                  6593677            0.230
  emar_medication_events     8428565      subject_id+hadm_id+poe_id+drug_class            8218421                   1763427               817                      4.660483                  152263983                  6454994            0.253
  emar_medication_events     8428565 subject_id+hadm_id+pharmacy_id+drug_class            6569352                   1652241               590                      3.976025                  101229488                  4917111            0.271
```

## Implementation conclusion

The failed implementation placed conditional LEFT JOINs and
post-join OR filtering directly above a full gzip CSV scan.
The replacement must materialize a narrow prescription
projection, split direct-name, pharmacy-id, and fallback-POE
candidate paths, union/deduplicate them at the frozen order
analysis unit, aggregate eMAR before joining, and checkpoint
every stage.
