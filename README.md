# Medication exposure provenance operator in MIMIC-IV

This repository accompanies **Medication Exposure Depends on Source, Time,
and Identity: A Provenance-Operator Audit in MIMIC-IV**. It implements a joint
medication-exposure operator across source observability, database-executable
identity, time, native event semantics, and required dose/route metadata.

Headline reproducibility findings include:

- 42,808,593 complete eMAR rows and 73 literal event states audited;
- 64.69% same-POE versus 86.06% same-class/window order conversion among
  264,171 post-deployment order units;
- route present in 9,940/9,940 eligible A1 order units but 0/87,569 strict VTE
  eMAR events;
- 183/184 fixed A2 residual stays linked by native pharmacy identifiers to PPI
  prescriptions; 256 rows collapsed to 183 independent order units, with eMAR
  POE preceding administration by median 5.68 hours and the linked prescription
  POE following it by 97.18 hours (paired separation 106.10 hours);
- after main text, 55/56 linked supplements, and three article-specific
  repositories were reviewed, only 7/40 studies named a native source, 2/40
  supplied executable identity, and 0/40 reported native event semantics.

These are measurement and reproducibility diagnostics, not causal estimates
of medication efficacy or safety. eICU is an interface-semantic contrast, not
external validation.

## Data access

No raw data, patient identifiers, stay-level rows, or derived patient-level
cohorts are included. Credentialed users must obtain MIMIC-IV 3.1 and eICU-CRD
2.0 directly from PhysioNet and comply with their training, license, and
data-use agreements.

Set these environment variables before running:

```powershell
$env:MIMIC_IV_ROOT = 'path\to\mimic-iv-3.1'
$env:EICU_ZIP = 'path\to\eicu-crd-2.0.zip'
$env:PYTHON_EXE = 'python'
$env:RSCRIPT_EXE = 'Rscript'
```

Install the recorded Python and R dependencies in `environment/`, then run
`scripts/run_pipeline.ps1`. The script is staged: core QDP, observability,
presubmission diagnostics, operator upgrade, residual trace, literature-scope
audit, and figure generation. Network access is required for RxNav, PubMed,
Europe PMC, and article-specific repository retrieval. The committed aggregate
tables are the versioned reference outputs for the frozen 1 August 2026 audit.

## Repository structure

- `contracts/`: hashed analysis/addendum contracts and published-operator codebook
- `config/`: frozen drug, event-state, anchor, and interface whitelists
- `scripts/`: executable Python/R/PowerShell pipeline
- `outputs/`: patient-free aggregate reference results, manifests, and QA
- `figures/`: figure deliverables and panel-level source data; Figure 1 is an
  appearance-preserving SVG raster container, while Figures 2-4 and S4-S5 have
  live-text vector backups
- `reports/`: QDP and implementation-failure audit reports
- `environment/`: recorded sessions and dependency files

The first stopped event-level join is retained as an engineering failure audit.
The production implementation projects required columns, filters frozen drug
definitions first, deduplicates orders, preaggregates eMAR, and joins bounded
small tables.

Repository: https://github.com/jiajunluo430-creator/mimic-exposure-provenance-operator
