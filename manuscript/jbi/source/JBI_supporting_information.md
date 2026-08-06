# Supporting Information

## A Machine-Executable Provenance Operator for Medication-Exposure Phenotyping Across Electronic Health Record Representations

Jiajun Luo, Qinglong Chen, Jing Liu, Fanghui Lu, and Xiaolong Liang

# Contents

- Supplementary Methods 1–8
- Tables S1–S17
- Supplementary reproducibility notes

# Supplementary Methods

## S1. Contract-first development

The method upgrade was governed by a frozen master contract. Scientific definitions, six drug-class whitelists, event-state rules, time windows, analysis units, ablation variants, expected parity values, adapter boundaries, and stop rules were committed before the corresponding execution. The implementation was not permitted to change an operator because a conversion rate, agreement statistic, or association estimate was small, null, or inconvenient. The earlier long-running all-table join remains recorded as an engineering implementation failure; it was not relabeled as a statistical failure.

The optimized native pipeline projected required columns from compressed source files, filtered the frozen medication lists before joining, aggregated eMAR to the declared order/class status unit, deduplicated prescription and pharmacy records to prespecified order units, and joined only reduced tables. Each stage emitted a checkpoint, row count, duration, and query plan. This changed implementation cost but not the scientific contract.

## S2. Operator schema and traceability

The operator is defined as O=(S,I,T,E,M). The machine-readable envelope contains `schema_version`, `operator_version`, construct name, analysis unit, target event, adapter, output profile, and provenance metadata. The five scientific dimensions are mandatory. The JSON Schema rejects missing dimensions and unsupported enumerations before adapter compilation.

Seven MIMIC example operators are generated from frozen contracts rather than manually edited. Each records the binding contract path and SHA-256, medication-list path and SHA-256, generator path and SHA-256, source-model version, author/date metadata, and canonical specification hash. Execution adds adapter version, evaluation level, aggregate-only status, capability decisions, and output hashes. Syntactic validity, adapter support, measurability, executability, and reproducible traceability are emitted separately.

## S3. Four-state classification

The source-observability gate precedes record classification. A unit cannot be called unexposed if the required source was not deployed, the adapter cannot access it, or a construct-required field is structurally absent. When source observability passes, the adapter evaluates identity, time, event semantics, and metadata in order. A positive record that passes every predicate produces exposed. Observable eligibility without a qualifying positive record produces unexposed. Ambiguous identity, unmapped event state, or record-level metadata ambiguity produces unresolved. Missing source capability or missing construct-required metadata produces unmeasurable.

The distinction is scientific rather than cosmetic. For example, an order source may contain route while the corresponding administration source does not. If route is necessary to distinguish prophylactic from therapeutic anticoagulation, a route-absent administration record does not support either exposure or non-exposure to the prophylactic construct.

## S4. MIMIC native interface audit

The source audit covered the complete eMAR table, not a sample. It enumerated all 73 exact `event_txt` values and measured POE linkage. The full eMAR table contained 42,808,593 rows; 96.19% linked to a nonblank POE identifier. `Flushed` (3,350,325 rows), `Confirmed` (1,852,934 rows), and blank event text (446,102 rows) were preserved as separate excluded categories and did not enter the strict given/not-given denominator. eMAR-detail fields were audited for dose availability and not-given reasons. The interface inventory also reproduced the prespecified case in which item 225925 existed in `d_items` while the corresponding `inputevents` table contained zero rows for that item.

Strict administration required frozen positive event semantics and the declared identity/time rule. Broad same-class/window administration was retained only as a sensitivity operator. The primary order-to-administration conversion denominator was the frozen post-eMAR-deployment order universe.

The cross-layer workflow-clock trace was re-expressed at the prespecified 183-stay analysis unit. The current medians separate prescription-linked POE minus first administration (97.18 hours), eMAR-linked POE minus first administration (−5.68 hours), and paired POE-role separation (106.10 hours). An earlier audit table used 256 prescription rows and reported a single 102.63-hour summary; the row-level and stay-level summaries answer different questions and should not be numerically substituted for one another.

## S5. Matched native/FHIR evaluation

