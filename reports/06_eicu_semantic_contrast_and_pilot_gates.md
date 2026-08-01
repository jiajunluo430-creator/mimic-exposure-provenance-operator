# 06 — eICU semantic contrast and locked pilot gates

## eICU boundary

eICU-CRD is used only to contrast interface semantics. In the
supplied whitelist, `medication` represents order/planned-start
evidence and `treatment` represents documentation. `infusionDrug`
and `intakeOutput` are administration-like only when a
drug-specific label, positive numeric value/rate, and valid
offset coexist. No eICU treatment, timing, dose, or outcome
association is presented as external validation.

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

## Pilot gates

```text
gate_id                 domain        status                                                                                               observed
    G01       source_integrity          PASS                                                                      14/14 monitored sources unchanged
    G02              full_emar          PASS                              42,808,593/42,808,593 rows reconcile; full scan=True; ignore_errors=False
    G03               poe_link          PASS                                                       A1 identity-link=99.76%; A2 identity-link=99.71%
    G04            emar_detail          PASS                                           32 class/category rows; 7/7 requested summary fields present
    G05     dictionary_orphans          PASS                                         complete zero-row list n=1,037; inputevents 225925 fact_rows=0
    G06       event_exclusions          PASS blank_n=200,193, confirmed_n=357,796, flushed_n=235; categories stored separately from given/not-given
    G07         class_coverage          PASS                                                   6/6 frozen classes retained; eligible orders=633,081
    G08     negative_stop_loss NOT_TRIGGERED                                      all six conversion >97%=False; meaningful OASIS association=False
    G09         association_A1          PASS                                                                order OR=2.430; administration OR=2.145
    G10         association_A2          PASS                                                                order HR=1.936; administration HR=1.231
    G11 material_effect_change          PASS                                                                                    material anchors=A2
    G12          eicu_boundary          PASS                                                        14 semantic summary rows; no eICU outcome model
    G13     prohibited_methods          PASS                                                            No nomogram/ML/SHAP implementation detected
    G14        reproducibility          PASS                                                       QDP01-07=True; environment=True; validation=True
```

## Decision

**GO** — Mandatory audits passed, a material measurement discrepancy exists, and at least one primary anchor met the locked effect-change criterion.

The negative stop-loss is applied exactly as frozen. It never
permits expansion of drug classes or relaxation of time windows.
