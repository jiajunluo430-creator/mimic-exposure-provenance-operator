# Independent recoding instructions

Status before author action: `AUTHOR_ACTION_REQUIRED_SECOND_CODER`.

The existing 20% worksheet is blank. It must be completed by a genuinely
independent human who has not seen the primary codes or aggregate reporting
counts. Codex or another output from the same AI workflow cannot serve as the
independent coder.

## Blinded workflow

1. A study coordinator selects the already frozen sample and supplies article
   main text, linked supplements, article-specific repositories, the blank
   worksheet, and the published codebook—but not primary coding columns.
2. The independent coder assigns exactly one of `reported`, `missing`,
   `ambiguous`, or `not_applicable` to each of the five dimensions and records a
   short evidence location.
3. The coder records a unique human coder ID and returns the completed CSV.
4. Run `scripts/49_import_second_coder.py` to validate the file.
5. Only after successful import, run `scripts/50_agreement_analysis.py` against
   the primary JSONL records.

Missing and ambiguous are separate nominal categories; they are not collapsed
before agreement calculation. Report percent agreement and unweighted Cohen
kappa per dimension. If prevalence makes kappa unstable or undefined, report
that fact alongside percent agreement without replacing the statistic after
seeing the result.

No adjudication changes the frozen primary 40-study result. Adjudicated codes,
if later created, are a separate labeled dataset.
