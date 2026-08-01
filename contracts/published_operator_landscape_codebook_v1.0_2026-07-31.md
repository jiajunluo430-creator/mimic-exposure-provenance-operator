# Published MIMIC-IV Medication-Exposure Operator Audit Codebook v1.0

Frozen: 2026-07-31 (America/Chicago), before supplement and linked-repository
content was reviewed.

## Unit and evidence scope

The coding unit is one included medication exposure-outcome study in the
prespecified 40-study sample. Review the article main text, all article-linked
supplementary files that can be retrieved, and article-specific code/data
repositories explicitly linked from the article or its supplements. Record
retrieval attempts and failures. A generic citation or link to the MIMIC code
repository is contextual documentation, not article-specific executable code.

Evidence may upgrade an existing code only when the evidence is explicit in an
audited source. Absence of a retrievable supplement or repository is coded as
`not verifiable`, never as evidence that a feature was absent. Evidence snippets
must be paraphrased and accompanied by the source location and file/URL.

## Coding dimensions

### 1. Exposure source layer

Allowed values are `order`, `administration`, `hybrid`, and `unspecified`.

- `order`: exposure is defined from a prescription, order, or medication-order
  record without requiring a documented administered event.
- `administration`: exposure requires a documented medication delivery or
  administration record.
- `hybrid`: the study explicitly combines or reconciles at least two source
  layers, such as prescriptions plus eMAR.
- `unspecified`: the report states medication use or treatment status but the
  record layer cannot be determined.

### 2. Named native medication table/source

Code `yes` only when a native MIMIC table or an unambiguous native extract is
named, for example `prescriptions`, `pharmacy`, `poe`, `emar`, `inputevents`, or
an explicitly named derived table whose native inputs are stated. A clinical
phrase such as "medication administration record" without a database object is
`no`.

### 3. Database-executable identity rule

Code `yes` only when the reported information allows a reviewer to implement
the medication identity predicate: a field, code system, explicit code/name
list, exact regular expression, reusable query, or equivalent identifier rule.
A drug or class name alone is `no`.

### 4. Time origin and exposure window

Code `yes` only when both the time origin and the exposure interval or state
rule are operationally specified. "During hospitalization" is acceptable when
hospital admission/discharge are the stated boundaries. An unanchored term such
as "early" is `no`.

### 5. Native event-state semantics

Code `yes` only when an administration-layer study states an executable native
event predicate that distinguishes administered events from held, not-given,
refused, flushed, confirmed-only, blank, or equivalent non-delivery states.
Simply saying "administered" or naming eMAR is `no`. For a purely order-defined
study, code `no/not applicable to the chosen layer` and retain `no` in the
binary summary so the complete operator remains non-executable as an
administration operator.

### 6. Dose or route constraint

Code `yes` when dose, route, formulation, concentration, or an explicit
dose/route inclusion rule is stated. Describing dose as a downstream covariate
without using or reporting it in the exposure construct may be documented but
does not qualify.

### 7. Fully executable exposure operator

Derived, not independently judged. Code `yes` only when all four are present:

1. named native medication table/source;
2. database-executable identity rule;
3. time origin and exposure window; and
4. native event-state semantics.

Dose/route is reported separately because some constructs do not require it.

## Independent recoding and agreement

A second coder receives the blank worksheet without the primary codes or
aggregate results. The coder reviews the same evidence scope independently.
After both worksheets are locked, report raw agreement and Cohen kappa for each
binary dimension; report a weighted or nominal agreement statistic for the
four-level source layer as prespecified by the analysts before unblinding.
Disagreements are adjudicated after agreement statistics are calculated.

Until a genuine second worksheet exists, describe the current audit as
single-primary-coder and do not report an agreement coefficient.

## Open-access sampling limitation

The frozen PubMed query returned 379 records, of which 293 met the English,
non-review, open-full-text filter. The direction of any reporting-quality bias
from excluding 86 non-open-full-text records is unknown: inaccessible articles
could report either more or less executable detail. The sample is a structured
landscape audit, not a systematic review of treatment effects.