Public native MIMIC-IV 2.2 and MIMIC-IV-on-FHIR 2.1 demonstrations were integrity-gated before evaluation. Native pharmacy records and FHIR MedicationDispense were compared at `pharmacy_id × medication_class`. MedicationRequest was compared with native prescriptions and pharmacy fields. MedicationAdministration top-level status and `dosage.method` were evaluated separately because the latter carried the native administration event meaning. Native `emar_id` was not required when absent from FHIR; instead, a prespecified pharmacy/class/time/semantic composite was reported as composite concordance rather than native-ID parity. The resource-role/status baseline treated all 6,697 class-mapped MedicationAdministration records as positive; the event-semantic operator identified 5,740 strict positives, so role/status-only execution exceeded the strict count by 957 records (16.7% relative to 5,740).

The demonstration was intentionally bounded. The public 100-patient pair was chosen because both native and FHIR inputs are distributable and independently rerunnable without a private conversion pipeline. Exact equality on this matched sample establishes functional cross-schema execution, not full-cohort transport or clinical validation. Scaling the same adapter to the complete MIMIC-IV-on-FHIR release remains future work rather than an unstated claim of this version.

## S6. OMOP and eICU capability boundaries

The OMOP demonstration was evaluated at two levels: record-existence drug exposure, which is directly supported by `DRUG_EXPOSURE`, and strict documented administration, which requires source event-state semantics. A synthetic four-unit provenance extension was included to test all terminal states deterministically. Removal of the extension was a prespecified semantic-loss ablation.

eICU has medication, infusion, treatment, and intake/output interfaces but no native medication cross-source identity equivalent to MIMIC POE/pharmacy linkage. Therefore, exact identity reconciliation was declared unsupported before analysis. Reconciliation was limited to same stay, same frozen class, and frozen time window after class-specific feasibility gates. Before the full ZIP run, the identical streaming, classification, gate, and reconciliation code was required to recover 100/100 constructed prokinetic order–infusion pairs spread across 10 synthetic hospitals. This positive control tested whether qualifying matches could be recovered; it did not establish semantic equivalence of the real interfaces. `treatment` remained documentation-only and `intakeOutput` remained excluded. No eICU result was interpreted as external validation, adherence, quality, effectiveness, or safety.

## S7. Structured publication validator

The validator consumed 40 human-coded structured records and did not infer fields from prose. Evidence review included 40 main articles, 55 of 56 linked supplementary files, and three article-specific repositories. Five repositories linked by articles but containing only generic MIT-LCP materials were not credited as article-specific executable code. The audit was restricted to open-access studies; the direction of selection bias is unknown.

The primary coding was performed by one coder. The package includes blank second-coder instructions, an import validator, and an agreement-analysis script, but no second-coder result and no kappa are reported. This boundary is retained in the submission materials.

## S8. Downstream stress-test boundary

The A1 and A2 anchors were used to show propagation from operator choice to patient classification and model output. They do not estimate whether prophylactic anticoagulation or proton-pump inhibitors improve outcomes. The same frozen adjustment structure was refit under each prespecified exposure operator. Effect movement is reported on the log scale and by null-direction crossing. No P value selected an operator or result.

<!-- PAGEBREAK -->

# Supplementary Tables

## Table S1. Required operator fields

| Component | Required fields | Typical values |
|---|---|---|
| Envelope | schema version, operator version, construct, unit, adapter | `1.0.0`, `medprov 0.1.0`, order unit or ICU stay |
| Source (S) | source role, resource/table, deployment, observability | order, pharmacy/dispense, documented administration |
| Identity (I) | vocabulary/list, keys, revision rule, deduplication, match mode | exact POE; pharmacy/class/time composite; same class/window |
| Time (T) | origin, assignment field, boundaries, grace, censoring | ICU admission; hospital overlap; first 48 hours |
| Event (E) | positive, negative, excluded, unresolved, precedence | given; held/not given; flushed/confirmed/blank |
| Metadata (M) | route, dose, unit, frequency, required values, missing policy | subcutaneous route required; route absent → unmeasurable |
| Provenance | contract/list/generator paths and SHA-256 values | immutable trace from specification to aggregate output |

## Table S2. Terminal states

| State | Necessary condition | Interpretation boundary |
|---|---|---|
| Exposed | Observable source and ≥1 record passes I, T, E-positive, and M | Documented exposure under this operator |
| Unexposed | Observable, eligible unit with no qualifying positive record | No qualifying documented event; not proof of no biological exposure |
| Unresolved | Relevant record exists but cannot be classified deterministically | Retained uncertainty; not merged into either binary class |
| Unmeasurable | Source/adapter/deployment/required field unavailable | Construct cannot be evaluated in this representation |

