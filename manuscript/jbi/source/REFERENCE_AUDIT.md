# Reference and citation audit

## Decision

**PASS_WITH_PRIMARY_OR_OFFICIAL_SOURCE_VERIFICATION**

The JBI manuscript contains 42 references. Numeric citations first appear in ascending order [1] through [42]. Every numbered reference is cited in the manuscript, and no in-text number lacks a reference-list entry. DOI and title checks use publisher pages, PubMed/PMC, journal pages, or official standards/data repositories. Access dates are included for living web standards.

## Corrections made during this audit

- Replaced abbreviated or paraphrased titles for references 5–7 with publisher-indexed titles and full author strings where available.
- Corrected reference 36 to the published Cureus title, “Missed Venous Thromboembolism Prophylaxis in ICU Patients: A Retrospective Cohort Study Using the Medical Information Mart for Intensive Care IV (MIMIC-IV).”
- Corrected reference 37 to the published Frontiers title, “Prophylactic proton pump inhibitor use and all-cause mortality in adult sepsis patients: a retrospective analysis based on the MIMIC-IV database.”
- Corrected reference 38 to the published Learning Health Systems title on harmonization and provenance.
- Corrected reference 39 to “Transparent reporting of data quality in distributed data networks,” which is the article attached to DOI 10.13063/2327-9214.1052.
- Resolved HARPER as a 2022 Value in Health article, volume 25, issue 10, pages 1663–1672, DOI 10.1016/j.jval.2022.09.001.

## Automated checks required in the build

The manuscript build must stop if:

- reference numbering is noncontiguous;
- first appearance is not ascending;
- a listed reference is uncited or an in-text citation is missing from the list;
- the abstract contains a numbered citation;
- the reference count differs from 42.

The machine-readable registry in `reference_registry.csv` records the DOI/official URL and verification source for every entry.
