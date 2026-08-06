# Figure legends and alt text

## Figure 1. Machine-executable medication-exposure provenance architecture
Panel A uses four source lanes to show native EHR, FHIR, OMOP, and eICU representations passing through source-specific adapters into a canonical medication-event record while preserving clinical role and retaining native identity when available without inferring it when absent. Panel B shows the five operator dimensions, validation chain, explicit four-state output, and the two prespecified evaluation paths.

## Figure 2. Native parity and prespecified operator ablation
Panel A is a log-log parity plot in which all frozen and generated six-class counts fall on the identity line; 19 of 19 checks pass. Panel B is a connected dot plot showing exposed proportions after successive operator ablations in A1 and A2, with route-required A1 administration explicitly classified as unmeasurable.

## Figure 3. Bounded cross-representation and cross-database evaluation
Panel A is a shape-coded capability matrix for native MIMIC-IV, matched FHIR demonstrations, an OMOP demonstration, and eICU. Panel B is a lollipop plot of matched-demo FHIR identity and time concordance. Panel C shows fail-closed state distributions for OMOP and eICU evaluations.

## Figure 4. Structured reporting validator
Panel A is a lollipop plot showing how often 40 coded MIMIC medication studies reported each provenance dimension. Panel B shows the drop from 40 encoded studies to 7 naming a native source, 2 specifying an executable identity rule, and none specifying event semantics or a complete operator; a small histogram shows reported dimensions per study.

## Figure 5. Reclassification and effect-estimate stress tests
Panel A shows exact-identity versus same-class/window reclassification in A1 and A2 and separately reports structural route non-measurability. Panel B is a paired forest plot comparing order-defined and administration-defined estimates under exact identity, same-class/window, and alternate time-window operators. These are measurement stress tests, not causal drug-effect estimates.