## Table S3. Frozen medication classes and intended use in the method evaluation

| Frozen class | Primary role in evaluation | Prohibited reinterpretation |
|---|---|---|
| Stress-ulcer prophylaxis | Conversion and cross-representation class | Efficacy/safety study |
| VTE prophylaxis after GI bleeding | Conversion, route measurability, A1 stress test | Optimal prophylaxis strategy |
| Intra-abdominal antibiotics | Conversion and eICU interface feasibility | Comparative antibiotic effectiveness |
| Electrolyte replacement | Conversion and ambiguity gate | Expansion after failed gate |
| Prokinetics | Conversion and minimum-evidence gate | Rescue by relaxing whitelist |
| Insulin | Conversion and sliding-scale/event semantics | Glycemic outcome prediction |

## Table S4. MIMIC-IV six-class native parity

| Medication class | Order units | Strict same-POE | Same-class/window | Parity status |
|---|---:|---:|---:|---|
| Electrolyte replacement | 113,854 | 57,408 | 92,717 | PASS |
| Insulin | 56,081 | 38,758 | 49,598 | PASS |
| Intra-abdominal antibiotics | 49,119 | 40,705 | 46,479 | PASS |
| Prokinetic | 2,329 | 1,855 | 1,986 | PASS |
| Stress-ulcer prophylaxis | 24,655 | 18,730 | 21,501 | PASS |
| VTE prophylaxis | 18,133 | 13,434 | 15,074 | PASS |
| Total | 264,171 | 170,890 | 227,355 | PASS |

## Table S5. Prespecified A1/A2 operator ablation

| Anchor | Operator | Exposed | Unexposed | Unresolved | Unmeasurable |
|---|---|---:|---:|---:|---:|
| A1 | Table-only | 12,950 | 7,298 | 0 | 0 |
| A1 | Source + class + window | 12,362 | 7,886 | 0 | 0 |
| A1 | Collapsed event semantics | 12,722 | 7,526 | 0 | 0 |
| A1 | Full exact-identity | 5,538 | 14,710 | 0 | 0 |
| A1 | Route required | 0 | 0 | 0 | 20,248 |
| A2 | Table-only | 1,061 | 1,752 | 0 | 0 |
| A2 | Source + class + window | 870 | 1,943 | 0 | 0 |
| A2 | Collapsed event semantics | 871 | 1,942 | 0 | 0 |
| A2 | Full exact-identity | 518 | 2,295 | 0 | 0 |

## Table S6. Agreement and Jaccard similarity

| Anchor | Comparison | Agreement | Positive agreement | Negative agreement | Jaccard |
|---|---|---:|---:|---:|---:|
| A1 | Full strict vs table-only | 0.634 | 0.599 | 0.663 | 0.428 |
| A1 | Full strict vs source/class/window | 0.663 | 0.619 | 0.698 | 0.448 |
| A1 | Full strict vs collapsed semantics | 0.645 | 0.607 | 0.677 | 0.435 |
| A2 | Full strict vs table-only | 0.807 | 0.656 | 0.866 | 0.488 |
| A2 | Full strict vs source/class/window | 0.875 | 0.746 | 0.917 | 0.595 |
| A2 | Full strict vs collapsed semantics | 0.875 | 0.746 | 0.917 | 0.595 |
| A2 | Original order vs hospital-overlap order | 0.951 | 0.903 | 0.967 | 0.823 |

## Table S7. Construct-required route availability in the A1 cohort

| Source layer | Records | Route available | Subcutaneous-compatible | Interpretation |
|---|---:|---:|---:|---|
| Eligible order unit within A1 cohort | 9,940 | 9,940 (100%) | 9,940 (100%) | Prophylactic route measurable |
| Strict VTE eMAR administration | 87,569 | 0 (0%) | 0 (0%) | Route-required construct unmeasurable |

## Table S8. Matched native/FHIR functional transport

