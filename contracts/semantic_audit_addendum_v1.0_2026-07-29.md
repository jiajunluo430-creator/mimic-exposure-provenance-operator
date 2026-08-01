# Pre-model semantic-audit addendum v1.0

Frozen: 2026-07-29, after the mandatory full-table `event_txt` audit and
before any severity or published-association model.

This addendum does not modify, replace, or re-hash the original frozen
contract. The original literal event mapping remains the primary definition
and continues to govern every pilot gate and the final stop-loss decision.

## Reason

The mandatory audit showed that MIMIC-IV uses the vendor subtypes `Hold Dose`
and `Not Given per Sliding Scale` (including its `in Other Location` variant).
These are semantically explicit non-administration/held-dose events but are not
equal to the original literal strings `Held` and `Not Given`. In particular,
the sliding-scale subtype is common for the frozen insulin class. Omitting this
fact would make the requested held/not-given interface audit incomplete.

This is a pre-model interface-semantic repair/sensitivity, not an
outcome-driven amendment. No outcome, effect estimate, P value, or model has
been inspected.

## Locked sensitivity mapping

The authoritative mapping is
`config/event_semantics_audit_sensitivity_v1.0.csv`.

- Original `given_strict` and original `not_given` events are retained.
- Exact normalized `hold dose` is added as `not_given_audit_sensitivity`.
- Normalized strings beginning with `not given per sliding scale` are added as
  `not_given_audit_sensitivity`.
- No other `Not Started`, `Not Applied`, `Not Flushed`, reconciliation,
  stopped, delayed, confirmed, blank, or other event is added.
- `Flushed`, `Confirmed`, and blank/null remain separately excluded.
- The same VTE POE-link restriction, covariates, shift definition, organ
  support, and stay-clustered standard errors are used.

## Reporting boundary

Both literal-primary and audit-semantic-sensitivity rates/models are reported.
The sensitivity cannot replace the frozen primary, change GO/BACKUP/NO-GO,
trigger class/window expansion, or be selected because of statistical
significance.
