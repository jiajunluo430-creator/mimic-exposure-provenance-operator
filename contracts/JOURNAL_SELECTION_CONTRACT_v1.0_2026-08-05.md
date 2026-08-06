# Transfer-journal selection contract

Version: 1.0  
Frozen: 2026-08-05, before the final transfer manuscript was drafted  
Scope: selection among Journal of Biomedical Informatics (JBI), International Journal of Medical Informatics (IJMI), JAMIA Open, BMC Medical Informatics and Decision Making, and Pharmacoepidemiology and Drug Safety (PDS)

## Inputs

- The completed `medprov` 0.1.0 source, wheel, source distribution, tests, schemas, command-line interface, documentation, and privacy-safe reports.
- Exact native MIMIC-IV parity, prespecified operator ablations, the structured 40-study reporting validator, bounded state-of-the-art comparison, matched-demo FHIR transport, OMOP capability/semantic-loss evaluation, and eICU interface-semantic comparison.
- Official journal scope and author instructions accessed on 2026-08-05.

## Pre-frozen decision hierarchy

1. Select JBI only if all or nearly all of the following are complete: installable software; versioned schema and unified CLI; exact native parity; prespecified ablation; executable comparator; at least one rigorous execution assessment beyond native MIMIC-IV 3.1; complete code/tests/documentation; and a manuscript centered on a generalizable new method.
2. Otherwise select IJMI if the software, validator, parity, and application evaluation are complete but cross-representation or state-of-the-art evidence is insufficient for JBI.
3. Select JAMIA Open if the public tool is useful but methodological novelty or transport evidence is weaker.
4. Select BMC Medical Informatics and Decision Making if validity, reproducibility, and open software are the strongest contribution but the higher informatics-method gates are not met.
5. Select PDS if the executable-method upgrade fails and the defensible contribution remains exposure measurement, patient reclassification, and estimate propagation.

## Hard interpretation boundaries

- The target is selected from observed evidence, not impact factor or an estimated acceptance probability.
- FHIR results are a functional cross-schema evaluation on matched public demonstrations, not full-release transport validation.
- OMOP results are capability and semantic-loss evaluations, not clinical validation.
- eICU results are an interface-semantic comparison, not external validation or exact replication.
- The A1/A2 analyses are downstream measurement stress tests, not drug-effect studies.
- The 40-study sample is a structured single-coder reporting audit, not a systematic review and not independently recoded.
- No Git push, public release, preprint, DOI registration, or journal submission is authorized by this contract.

## Official sources frozen for selection

- JBI Guide for Authors: https://www.sciencedirect.com/journal/journal-of-biomedical-informatics/publish/guide-for-authors
- JBI Aims and Scope: https://www.sciencedirect.com/journal/journal-of-biomedical-informatics/about/aims-and-scope
- IJMI Guide for Authors: https://www.sciencedirect.com/journal/international-journal-of-medical-informatics/publish/guide-for-authors
- JAMIA Open General Instructions: https://academic.oup.com/jamiaopen/pages/General_Instructions
- BMC Medical Informatics and Decision Making Submission Guidelines: https://bmcmedinformdecismak.biomedcentral.com/submission-guidelines
- PDS Author Guidelines: https://onlinelibrary.wiley.com/page/journal/10991557/homepage/forauthors.html

## Stop rule

Once the evidence is mapped to the hierarchy, one selected target and one backup are frozen. The manuscript may be reformatted for the selected target, but the scientific contract, whitelists, windows, classification states, parity thresholds, and transport claim boundaries may not be changed to improve journal fit.
