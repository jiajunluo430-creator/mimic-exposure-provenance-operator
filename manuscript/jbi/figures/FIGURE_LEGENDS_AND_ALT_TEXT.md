# Figure legends and alt text

## Figure 1. Machine-executable medication-exposure provenance architecture
Panel A shows four evaluated EHR representations passing through version-gated adapters into a canonical medication-event representation while retaining clinical role, native identity, time, event state, and required metadata. Panel B shows the five-dimensional operator, validation states, four deterministic terminal classifications, aggregate comparison, and downstream stress testing.

Alt text: Two-panel architecture diagram. Native EHR, FHIR, OMOP, and eICU sources feed adapters and a canonical event representation. Five operator dimensions labeled source, identity, time, event semantics, and metadata pass through validation gates and produce exposed, unexposed, unresolved, or unmeasurable states.

## Figure 2. Native parity and prespecified operator ablation
Panel A compares frozen expected and medprov-generated class counts on identical log scales; all points fall on the identity line and 19 of 19 parity checks passed. Panel B shows exposed proportions for table-only, source/class/window, collapsed-semantics, and full exact-identity operators in A1 and A2, plus the fail-closed route-required A1 result.

Alt text: A parity scatterplot places order, strict-administration, and same-class counts exactly on the identity line. Grouped horizontal bars show decreasing exposed proportions as identity and semantics constraints are added; a separate gray callout identifies all route-required A1 units as unmeasurable.

## Figure 3. Bounded cross-representation and cross-database evaluation
Panel A summarizes supported, partial or relocated, and unavailable provenance capabilities in native MIMIC-IV, matched native/FHIR demonstrations, an OMOP demonstration, and eICU. Panel B reports quantitative matched-demo FHIR identity and time concordance. Panel C shows fail-closed state distributions in OMOP and eICU evaluations.

Alt text: A capability matrix shows that no representation carries every provenance dimension identically. FHIR bars show exact dispense identity and nearly exact first-administration time. Stacked bars show strict OMOP administration becoming unmeasurable when literal state is absent and eICU producing a majority unmeasurable classification.

## Figure 4. Structured reporting validator results
Panel A reports how often 40 coded MIMIC medication studies supplied each provenance dimension. Panel B shows the narrowing from 40 encoded studies to 7 with a named native source, 2 with executable identity, and none with native event semantics or a complete executable operator.

Alt text: Horizontal bars show 7 of 40 studies naming a native source, 2 specifying executable identity, 35 specifying time, none reporting native event semantics, and 30 reporting dose or route requirements. A funnel ends at zero complete operators.

## Figure 5. Downstream reclassification and effect-estimate stress tests
Panel A compares full exact-identity with same-class/window administration and reports positive Jaccard agreement, while separately identifying structural route non-measurability. Panel B connects paired order- and administration-defined association estimates under exact-identity, same-class/window, and alternate time-window operators.

Alt text: Stacked bars show class-only exposure added beyond exact identity in both anchors. A connected forest plot shows little drift for some exact-identity pairs but large movement for broad same-class pairs; the plot is explicitly labeled as a measurement stress test rather than a causal drug-effect analysis.
