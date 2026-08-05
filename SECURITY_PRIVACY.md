# Security and privacy

## Restricted clinical data

This repository contains no MIMIC-IV/eICU patient-level data. Users must obtain
source data independently and comply with PhysioNet credentialing, training,
license, and data-use requirements. Do not open issues or pull requests that
contain clinical rows, identifiers, screenshots of restricted records, access
tokens, or local source paths.

## Aggregate-only execution

The public executor returns aggregate counts and metrics. A recursive guard
rejects result keys corresponding to subject, admission, stay, POE, pharmacy,
or eMAR identifiers. This guard is defense in depth; adapter authors must also
avoid constructing restricted payloads.

## Secrets

Credentials belong in local environment variables or credential stores and
must not be committed. Release validation scans for token-like strings,
absolute paths, and patient-key column names.

## Reporting a vulnerability

Report software vulnerabilities privately to the repository maintainers. For
restricted-data exposure, stop distribution immediately, preserve an audit
record, and follow the applicable data-use incident procedure. Do not attach
the exposed material to a public report.

## Scope of the MIT license

The MIT license applies to the newly developed medprov package, schemas,
examples, tests, and accompanying documentation. It does not relicense MIMIC-
IV, eICU, third-party content, or legacy components with separate terms.
