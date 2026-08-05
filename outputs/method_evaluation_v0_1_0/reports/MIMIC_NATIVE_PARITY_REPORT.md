# MIMIC native parity report

Reference implementation: MIMIC-IV native 3.1; medprov 0.1.0.
All outputs are aggregate-only.

## Decision: PASS

19/19 prespecified parity gates passed; integer tolerance was zero and the common stored-model beta tolerance was 1e-10.

## Core counts

- Post-deployment order units: 264,171.
- Strict same-POE converted: 170,890 (64.69%).
- Same-class/window converted: 227,355 (86.06%).
- A1 order-exposed: 7,047/20,248; strict administration-exposed: 5,538/20,248.
- A2 original order: 655/2,813; hospital-overlap order: 776/2,813; original strict administration: 518/2,813.

## Six-class parity

| Class | Orders | Strict | Broad | Status |
|---|---:|---:|---:|---|
| electrolyte_replacement | 113,854 | 57,408 | 92,717 | PASS |
| insulin | 56,081 | 38,758 | 49,598 | PASS |
| intra_abdominal_antibiotics | 49,119 | 40,705 | 46,479 | PASS |
| prokinetic | 2,329 | 1,855 | 1,986 | PASS |
| stress_ulcer_prophylaxis | 24,655 | 18,730 | 21,501 | PASS |
| vte_prophylaxis | 18,133 | 13,434 | 15,074 | PASS |

## P2 retained trace

The previously completed P2 trace also passed: 183/183 primary units linked to raw POE; median prescription-POE minus administration was +97.18 h, eMAR-POE minus administration was -5.68 h, and paired POE-role separation was 106.10 h.

No original source scan or outcome model was rerun. The adapter executed against the already-audited read-only materialized references. The earlier multi-table long-running implementation remains an engineering failure audit, not a statistical failure.