| Dimension | Native count | FHIR count | Paired/exact result | Classification |
|---|---:|---:|---|---|
| Dispense `pharmacy_id × class` | 3,870 | 3,870 | 3,870/3,870 exact | Exact transport |
| Frozen-class request units | 3,903 | 2,726 | Not forced to parity | Partial transport |
| Administration top-level role/status | — | 6,697 positive | 957 above strict `dosage.method` count (16.7% relative) | Role/status-only overclassification |
| Administration strict positives | 5,696 | 5,740 by `dosage.method` | Similar semantic count | Semantic relocation |
| Administration composite identity | 6,253 native-linkable | 6,697 mapped FHIR | 5,220 paired (83.5%) | Composite concordance |
| Request clock | 2,249 deterministic pairs | 2,249 | `authoredOn`=`pharmacy.entertime` in 2,249/2,249 | Exact workflow-clock transport |
| First administration time | 1,353 linked units | — | 1,347/1,353 exact (99.6%) | Near-exact transport |
| Native `emar_id` | Available | Omitted | Not evaluable | Native identity unavailable |

## Table S9. OMOP capability and semantic-loss evaluation

| Evaluation | Eligible units | Exposed | Unexposed | Unresolved | Unmeasurable |
|---|---:|---:|---:|---:|---:|
| Official demo, record existence | 37 | 37 | 0 | 0 | 0 |
| Official demo, strict administration | 37 | 0 | 0 | 0 | 37 |
| Synthetic fixture, ATLAS-style existence | 4 | 4 | 0 | 0 | 0 |
| Synthetic fixture, medprov extension | 4 | 1 | 1 | 1 | 1 |
| Synthetic fixture, extension removed | 4 | 0 | 0 | 0 | 4 |

## Table S10. eICU interface-semantic feasibility

| Class | Eligible medication order units | Same-stay/class/window administration-like units | Conversion | Gate status |
|---|---:|---:|---:|---|
| Stress-ulcer prophylaxis | 167,806 | 3,696 | 2.202543% | PASS |
| VTE prophylaxis | 134,102 | 7,491 | 5.586046% | PASS |
| Intra-abdominal antibiotics | 88,816 | 224 | 0.252207% | PASS |
| Electrolyte replacement | — | — | Not reconciled | FAIL: identity ambiguity |
| Insulin | — | — | Not reconciled | FAIL: identity ambiguity |
| Prokinetic | — | — | Not reconciled | FAIL: insufficient events/hospitals |

**Adapter positive control:** the same code path recovered 100/100 constructed prokinetic order–infusion pairs across 10 synthetic hospitals before full execution. This is a reconciliation-mechanics control, not an external clinical validation.

**Boundary:** These values quantify interface reconciliation under a frozen same-stay/class/window rule. They are not administration adherence, hospital quality, or external validation.

## Table S11. Structured reporting validator

| Required reporting element | Studies reporting element | Percentage |
|---|---:|---:|
| Named native medication source | 7/40 | 17.5% |
| Database-executable identity | 2/40 | 5.0% |
| Time origin and exposure window | 35/40 | 87.5% |
| Native event-state semantics | 0/40 | 0% |
| Dose or route rule | 30/40 | 75.0% |
| Complete executable five-dimensional operator | 0/40 | 0% |

## Table S12. Software and artifact validation

| Validation component | Result |
|---|---|
| Software version | `medprov` 0.1.0 |
| Tests | 61 passed, 0 failed |
| Branch-aware coverage | 86.03% |
| Release checks | 10/10 passed |
| Wheel build/install | Passed in clean virtual environment |
| Source distribution | Built successfully |
| Four-state deterministic demo | Reproduced after clean install |
| Cross-model package checks | 39/39 passed |
| Public output privacy | Aggregate only; no native identifiers |

## Table S13. Wheel and source-distribution checksums

| Artifact | SHA-256 |
|---|---|
| `medprov-0.1.0-py3-none-any.whl` | `de654ab1a304c92852344b1770a7ba76f04518157b228a090be7d8d6c473599d` |
| `medprov-0.1.0.tar.gz` | `aa720c9955f1a772f4366808c0726156d73eb08d201834f356dde4edfdbd6987` |

## Table S14. Full downstream stress-test estimates

| Anchor/operator | Source | Exposed | Effect (95% CI) | Δlog administration−order | Crossed null direction |
|---|---|---:|---|---:|---|
| A1 original strict | Order | 7,047 | OR 1.868 (1.715–2.036) | Reference | — |
| A1 original strict | Administration | 5,538 | OR 1.953 (1.788–2.133) | 0.044 | No |
| A1 original broad | Administration | 12,362 | OR 0.907 (0.831–0.990) | −0.723 | Yes |
| A1 dose-constrained broad | Administration | 12,183 | OR 0.909 | −0.720 | Yes |
| A2 original strict | Order | 655 | HR 1.904 (1.683–2.154) | Reference | — |
| A2 original strict | Administration | 518 | HR 1.926 (1.689–2.196) | 0.012 | No |
| A2 original broad | Administration | 870 | HR 1.208 (1.070–1.363) | −0.455 | No |
| A2 hospital-overlap strict | Order | 776 | HR 1.643 (1.457–1.854) | Reference | — |
| A2 hospital-overlap strict | Administration | 521 | HR 1.927 (1.691–2.196) | 0.159 | No |
| A2 hospital-overlap broad | Administration | 870 | HR 1.208 (1.070–1.363) | −0.308 | No |

