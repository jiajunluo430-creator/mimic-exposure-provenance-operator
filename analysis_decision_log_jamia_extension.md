# JAMIA extension decision log

## Scope

This append-only record covers the source-corrected JAMIA observability
extension. It does not modify the hashed parent `analysis_decision_log.md` or
the original frozen medication, window, semantic, anchor, and model
definitions.

## J001 — Story upgrade

- Decision: frame the study as an evaluated medication-exposure
  data-generation pathway with four auditable stages: observe, link,
  interpret, and propagate.
- Rationale: the contribution is the connected sequence from
  calendar-aligned source observability to paired effect-estimate drift, not
  the already-known generic fact that medication records have provenance.
- Consequence: delivery, temporal, and semantic fidelity remain separate
  estimands; no scalar fidelity score was introduced.

## J002 — Source correction

- Decision: replace the superseded deployment interval with the documented
  2014–2016 MIMIC-IV eMAR implementation interval under frozen addendum v1.1.
- Boundary: only calendar-era assignment changed. Medication classes,
  whitelists, event mappings, windows, analysis units, anchors, covariates,
  model families, and material-change thresholds remained fixed.
- Audit: the v1.0 source-definition failure remains preserved as an
  implementation/source-verification failure, not a statistical failure.

## J003 — Main positive pattern

- Post-implementation administration-layer observability reached 98.18%, but
  only 64.69% of 264,171 eligible order units reached a qualifying documented
  administration; class-specific conversion ranged from 50.42% to 82.87%.
- First-dose timing remained nontrivial (class medians 1.21–6.51 hours), with
  electrolyte replacement showing a 49.38-hour 95th percentile and 12.16%
  beyond 24 hours.
- Literal semantics were analytically consequential: the frozen semantic
  audit changed insulin not-given classification from 11.99% to 48.56%.
- Exposure-source substitution propagated selectively. The VTE anchor changed
  7.09% on the relative absolute log-effect scale and remained below the
  materiality rule; the PPI anchor changed 70.68%, and all four prespecified
  PPI variants met the frozen material-change rule.

## J004 — Implementation rewrite

- Decision: stop the event-level many-to-many implementation and replace it
  with projected/materialized source tables, whitelist-first filtering,
  frozen-unit order deduplication, eMAR preaggregation, and equality joins.
- Audit: the abandoned plan would have expanded 633,081 order units to an
  estimated 1,348,577 event-level rows, with maximum key multiplicity 297.
  Preaggregation retained the frozen unit and avoided 715,496 expanded rows.
- Interpretation: this is a reproducibility and query-design finding, not a
  statistical failure.

## J005 — Journal and submission decision

- Analytic decision: `GO_JAMIA_ANALYTIC`.
- Final package decision: `GO_JAMIA_AUTHOR_COMPLETION_REQUIRED`.
- Evidence: analytic checks 14/14 PASS; manuscript checks 9/9 PASS; final
  package checks 13/13 PASS; J01–J10 all PASS; 40 rendered DOCX pages visually
  reviewed; six accessibility audits with zero high, medium, or low findings;
  11/11 SVG/PDF structures and 11/11 Illustrator open tests passed.
- Upload boundary: authors must still supply authorship, affiliations, ORCID,
  corresponding-author information, funding, conflicts, CRediT roles,
  acknowledgements, institution-specific ethics or exemption determination,
  final approval, and the approved repository URL.
- Stop-loss: do not expand classes, windows, anchors, or semantic mappings to
  seek stronger effects. If JAMIA declines for single-center scope, retain the
  same provenance-aware story for Journal of Biomedical Informatics, then
  Pharmacoepidemiology and Drug Safety.

## J006 — Author metadata completion and upload boundary

- Source: the author-supplied `文章信息完善.docx` was fully extracted and
  rendered before use (SHA-256
  `7ac30e1bd61cb8ff93e8c5b67571e769af9f679faa8a04c2a58316f01b0d6d3e`).
- Applied without inference: five-author order, three affiliations, three
  equal-contribution designations, two co-corresponding authors and supplied
  e-mails, two funding awards, no competing interests, CRediT roles derived
  conservatively from the supplied author-order instruction, database
  acknowledgement, and transparent GPT/ChatGPT/Codex disclosure.
- Analytic boundary: no medication class, whitelist, time window, semantic
  mapping, analysis unit, anchor, covariate, model, threshold, estimate, or
  conclusion changed during author-information completion.
- Administrative hold: the source did not provide degrees for Jiajun Luo,
  Qinglong Chen, or Jing Liu; corresponding-author telephone number(s); a full
  Fanghui Lu postal address/postcode; final all-author approval and
  originality/exclusive-consideration confirmation; local confirmation of the
  source-level ethics wording; or the intended public repository URL.
- Upload decision: `HOLD_REQUIRED_CONTACT_APPROVAL_AND_REPOSITORY_FIELDS`.
  This is an administrative completion boundary, not an analytic or
  statistical failure.
- Repository audit: no GitHub push was attempted because the current Git
  remote belongs to a different project and the worktree contains unrelated
  changes. Publication requires an explicitly approved N1 repository target.

## J007 — Second-prereview diagnostic expansion

- Date: 31 July 2026.
- Decision: freeze a reviewer-motivated diagnostic addendum before any new
  result scan. The original ICU-order-window analyses remain primary.
- Added diagnostics: A2 hospital-overlap order-window decomposition; A1
  available-metadata-constrained administration and administration-only
  provenance; NDC/RxNorm-reference coding asymmetry; a structured published-
  operator landscape sample; complete paired bootstrap coverage; calendar-
  stratum reporting; and explicit Sepsis-3/OMOP feasibility gates.
- Boundary: the six medication classes, name dictionaries, event semantics,
  original windows, cohorts, outcomes, covariates, anchors, and material-change
  rules are unchanged. New operators are labelled sensitivities and cannot
  replace the original results based on direction, magnitude, or significance.
- Submission status: the eventual package remains a clean first submission;
  this prereview and its issue matrix are internal provenance only.

## J008 — Figure 1 artwork decision

- Date: 1 August 2026.
- Decision: use the author-approved ImageGen concept artwork directly as the
  main Figure 1 because it communicates the source-to-operator-to-drift story
  more clearly than the superseded programmatic redraw.
- Reproducibility: lock the source PNG by SHA-256; preserve it unchanged as the
  submission PNG; create TIFF/PDF delivery copies; archive the superseded
  vector assets; and include the source image, prompt, and artwork manifest in
  the patient-free reproducibility bundle.
- Disclosure: explicitly report OpenAI ImageGen use in the manuscript, title
  page, and cover letter, with author verification of every label, connection,
  and interpretation.
- Analytic boundary: this is a presentation decision only. No frozen class,
  whitelist, time window, event semantic, analysis unit, anchor, model,
  estimate, or conclusion changed.
