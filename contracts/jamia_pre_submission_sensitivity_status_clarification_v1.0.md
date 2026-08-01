# Status-semantics clarification for pre-submission addendum

**Frozen before scanning POE or pharmacy status distributions:** 31 July 2026

This clarification overrides only the first category in S4 of
`jamia_pre_submission_sensitivity_addendum_v1.0.md`.

## Explicit cancellation/discontinuation category

An order enters the primary cancellation/discontinuation category only when:

- POE `order_status`, `transaction_type`, `order_type`, or `order_subtype`
  contains an explicit `cancel`, `discontinu`, or standalone `dc` token;
- `discontinue_of_poe_id` or `discontinued_by_poe_id` is nonempty; or
- pharmacy `status` contains an explicit `cancel`, `discontinu`, or standalone
  `dc` token.

The generic values `inactive`, `stopped`, `complete`, and `completed` are not
sufficient for the primary category because they can represent normal record
closure. They will be reported as a separate, nonexclusive ambiguous-status
flag. No ambiguous status may be relabelled as clinical cancellation after
counts are inspected.

All remaining S4 hierarchy, definitions, and interpretive boundaries are
unchanged.
