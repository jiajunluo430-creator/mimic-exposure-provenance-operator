# Structured literature-reporting validator contract v1.0

Frozen: 2026-08-05, before transforming the existing 40-study coding table.  
Status: binding method-evaluation addendum.

## Purpose

Transform the already completed single-primary-coder audit into records that
conform to `medication_exposure_reporting.schema.json`, and use the same public
validator to reproduce the frozen reporting counts. The validator reads human-
coded structured fields. It does not infer reporting quality from article text,
and no AI/text-assist output contributes to the primary result.

## Frozen input

- 40 studies in the previously frozen sample, with main text reviewed for all;
- 55/56 linked supplementary files reviewed and all three article-specific
  repositories retrieved/reviewed;
- authoritative coding table:
  `published_operator_landscape_expanded_evidence_sample.csv`;
- evidence-scope table: `published_operator_evidence_scope.csv`;
- evidence-scope coding change table:
  `published_operator_landscape_evidence_scope_coding_diff.csv`;
- one primary coder only; the independent 20% worksheet is blank.

No new study is added or removed. Open-access filtering remains a limitation
and the sample is not relabeled a systematic review.

## Deterministic field mapping

| Existing field | Reporting-schema dimension | Mapping |
|---|---|---|
| `named_native_table_reported` | `source_layer` | true = reported; false = missing; unclear = ambiguous |
| `database_identity_rule_reported` | `identity_rule` | same mapping |
| `time_origin_and_window_reported` | `time_origin_window` | same mapping |
| `event_semantics_reported` | `event_semantics_map` | same mapping |
| `dose_or_route_reported` | `required_metadata` | same mapping |
| `fully_executable_exposure_operator` | operational complete operator | direct frozen derived indicator |

For positive fields, a short paraphrased evidence location is retained. The
single supplement-driven code change identified in the frozen difference table
is labeled supplement evidence; otherwise positive evidence is attributed to
the main-text coding packet. No article full text or long quotation is copied.

Repository version/hash indicators are false unless explicitly present in the
frozen evidence, and are never inferred from a generic MIT-LCP repository.

## Required outputs and exact gates

- 40 schema-valid records;
- named native source 7/40;
- executable identity 2/40;
- time origin/window 35/40;
- native event semantics 0/40;
- dose/route 30/40;
- complete executable operator 0/40;
- study-level missing-dimension list and count of reported core dimensions;
- aggregate JSON/TSV/Markdown/HTML validator outputs;
- `primary_validator_mode=structured_human_coded_input` and
  `text_assist_used_for_primary_results=false`.

Any mismatch creates a mapping diagnostic and stops the primary-count claim;
the frozen source codes are not changed to force agreement.

## Independent recoding boundary

Infrastructure will be supplied for blinded import and agreement analysis.
Missing, ambiguous, reported, and not-applicable are separate categories for
agreement. Percent agreement and unweighted Cohen kappa are computed only after
a genuinely independent human returns a completed file. Codex/the same AI may
not populate it or act as a second coder. Until then, the required status is
`AUTHOR_ACTION_REQUIRED_SECOND_CODER`; no kappa is reported.
