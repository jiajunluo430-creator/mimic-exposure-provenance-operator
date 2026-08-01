# Nonconversion timing correction v1.0

**Versioned after a failed implementation audit and before generating the
corrected mechanism table:** 31 July 2026

## Failure retained

The first implementation aggregated any later POE/pharmacy closure state over
the lifetime of an order. It classified 91,009/93,281 nonconverted units as
cancelled/discontinued. That implementation is invalid for mechanistic
interpretation because nearly every historical order can eventually become
inactive or discontinued. The counts are retained only in the implementation
log and must not enter the manuscript.

## Corrected primary rule

The primary cancellation/discontinuation category now requires a timed POE
transaction that explicitly contains `cancel`, `discontinu`, or a standalone
`dc` token, or a POE row whose `discontinue_of_poe_id` points to the candidate
order. The transaction time must fall from two hours before through six hours
after the candidate order time. This interval is fixed to the parent
conversion timing tolerance and is not chosen from the observed counts.

Untimed or later `Discontinued`, `Inactive`, `Stopped`, `Complete`, pharmacy
status, and `discontinued_by_poe_id` evidence remains available as a
nonexclusive audit flag but cannot assign the primary mechanism category.

The remaining hierarchy is unchanged:

1. early explicit cancellation/discontinuation transaction;
2. conditional/PRN/one-time protocol evidence;
3. same-class strict-given event in the frozen window without qualifying POE
   identity linkage;
4. no same-class strict-given event in the frozen window.

These remain documentation-evidence categories and are not claims about
clinical appropriateness or true nonadministration.
