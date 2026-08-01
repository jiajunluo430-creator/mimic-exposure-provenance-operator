# 07 — Final QDP decision

## 1. Executive decision

**GO** — Mandatory audits passed, a material measurement discrepancy exists, and at least one primary anchor met the locked effect-change criterion.

The full eMAR audit reconciled 42,808,593
rows. All six locked drug classes were retained; conversion
spanned 22.96%–44.49%, with the lowest conversion
prokinetic at 22.96%. The locked
OASIS association was OR 0.957 (95% CI 0.940–0.974). The largest primary-anchor
absolute log-effect change was
A2 at 0.453.

The prespecified A2 contrast changed from order HR 1.936 to administration HR 1.231; relative absolute log-effect change 68.5%.
All 4 prespecified A2 model variants
met the frozen material-change rule. Separately, VTE strict-given
eMAR route availability was 0/218,831; route remained an
audited attribute, not an added administration gate.

This supports only a measurement-validity/effect-sensitivity
claim. It does not establish drug efficacy, harm, optimal use,
or treatment thresholds.

## 2. Ranked candidate table

```text
 rank                                      story decision                                               claim  feasibility_5  novelty_5  ceiling_5
    1           Primary six-class validity paper       GO Exposure-definition validity and effect sensitivity              5          4          4
    2          Six-class negative-validity audit   BACKUP  Quantifies small/heterogeneous order-delivery gaps              5          3          3
    3 MIMIC/eICU interface-semantic methods note   BACKUP Documents transport limits without validation claim              5          3          2
```

### Top-3 red-team

1. The primary story can be weakened by residual semantic error:
   a documented eMAR event is not bedside observation, and POE
   links can miss legitimate administration workflows.
2. A negative-validity story remains useful but has a lower
   journal ceiling; it must retain every class and avoid
   post-result window changes.
3. eICU interface differences are descriptive only. Label/stay
   counts cannot validate MIMIC exposure or outcome effects.

## 3. Best dry-only topics

- Primary: six-class MIMIC order-to-administration validity plus
  the two frozen published-association sensitivity analyses.
- Backup: a complete negative-validity/data-quality report if
  association effects are not materially changed.

## 4. Best wet-lab-supported topics

None. Wet-lab validation is scientifically mismatched to an EHR
interface-measurement question and would expand the frozen scope.

## 5. No-go topics

- Any single-drug efficacy or safety causal study derived from
  these results.
- Nomogram, machine-learning prediction, SHAP, or
  significance-selected class/window analyses.
- Calling the eICU semantic contrast external validation.

## 6. Literature collision risk

A1 and A2 are deliberately published anchors, so their clinical
associations are not novel claims. The defensible novelty is the
pre-result, six-class exposure-measurement audit and its effect
change under identical cohorts/covariates. Collision risk is
moderate because missed-dose and medication-adherence literatures
exist; the manuscript must foreground the native POE/eMAR
identity audit and cross-association sensitivity design.

## 7. Data feasibility audit

- Full eMAR rows reconciled: 42,808,593.
- Same-subject/same-admission POE identity links: 41,176,690.
- Complete d_items zero-fact-row entries: 1,037; inputevents 225925 was
  explicitly reproduced with zero rows.
- eMAR-detail dose, route, product amount, barcode fields,
  administration type, and complete-dose-not-given were audited.
- The literal not-given model remains primary; a separately
  hashed pre-model semantic sensitivity reports `Hold Dose` and
  `Not Given per Sliding Scale*` without affecting gates.
- All derived files stay inside this project; raw sources were
  monitored as read-only.

## 8. Statistical risk

- Exposure misclassification is the estimand, but eMAR remains
  documentation rather than direct observation.
- Confounding is not solved by redefining exposure; paired
  estimates are not causal contrasts.
- A2 uses frozen ICD-coded sepsis, not exact Sepsis-3 replication.
- A1 paired estimates did not reproduce the published protective
  direction; this is an anchor-fidelity limitation, not evidence
  of a causal drug-effect reversal.
- Order and administration exposure prevalence can create sparse
  discordant cells; finite estimates and convergence are retained
  in the model audit.
- Multiplicity is descriptive; BH q-values are reported for the
  five locked not-given correlates, not used for selection.

## 9. Clinical novelty score

Overall: **4/5**. The clinical
drug-outcome associations themselves are not novel; novelty
comes from quantifying whether a common order-as-administration
assumption changes published ICU pharmacoepidemiology estimates.

## 10. Journal ceiling estimate

Methods-oriented critical-care informatics or pharmacoepidemiology journal; estimated upper target: JAMIA, Critical Care, or Pharmacoepidemiology and Drug Safety, subject to manuscript execution and reviewer fit.

## 11. Stop-loss gates

```text
gate_id        status                                                                                               observed
    G01          PASS                                                                      14/14 monitored sources unchanged
    G02          PASS                              42,808,593/42,808,593 rows reconcile; full scan=True; ignore_errors=False
    G03          PASS                                                       A1 identity-link=99.76%; A2 identity-link=99.71%
    G04          PASS                                           32 class/category rows; 7/7 requested summary fields present
    G05          PASS                                         complete zero-row list n=1,037; inputevents 225925 fact_rows=0
    G06          PASS blank_n=200,193, confirmed_n=357,796, flushed_n=235; categories stored separately from given/not-given
    G07          PASS                                                   6/6 frozen classes retained; eligible orders=633,081
    G08 NOT_TRIGGERED                                      all six conversion >97%=False; meaningful OASIS association=False
    G09          PASS                                                                order OR=2.430; administration OR=2.145
    G10          PASS                                                                order HR=1.936; administration HR=1.231
    G11          PASS                                                                                    material anchors=A2
    G12          PASS                                                        14 semantic summary rows; no eICU outcome model
    G13          PASS                                                            No nomogram/ML/SHAP implementation detected
    G14          PASS                                                       QDP01-07=True; environment=True; validation=True
```

The locked negative stop-loss was not triggered. No class was added and no window was relaxed.

## 12. Next Codex / Claude Code execution prompt

Draft the manuscript strictly from QDP 01–07 and the
machine-readable tables. Lead with exposure-measurement validity,
report all six frozen classes and both anchors, preserve the
Flushed/Confirmed/blank exclusions, state that eICU is only a
semantic contrast, and make no causal drug claim. Do not add
classes, alter windows, select by significance, or introduce
prediction methods. Re-run `scripts/07_validate_package.py` after
any presentation-only edit.
