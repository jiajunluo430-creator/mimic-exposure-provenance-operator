# JAMIA independent-recoding packet addendum v1.0

Frozen before sample generation on 2026-08-01.

- Sampling frame: the 40 studies in `published_operator_blinded_recode_worksheet.csv`.
- Sampling unit: one study.
- Sample size: 8 studies (20%), sampled without replacement.
- Pseudorandom seed: `20260801` using Python `random.Random`.
- Output ordering: selected studies sorted by the original `sample_order`.
- Blinding: bibliographic and retrieval-status fields are retained; all coder,
  review-date, operator-code, evidence-location, and notes fields remain blank.
- Interpretation: the packet enables independent human recoding. It is not a
  completed second review, and no inter-rater coefficient may be reported until
  an independent human coder completes and returns it.
- The original 40-study coding, codebook, contract, estimates, drug classes,
  windows, and statistical definitions are unchanged.