## Table S15. Bounded comparison with adjacent standards and methods

| Family | Primary contribution | Provenance-operator complement |
|---|---|---|
| FHIR medication resources | Separates request, dispense, administration and statement roles | Declares identity, clock and event-semantic mappings across resources |
| OMOP CDM / ATLAS | Standard drug records and executable common-model cohorts | Retains source role and fail-closed event/metadata capability |
| CQL | Executable clinical logic | Supplies the medication-specific observable-evidence contract |
| PheKB / computable phenotypes | Dissemination and portability workflows | Adds machine-testable source, identity, time, semantics and metadata fields |
| RECORD-PE / RECORD / STROBE | Reporting transparency | Provides executable evidence rather than narrative reporting alone |
| STaRT-RWE / HARPER | Structured design and protocol decisions | Compiles exposure decisions against representation capabilities |

No numeric superiority score was calculated because these families solve complementary problems.

## Table S16. Claim boundary matrix

| Result | Supported claim | Unsupported claim |
|---|---|---|
| MIMIC exact parity | Reference implementation reproduces frozen aggregates | Medication events represent biological truth |
| Operator ablation | Dimensions change classification and measurability | Broad or strict definition is universally superior |
| FHIR demo | Functional cross-schema transport and semantic relocation | Full-dataset or cross-institution validation |
| OMOP demo | Capability and semantic-loss demonstration | OMOP is unsuitable for drug research |
| eICU | Interface observability and gate behavior | External validation, adherence or quality ranking |
| Literature validator | Published evidence did not specify complete operators | The original studies were analytically wrong |
| A1/A2 stress tests | Exposure definition can propagate to estimates | Causal benefit, harm or treatment recommendation |

## Table S17. Prespecified evaluation layers and achieved gates

| Evaluation layer | Data/fixture | Target claim | Prespecified gate | Result |
|---|---|---|---|---|
| Native reference | MIMIC-IV 3.1 | Implementation fidelity | 19 zero-tolerance count/model checks | PASS, 19/19 |
| Operator ablation | MIMIC A1/A2 and six classes | Dimension-specific reclassification and measurability | Frozen variants retained regardless of result | PASS; identity, time and route localized |
| FHIR functional transport | Matched native 2.2/FHIR 2.1 demos | Exact, transformed, relocated or unavailable semantics | Frozen integrity, identity, time and state comparisons | PASS_FUNCTIONAL_CROSS_SCHEMA |
| OMOP capability | Official demo plus synthetic extension | Record-existence capability and semantic loss | Real-demo and deterministic four-state execution | PASS semantic ablation; capability smoke test |
| eICU interface comparison | Full eICU 2.0 ZIP plus positive control | Source observability under missing native identity | Positive control plus five per-class gates | 100/100 control; 3/6 classes executable; not external validation |
| Reporting validator | 40 structured publication records | Published operator reproducibility | Deterministic fields; no prose inference | PASS; 0/40 complete operators |
| Software release | Wheel, sdist, tests, clean environment | Installability and traceability | Release, negative-path, privacy, and adapter tests | Reported in Table S12 |
| Cross-model package | Aggregate artifacts and manifests | Artifact integrity, privacy, frozen invariants | 39 validation checks | PASS, 39/39 |

# Reproducibility notes

The public repository contains the schema, example operators, source code, command-line guide, adapter-authoring guide, contracts, class lists, synthetic fixtures, tests, aggregate reports, figure data, and figure-generation script. Licensed source data must be acquired directly from PhysioNet. The public executor rejects native identifiers and writes aggregate outputs only.

Core commands after installation are:

`medprov validate-spec examples/mimic_strict_same_poe.yaml`

`medprov demo --out demo_output`

Credentialed local MIMIC and full eICU runs are outside the public smoke test; distributed aggregate expected values and manifests let authorized users verify local execution without receiving restricted rows.
