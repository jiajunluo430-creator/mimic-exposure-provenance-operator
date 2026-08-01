# Stage 02 VTE administration-field audit

Contract section 4.1 applies the frozen subcutaneous route
and prophylactic-dose rule to strict VTE orders. Section 4.2
defines actual administration by strict class match, ICU
timing, positive event semantics, and absence of a
complete-dose-not-given override; it explicitly does not
require a numeric administered dose.

The route and numeric-dose fields below are therefore
availability audit fields, not additional administration
eligibility gates.

```text
 vte_emar_stay_events_n  strict_given_events_n  strict_given_route_nonmissing_n  strict_given_numeric_dose_nonmissing_n  not_given_events_n
                 330521                 218831                                0                                  206872                8704
```
