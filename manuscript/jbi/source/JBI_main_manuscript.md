# A Machine-Executable Provenance Operator for Medication-Exposure Phenotyping Across Electronic Health Record Representations

**Article type:** Research Paper  
**Short title:** Executable Medication-Exposure Provenance

Jiajun Luo, PhD¹˒²,#; Qinglong Chen, MSc³,#; Jing Liu, MSc³,#; Fanghui Lu, PhD³,†; Xiaolong Liang, MD, PhD¹,†

¹ Department of Gastrointestinal Surgery, The First Affiliated Hospital of Chongqing Medical University, Chongqing 400016, China  
² Molecular Oncology Laboratory, Department of Orthopedic Surgery and Rehabilitation Medicine, University of Chicago Medical Center, Chicago, Illinois, USA  
³ Department of Cancer Center, The Second Affiliated Hospital of Chongqing Medical University, Chongqing, China

# Corresponding authors

Xiaolong Liang, MD, PhD, Department of Gastrointestinal Surgery, The First Affiliated Hospital of Chongqing Medical University, Chongqing 400016, China. Email: 204951@hospital.cqmu.edu.cn  
Fanghui Lu, PhD, Department of Cancer Center, The Second Affiliated Hospital of Chongqing Medical University, Chongqing, China. Email: lufh@cqmu.edu.cn

<!-- PAGEBREAK -->

# Abstract

## Objective

To make medication-exposure phenotypes explicit, executable, and transport-auditable across electronic health record (EHR) representations.

## Methods

We specified exposure as a deterministic five-dimensional operator, O=(S,I,T,E,M), comprising source layer, medication identity, time origin/window, native event semantics, and required dose/route metadata. A Python reference implementation (`medprov`) compiles versioned YAML/JSON specifications through representation-specific adapters and returns four states: exposed, unexposed, unresolved, or unmeasurable. We evaluated exact parity in MIMIC-IV 3.1, prespecified operator ablations, functional transport in matched native/FHIR demonstrations, semantic-loss capability in an OMOP demonstration, interface observability in eICU, and a structured validator applied to 40 published MIMIC medication studies. Two published-association anchors were retained only as downstream measurement stress tests.

## Results

All 19 native parity gates passed for 264,171 medication-order units. Exact same-order identity linked 170,890 (64.69%) to strict administrations; same-class/window matching linked 227,355 (86.06%). Requiring an administration route rendered all 20,248 prophylactic-anticoagulation anchor units unmeasurable because route was available for 9,940/9,940 eligible order units but 0/87,569 strict eMAR events. In matched demonstrations, native and FHIR dispense identity agreed for 3,870/3,870 class-mapped units, whereas administration semantics moved from native event text to FHIR dosage method. The OMOP demonstration supported drug-record existence but not strict administration when event state was absent. Among 40 publications, 7 named a native source, 2 specified executable identity, and none reported a complete operator. Exposure reclassification propagated to association estimates, including an A1 odds ratio shift from 1.868 under orders to 0.907 under same-class/window administration.

## Conclusion

Medication exposure is an executable provenance decision, not a table label. The operator localizes semantic loss, distinguishes absence from non-measurability, and supports bounded transport across EHR representations before downstream analysis.

**Keywords:** electronic health records; medication exposure; computable phenotyping; data provenance; FHIR; OMOP; reproducibility

# 1. Introduction

Medication exposure is often encoded in observational EHR research as a binary variable derived from a named table. That simplification hides a data-generation process: a clinician may express treatment intent, a pharmacy may verify or dispense an item, an administration interface may document delivery or non-delivery, and each layer may use a different identity and clock. Operational EHR data therefore reflect clinical workflow as well as patient state [1], and their provenance can change the meaning of an apparently identical variable [2]. Established data-quality frameworks describe completeness, correctness, concordance, plausibility, and fitness for use [3,4], but they do not by themselves compile a medication construct into a deterministic cross-layer classification rule.

This gap matters because drug-exposure measurement is defined by more than drug name. Pharmacoepidemiologic guidance emphasizes exposure source, timing, dose, persistence, and the relation between recorded events and the estimand [5,6]. Misclassification can attenuate, amplify, or redirect association estimates [7]. In inpatient EHRs, the problem is sharpened by native event states such as given, held, not given, confirmed, flushed, or blank; by order revisions; by workflow-specific timestamps; and by source-dependent availability of dose and route. Calling all records in an administration table “administered,” or all orders “exposed,” is therefore an implicit algorithm with unreported decisions.

We developed a machine-executable medication-exposure provenance operator that makes those decisions inspectable. The operator treats exposure as the output of five required dimensions—source, identity, time, event semantics, and metadata—and returns exposed, unexposed, unresolved, or unmeasurable. The distinction between unexposed and unmeasurable is central: if an EHR layer does not contain a route required by a clinical construct, absence of a qualifying row cannot be interpreted as absence of exposure.

## 1.1. Statement of significance

The methodological contribution is a fail-closed, versioned measurement layer rather than another medication-specific outcome model. It provides (1) a formal specification, (2) an executable reference implementation, (3) adapters that expose which dimensions survive or move across native EHR, FHIR, OMOP, and eICU representations, (4) exact-parity and semantic-loss tests, and (5) a structured reporting validator. The intended applicability is any medication phenotype for which clinical workflow layer, identity, time, event meaning, or dose/route requirements can alter classification.

# 2. Related work

Computable phenotyping has progressed from institution-specific rules toward reusable representations and execution environments [8]. Desiderata for computable phenotype representations include human readability, machine interpretability, modularity, and explicit data dependencies [9]. PheKB supplies a catalog and collaborative workflow for phenotype algorithms [10], and multicenter execution studies show both the feasibility and the remaining local-mapping burden of portable phenotypes [11]. Common-data-model approaches can improve transfer by standardizing inputs, although phenotype equivalence still depends on how source concepts and workflow are mapped [12].

FHIR separates MedicationRequest, MedicationDispense, MedicationAdministration, and MedicationStatement according to clinical role [13]. MIMIC-IV-on-FHIR demonstrates how a well-characterized native EHR can be represented in those resources [14]. This separation is an important prerequisite, but resource type alone does not guarantee that native identity, timestamp meaning, or administration event semantics are preserved.

The Observational Health Data Sciences and Informatics program supports distributed observational research through a common data model and shared analytics [15]. The OMOP lineage has enabled standardized active-surveillance and multisource analyses [16,17], while the current common data model defines `DRUG_EXPOSURE` as the central medication record [18]. ATLAS cohort definitions make reusable record-existence and temporal logic executable [19]. These capabilities are complementary to provenance specification: a standardized drug record can still combine order, dispensing, or administration origins unless source role and event meaning are retained.

Clinical Quality Language provides a computable formalism for clinical logic [20], and JSON Schema provides machine-validation of structured contracts [21]. Neither prescribes which native medication events constitute exposure. Reporting frameworks address adjacent parts of the problem: RECORD-PE promotes transparent pharmacoepidemiology using routinely collected data [22], STaRT-RWE specifies reproducible real-world-evidence design decisions [23], HARPER structures treatment-effect protocols [24], RECORD extends reporting for routinely collected health data [25], and STROBE guides observational-study reporting [26]. The unresolved increment is a representation-aware medication operator that can be validated before cohort analysis and can fail closed when its construct is not measurable.

# 3. Methods

## 3.1. Design and frozen boundaries

We performed a software-method development and bounded evaluation study. The scientific contract, six medication-class whitelists, event semantics, time windows, comparison operators, parity tolerances, transport gates, and stop rules were frozen before the corresponding aggregate queries. Definitions were retained regardless of the observed direction or magnitude. MIMIC-IV and eICU data were read-only. No raw rows, patient identifiers, stay identifiers, order identifiers, pharmacy identifiers, or eMAR identifiers are distributed.

The six frozen classes were stress-ulcer prophylaxis, venous thromboembolism (VTE) prophylaxis after gastrointestinal bleeding, intra-abdominal antibiotics, electrolyte replacement, prokinetics, and insulin. The primary reference unit was a deduplicated medication order after eMAR deployment; anchor analyses used their prespecified ICU-stay or patient units. eICU was evaluated only for interface semantics and source observability, not as external validation.

## 3.2. Formal operator

For analysis unit u with eligible source records Rᵤ, we defined

O=(S,I,T,E,M), and Cᵤ=O(Rᵤ),

where S is source layer and observability; I is medication identity, native keys, revision handling, and deduplication; T is time origin, assignment field, boundaries, grace periods, and censoring; E is a literal event-state map with precedence rules; and M is required dose, unit, route, frequency, or status metadata. Envelope fields record schema and operator versions, construct, analysis unit, target event, adapter, output profile, and provenance hashes but do not constitute a sixth scientific dimension.

Adapters map native records to a canonical intermediate event representation containing local subject, encounter and analysis-unit keys; medication class and ingredient; clinical source role; native event and order identity; event time; event state; dose; unit; route; frequency; and provenance flags. Public execution rejects payloads containing native MIMIC/eICU identifiers and uses synthetic identifiers only.

Classification proceeds through ordered gates. First, the source-observability gate asks whether the required layer was deployed and available for the unit. Second, the identity predicate applies the frozen code/name list, match mode, revision rule, and deduplication unit. Third, the time predicate applies the specified origin and interval. Fourth, literal source states are mapped to positive, negative, excluded, or unresolved; in the MIMIC reference, `Flushed`, `Confirmed`, and blank eMAR values remain excluded categories and do not enter the given/not-given denominator. Fifth, the metadata predicate evaluates construct-required fields and value constraints.

The terminal states are: exposed, when at least one deduplicated record satisfies all predicates; unexposed, when the required source is observable and no qualifying positive record exists; unresolved, when records exist but identity, state, or record-level metadata cannot be deterministically classified; and unmeasurable, when the source, adapter, deployment interval, or a construct-required field is unavailable. For order-to-administration conversion, unexposed means no qualifying documented administration under that operator, not proof of no biological exposure.

## 3.3. Reference implementation

We implemented `medprov` 0.1.0 in Python as an installable package with Draft 2020-12 schemas, contract-generated YAML examples, adapters, compiler, aggregate executor, comparison functions, reporting validator, command-line interface, privacy guard, and traceable outputs. Five validation judgments remain separate: syntactically valid, adapter supported, measurable, executable, and reproducible/traceable. Each generated specification stores the schema, operator, binding contract, code list, generator, version, and SHA-256 hashes. The public repository includes a wheel, source distribution, synthetic fixtures, documentation, tests, and aggregate evidence.

## 3.4. Data representations

The exact-parity reference was MIMIC-IV 3.1 [27,28]. Cross-representation evaluation used the official 100-patient MIMIC-IV native 2.2 demonstration [29] and matched MIMIC-IV-on-FHIR 2.1 demonstration [30]. OMOP evaluation used the official MIMIC-IV-OMOP demonstration, whose documented medication transformation is based on prescriptions and pharmacy rather than eMAR details [31]. eICU 2.0 supplied a cross-hospital interface-observability evaluation [32]. Ingredient and class recognition used frozen name expressions and, where available, RxNorm/National Drug Code mappings [33,34].

## 3.5. Evaluation layers

### 3.5.1. Native exact parity and ablation

The reference adapter executed against already-audited, read-only materialized MIMIC tables. We required zero integer discrepancy for 19 frozen parity checks and a beta tolerance of 10⁻¹⁰ for shared stored models. Prespecified ablations added dimensions in stages: table-only record existence; source plus class plus time window; collapsed event semantics; and the full exact-identity operator. Separate ablations changed exact same-order identity to same-class/window matching, altered the A2 order window to hospital overlap, required route for A1, or removed the eMAR deployment gate. We reported counts, agreement, positive/negative agreement, and Jaccard similarity; no definition was selected by statistical significance.

### 3.5.2. Cross-representation capability

In matched native/FHIR demonstrations, we assessed class counts, native identity retention, composite linkage, timestamp equivalence, metadata availability, and relocation of administration semantics. In OMOP, we compared drug-record existence with a strict-administration operator on both the public demonstration and a four-unit synthetic provenance-extension fixture. eICU processing streamed each required gzip member once, projected and filtered frozen class labels before reconciliation, and joined only reduced stay-by-class objects. Classes had to pass prespecified identity, event-count, hospital-count, time-field, and deployment/observability gates. Composite labels were excluded rather than reassigned.

### 3.5.3. Structured literature validator

We represented 40 previously coded MIMIC medication studies as structured records and ran a deterministic validator for native source, executable identity, time origin/window, native event semantics, dose/route rule, and complete five-dimensional operator. Evidence review covered all 40 main texts, 55 of 56 linked supplements, and three article-specific repositories. Generic MIMIC code repositories were not treated as article-specific implementations. The primary coding was performed once; no second-coder agreement or kappa is claimed.

### 3.5.4. Downstream measurement stress tests

Two published MIMIC associations were prespecified before results: an A1 VTE-prophylaxis/order construct with a binary outcome, and an A2 early proton-pump-inhibitor construct with time-to-event outcome. OASIS contributed the frozen severity adjustment [35]. The anchors reproduce the exposure concepts of published MIMIC studies [36,37] but are not efficacy or safety replications. We refit the same frozen regression structure under paired exposure operators and report effect-estimate movement as a measurement stress test only. A1 route availability was evaluated separately as construct measurability. P values were not used to choose operators, classes, windows, or reported comparisons.

## 3.6. Software and artifact validation

Unit, integration, schema, command-line, privacy, synthetic-state, adapter, and parity tests were run locally. A clean virtual environment installed the built wheel and executed a bundled deterministic demo. Cross-model outputs were checked against frozen manifests, contract hashes, privacy constraints, and prespecified invariants. Vector figures were generated from committed aggregate tables; no patient-level coordinates were used.

# 4. Results

## 4.1. Executable method and software validation

The implementation produced versioned, machine-validatable specifications and deterministic four-state classifications (Figure 1; Table 1). All 10 release checks passed. Thirty tests completed with no failures and 70.15% branch-aware code coverage. Both wheel and source distribution built successfully; clean-environment wheel installation resolved contract, code-list and generator hashes and reproduced the four-state demo. Cross-model package validation passed 39/39 artifact, contract, privacy, and internal-consistency checks (Table 2).

## 4.2. Exact native parity

All 19 prespecified MIMIC parity gates passed (Figure 2A). Among 264,171 post-deployment order units, 170,890 (64.69%) had a strict same-POE documented administration and 227,355 (86.06%) had a same-class/window administration. By class, strict conversions were 57,408/113,854 electrolyte orders, 38,758/56,081 insulin orders, 40,705/49,119 intra-abdominal antibiotic orders, 1,855/2,329 prokinetic orders, 18,730/24,655 stress-ulcer-prophylaxis orders, and 13,434/18,133 VTE-prophylaxis orders. The exact values equaled the frozen reference at every checked cell.

The adapter also reproduced the previously retained cross-layer timestamp trace: all 183 primary discordant units linked to raw POE, the median prescription-POE timestamp was 97.18 hours after administration, the eMAR-linked POE timestamp was 5.68 hours before administration, and the paired POE-role separation was 106.10 hours. This identifies different workflow clocks under apparently shared POE terminology rather than random timing noise.

## 4.3. Prespecified ablation localized the consequential dimensions

Relaxing exact same-POE identity to same-class/window matching added 56,465 converted order units (Figure 2B). In A1 (n=20,248), exposed counts were 12,950 for table-only, 12,362 for source/class/window, 12,722 after collapsed event semantics, and 5,538 for the full exact-identity operator. Exact identity versus same-class/window yielded agreement 0.663 and Jaccard 0.448. In A2 (n=2,813), exposed counts were 1,061, 870, 871, and 518, respectively; agreement was 0.875 and Jaccard 0.595.

Time remained independent of identity. Changing the A2 order window from the original ICU-anchored definition to hospital-overlap eligibility increased order exposure from 655 to 776 patients; agreement between the two order definitions was 0.951 and Jaccard similarity was 0.823. The operator therefore localized reclassification to identity and time rather than treating both as a generic source discrepancy.

A1 demonstrated a stronger boundary: route was present and subcutaneous-compatible for 9,940/9,940 eligible order units in the A1 cohort but absent for 0/87,569 strict VTE eMAR events. The route-required administration operator consequently returned 20,248/20,248 analysis units as unmeasurable—not unexposed. Ignoring route made the broad administration operator executable for 12,362 exposed units, but it measured a different construct.

## 4.4. Cross-representation evaluation separated equivalence, transformation, and loss

No evaluated representation preserved every dimension identically (Figure 3). In the matched MIMIC native/FHIR demonstrations, native pharmacy and FHIR MedicationDispense achieved exact class-mapped identity for 3,870/3,870 pharmacy-by-class units. Request transport was partial: frozen-class units numbered 3,903 in native prescriptions and 2,726 in FHIR MedicationRequest. For 2,249 deterministically paired request units, FHIR `authoredOn` equaled native pharmacy `entertime` in every case, not prescription `starttime` or usually POE `ordertime`. First-administration time matched exactly in 1,347/1,353 linked units.

Administration semantics relocated across fields. All 6,697 class-mapped FHIR MedicationAdministration records appeared positive by top-level status, whereas `dosage.method` recovered 5,740 strict-positive events, close to 5,696 native strict eMAR events. FHIR omitted native `emar_id`; a frozen pharmacy/class/time/semantic composite paired 5,220 of 6,253 native-linkable administration events. These results distinguish exact transport, partial transformation, semantic relocation, and non-retention of native record identity.

The OMOP demonstration contained 18,229 `DRUG_EXPOSURE` rows; 48 PPI rows collapsed to 37 person-visit-class units. Record-existence exposure classified all 37 as exposed, but strict documented administration classified all 37 as unmeasurable because literal event state was absent. On the four-unit synthetic fixture, an ATLAS-style record-existence rule classified all four as exposed; the provenance extension separated one exposed, one unexposed, one unresolved, and one unmeasurable unit. Removing the extension made all four unmeasurable.

Full eICU streaming processed 7,301,853 medication rows and 4,803,719 infusion rows without a full-table many-to-many join. Three of six classes passed all frozen interface gates. Same-stay/class/window reconciliation linked 3,696/167,806 stress-ulcer-prophylaxis, 7,491/134,102 VTE-prophylaxis, and 224/88,816 intra-abdominal-antibiotic order units to an administration-like infusion record. Electrolytes and insulin failed identity-unambiguity because three composite labels matched both classes; prokinetics failed minimum event/hospital gates. These low reconciliations describe non-equivalent interfaces and observability, not external clinical validity.

## 4.5. Published studies rarely specified an executable operator

The deterministic reporting validator reproduced the structured landscape audit (Figure 4). Seven of 40 studies named a native medication source, 2 specified database-executable identity, 35 reported a time origin/window, none reported literal native event-state semantics, and 30 described a dose or route rule. No study supplied all five dimensions as a complete executable operator. This finding does not establish that the underlying analyses were incorrect; it establishes that their published evidence was insufficient to reproduce the medication-exposure classification without investigator inference.

## 4.6. Reclassification propagated to downstream estimates

The two anchors showed different exposure sensitivity (Figure 5; Table 3). In A1, the order-defined odds ratio (OR) was 1.868 (95% confidence interval [CI], 1.715–2.036). Strict same-POE administration produced OR 1.953 (1.788–2.133; Δlog effect 0.044), whereas same-class/window administration produced OR 0.907 (0.831–0.990; Δlog effect −0.723), crossing the null direction. The dose-constrained broad comparator was similar (OR 0.909), while the clinically required route remained structurally unmeasurable.

In A2, the original order-defined hazard ratio (HR) was 1.904 (1.683–2.154), strict administration HR was 1.926 (1.689–2.196; Δlog effect 0.012), and same-class/window administration HR was 1.208 (1.070–1.363; Δlog effect −0.455). Under hospital-overlap order eligibility, order HR was 1.643 (1.457–1.854), strict administration HR was 1.927 (1.691–2.196; Δlog effect 0.159), and same-class/window administration HR remained 1.208 (Δlog effect −0.308). Identity alignment was therefore necessary but not sufficient: changing the time operator altered both cohort membership and the paired estimate. These are propagation demonstrations, not drug-effect conclusions.

# 5. Discussion

## 5.1. Principal findings

This study turns medication-exposure provenance from a narrative caveat into an executable method. The positive result is not simply that orders and administrations differ. It is that a single five-dimensional operator reproduced a frozen native analysis exactly, identified which dimension caused reclassification, distinguished unmeasurable from unexposed, and executed bounded capability tests across FHIR, OMOP, and eICU without redefining the clinical construct after seeing results.

Three findings carry the main methodological increment. First, identity is not a drug-name synonym: exact same-order and same-class/window operators differed by 56,465 converted units. Second, time is not merely a covariate: FHIR carried pharmacy-entry time in `MedicationRequest.authoredOn`, MIMIC POE roles differed by about 106 hours in a discordant trace, and an alternate A2 time window changed estimate separation despite aligned medication identity. Third, metadata availability is source-specific: route was complete at the A1 order layer and absent at the evaluated administration layer. A valid operator must therefore state what cannot be measured, not substitute a convenient source and retain the original construct label.

## 5.2. Relation to existing standards

The method complements rather than replaces existing interoperability, common-data-model, phenotyping, and reporting systems. FHIR makes workflow roles explicit, but native meaning can relocate across fields. OMOP/ATLAS makes common-model cohorts reusable and executable, but a drug record cannot be assumed to represent documented administration when source event state is absent. PheKB and CQL support dissemination and executable logic, while RECORD-PE, STaRT-RWE, and HARPER improve reporting and protocol transparency. `medprov` supplies the medication-specific provenance contract those systems can carry or call.

This framing is consistent with broader calls to retain provenance during EHR harmonization [38] and to report data-quality assessment transparently [39]. It adds a concrete execution consequence: a missing dimension yields a declared capability state and, when scientifically required, a fail-closed classification. Versioned contracts, hashes, synthetic fixtures, and aggregate evidence also align with FAIR principles [40] and reproducible computational practice [41]. The established MIMIC code ecosystem demonstrates the value of public query artifacts [42]; the present method adds a schema that records what each medication query means.

## 5.3. Applicability

The operator is most useful when different clinical workflow layers can plausibly answer different questions. Order layers represent treatment intention; pharmacy layers represent verification or dispensing workflow; eMAR-like layers represent documented administration; and none alone guarantees biological exposure. A study of clinician decision-making may appropriately choose orders, whereas a study requiring documented delivery may require administration semantics and fail if those semantics are unavailable. The operator does not privilege a universal “best table”; it makes the match between scientific construct and observable layer testable.

The implementation can be applied prospectively before cohort generation, retrospectively as a reporting validator, or during data-model transport. A specification can be compiled against a target adapter, and the adapter can report whether each source, identity, clock, state, and metadata field is supported. This provides a practical pre-analysis gate: proceed when the construct is executable, revise the scientific question explicitly when a different construct is acceptable, or report non-measurability without creating false negatives.

## 5.4. Limitations

MIMIC-IV is a single-center reference dataset, and exact native parity validates implementation fidelity rather than clinical truth. The matched FHIR and OMOP resources are small public demonstrations; they test representation behavior, not full-dataset transport. eICU lacks a native cross-source medication key and was limited to interface semantics, with no claim of external validation or hospital quality. Medication recognition used frozen name/code rules and does not establish universal terminology coverage.

The 40-study landscape sample was restricted by open access; excluded studies could have higher or lower reporting completeness. One coder performed the primary abstraction, and no inter-rater statistic is claimed. The validator measures reported evidence rather than hidden analytic correctness. The downstream anchors preserve selected published-style models only to demonstrate measurement propagation; residual confounding, clinical indication, treatment selection, and other causal biases preclude efficacy or safety interpretation. Finally, documented administration remains short of biological ingestion or pharmacologic exposure.

# 6. Conclusion

Medication exposure in EHR research is a provenance-sensitive computation. A five-dimensional, machine-executable operator made source, identity, time, event semantics, and metadata requirements explicit; reproduced a frozen native reference exactly; localized semantic transformation and loss across FHIR, OMOP, and eICU; and showed how classification differences can propagate to downstream estimates. The method is applicable as a pre-analysis measurability gate, a cross-representation transport contract, and a reporting artifact. Its central discipline is simple: when the required evidence is absent, say unmeasurable rather than manufacture unexposed.

# CRediT authorship contribution statement

Jiajun Luo: Conceptualization, Methodology, Software, Formal analysis, Data curation, Visualization, Writing – original draft. Qinglong Chen: Methodology, Validation, Investigation, Writing – review and editing. Jing Liu: Validation, Investigation, Writing – review and editing. Fanghui Lu: Conceptualization, Supervision, Project administration, Writing – review and editing. Xiaolong Liang: Conceptualization, Supervision, Project administration, Writing – review and editing.

# Funding

This work was supported by the National Natural Science Foundation of China Youth Program (grant 82403569) and the Chongqing Postdoctoral Special Science Foundation (grant 2024CQBSHTB3146). The funders had no role in study design; data analysis or interpretation; preparation of the manuscript; or the decision to submit.

# Ethics statement

This study used deidentified secondary data from MIMIC-IV and eICU. The creation and sharing of these databases were approved by the relevant institutional review boards, with informed-consent requirements waived as described in the source publications. Access was limited to credentialed users who completed the required data-use training and agreements. The present study involved no patient contact and distributed no patient-level or identifiable data.

# Declaration of competing interest

The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

# Declaration of generative AI and AI-assisted technologies in the manuscript preparation process

During preparation of this work, the authors used OpenAI GPT-based tools to assist with English-language editing, code drafting, document assembly, and quality-control scripting. The authors reviewed and edited all outputs and take full responsibility for the content. These tools did not define the frozen scientific contracts, select analyses based on results, access restricted patient-level data, or determine the conclusions. All scientific figures were generated programmatically from committed aggregate tables; no generative-image system was used for the submitted figures.

# Data and code availability

MIMIC-IV and eICU are available to credentialed users through PhysioNet under their respective data-use agreements. Restricted source data and patient-level derived data cannot be redistributed. The `medprov` specification, source code, generated example operators, synthetic fixtures, tests, aggregate validation outputs, figure-generation code, and frozen contracts are available at https://github.com/jiajunluo430-creator/mimic-exposure-provenance-operator. The repository emits aggregate-only public outputs and does not contain patient, encounter, stay, order, pharmacy, POE, or eMAR identifiers.

# Tables

## Table 1. Five-dimensional medication-exposure provenance operator and executable behavior

| Dimension | Required specification | Example implementation question | Fail-closed consequence |
|---|---|---|---|
| Source (S) | Clinical layer, resource/table, deployment and observability | Is the selected layer treatment intention, dispensing, or documented administration? | Missing/unobservable layer → unmeasurable |
| Identity (I) | Vocabulary/name list, native keys, revisions, deduplication, match mode | Must administration share an order key, or is same class/window sufficient? | Ambiguous/unresolved identity retained separately |
| Time (T) | Origin, assignment timestamp, interval boundaries, grace, censoring | Does `authoredOn` represent order time, pharmacy entry, or another workflow clock? | Unsupported/missing required clock → unresolved or unmeasurable |
| Event semantics (E) | Literal positive, negative, excluded and unresolved states; precedence | Do held, not-given, confirmed, flushed and blank events enter exposure or denominator? | Unmapped state → unresolved; excluded states remain outside denominator |
| Metadata (M) | Required route, dose, unit, frequency and value constraints | Can a prophylactic construct be separated from therapeutic delivery? | Required field absent at layer → unmeasurable |
| Output | Exposed, unexposed, unresolved, unmeasurable | What claim does the observable evidence support? | Absence is not converted into a false negative |

## Table 2. Prespecified evaluation layers, target claims, and achieved gates

| Evaluation layer | Data/fixture | Target claim | Prespecified gate | Result |
|---|---|---|---|---|
| Native reference | MIMIC-IV 3.1 | Implementation fidelity | 19 zero-tolerance count/model checks | PASS, 19/19 |
| Operator ablation | MIMIC A1/A2 and six classes | Dimension-specific reclassification and measurability | Frozen variants retained regardless of result | PASS; identity, time and route localized |
| FHIR functional transport | Matched native 2.2/FHIR 2.1 demos | Exact, transformed, relocated or unavailable semantics | Frozen integrity, identity, time and state comparisons | PASS_FUNCTIONAL_CROSS_SCHEMA |
| OMOP capability | Official demo + synthetic extension | Record-existence capability and semantic loss | Deterministic four-state fixture | PASS semantic ablation; capability smoke test |
| eICU interface comparison | Full eICU 2.0 ZIP | Source observability under missing native identity | Five per-class feasibility gates | 3/6 classes executable; not external validation |
| Reporting validator | 40 structured publication records | Published operator reproducibility | Deterministic fields; no prose inference | PASS; 0/40 complete operators |
| Software release | Wheel, sdist, tests, clean environment | Installability and traceability | Ten release checks | PASS, 10/10; 30 tests |
| Cross-model package | Aggregate artifacts and manifests | Artifact integrity, privacy, frozen invariants | 39 validation checks | PASS, 39/39 |

## Table 3. Prespecified downstream measurement stress tests

| Anchor | Order operator/window | Administration operator | Order exposed | Administration exposed | Order estimate (95% CI) | Administration estimate (95% CI) | Δlog(admin−order) |
|---|---|---|---:|---:|---|---|---:|
| A1 | Original | Strict same-POE | 7,047 | 5,538 | OR 1.868 (1.715–2.036) | OR 1.953 (1.788–2.133) | 0.044 |
| A1 | Original | Same-class/window | 7,047 | 12,362 | OR 1.868 (1.715–2.036) | OR 0.907 (0.831–0.990) | −0.723 |
| A2 | Original ICU window | Strict same-POE | 655 | 518 | HR 1.904 (1.683–2.154) | HR 1.926 (1.689–2.196) | 0.012 |
| A2 | Original ICU window | Same-class/window | 655 | 870 | HR 1.904 (1.683–2.154) | HR 1.208 (1.070–1.363) | −0.455 |
| A2 | Hospital-overlap | Strict same-POE | 776 | 521 | HR 1.643 (1.457–1.854) | HR 1.927 (1.691–2.196) | 0.159 |
| A2 | Hospital-overlap | Same-class/window | 776 | 870 | HR 1.643 (1.457–1.854) | HR 1.208 (1.070–1.363) | −0.308 |

**Note:** A1 additionally required prophylactic route. At the administration layer this construct was unmeasurable because route was available for 0/87,569 strict VTE eMAR events. All estimates are measurement stress tests; none is a causal drug-effect estimate.

# Figure legends

## Figure 1. Machine-executable medication-exposure provenance architecture

Panel A shows four evaluated EHR representations passing through version-gated adapters into a canonical medication-event representation while retaining clinical role, native identity, time, event state, and required metadata. Panel B shows the five-dimensional operator, validation states, four deterministic terminal classifications, aggregate comparison, and downstream stress testing.

## Figure 2. Native parity and prespecified operator ablation

Panel A compares frozen expected and `medprov`-generated class counts on identical log scales; all points fall on the identity line and 19 of 19 parity checks passed. Panel B shows exposed proportions for table-only, source/class/window, collapsed-semantics, and full exact-identity operators in A1 and A2, plus the fail-closed route-required A1 result.

## Figure 3. Bounded cross-representation and cross-database evaluation

Panel A summarizes supported, partial or relocated, and unavailable provenance capabilities in native MIMIC-IV, matched native/FHIR demonstrations, an OMOP demonstration, and eICU. Panel B reports quantitative matched-demo FHIR identity and time concordance. Panel C shows fail-closed state distributions in OMOP and eICU evaluations.

## Figure 4. Structured reporting validator results

Panel A reports how often 40 coded MIMIC medication studies supplied each provenance dimension. Panel B shows the narrowing from 40 encoded studies to 7 with a named native source, 2 with executable identity, and none with native event semantics or a complete executable operator.

## Figure 5. Downstream reclassification and effect-estimate stress tests

Panel A compares full exact-identity with same-class/window administration and reports positive Jaccard agreement, while separately identifying structural route non-measurability. Panel B connects paired order- and administration-defined association estimates under exact-identity, same-class/window, and alternate time-window operators. The estimates demonstrate measurement propagation and are not causal drug-effect estimates.

# References

1. Hersh WR, Weiner MG, Embi PJ, et al. Caveats for the use of operational electronic health record data in comparative effectiveness research. Med Care. 2013;51(8 Suppl 3):S30–S37. doi:10.1097/MLR.0b013e31829b1dbd.
2. Johnson KE, Kamineni A, Fuller S, Olmstead D, Wernli KJ. How the provenance of electronic health record data matters for research: a case example using system mapping. EGEMS (Wash DC). 2014;2(1):1058. doi:10.13063/2327-9214.1058.
3. Weiskopf NG, Weng C. Methods and dimensions of electronic health record data quality assessment: enabling reuse for clinical research. J Am Med Inform Assoc. 2013;20(1):144–151. doi:10.1136/amiajnl-2011-000681.
4. Kahn MG, Callahan TJ, Barnard J, et al. A harmonized data quality assessment terminology and framework for the secondary use of electronic health record data. EGEMS (Wash DC). 2016;4(1):1244. doi:10.13063/2327-9214.1244.
5. Thai TN, Winterstein AG. Core concepts in pharmacoepidemiology: measurement of medication exposure in routinely collected healthcare data for causal inference studies in pharmacoepidemiology. Pharmacoepidemiol Drug Saf. 2024;33(3):e5683. doi:10.1002/pds.5683.
6. Clary A, Lin ND, Lasky T, Reynolds MW, Chokkalingam A, Rodriguez-Watson C. Considerations for defining medication exposure when analyzing real-world data. Pharmacoepidemiol Drug Saf. 2023;32(8):933–937. doi:10.1002/pds.5613.
7. Hempenius M, Groenwold RHH, de Boer A, Klungel OH, Gardarsdottir H. Drug exposure misclassification in pharmacoepidemiology: sources and relative impact. Pharmacoepidemiol Drug Saf. 2021;30(12):1703–1715. doi:10.1002/pds.5346.
8. Hripcsak G, Albers DJ. Next-generation phenotyping of electronic health records. J Am Med Inform Assoc. 2013;20(1):117–121. doi:10.1136/amiajnl-2012-001145.
9. Mo H, Thompson WK, Rasmussen LV, et al. Desiderata for computable representations of electronic health records-driven phenotype algorithms. J Am Med Inform Assoc. 2015;22(6):1220–1230. doi:10.1093/jamia/ocv112.
10. Kirby JC, Speltz P, Rasmussen LV, et al. PheKB: a catalog and workflow for creating electronic phenotype algorithms for transportability. J Am Med Inform Assoc. 2016;23(6):1046–1052. doi:10.1093/jamia/ocv202.
11. Pacheco JA, Rasmussen LV, Kiefer RC, et al. A case study evaluating the portability of an executable computable phenotype algorithm across multiple institutions and electronic health record environments. J Am Med Inform Assoc. 2018;25(11):1540–1546. doi:10.1093/jamia/ocy101.
12. Hripcsak G, et al. Facilitating phenotype transfer using a common data model. J Biomed Inform. 2019;96:103253. doi:10.1016/j.jbi.2019.103253.
13. Health Level Seven International. FHIR Release 4: Medications module. https://hl7.org/fhir/R4/medications-module.html. Accessed August 5, 2026.
14. Bennett AM, et al. MIMIC-IV on FHIR: converting a public EHR dataset to FHIR. J Am Med Inform Assoc. 2023;30(4):718–725. doi:10.1093/jamia/ocad002.
15. Hripcsak G, Duke JD, Shah NH, et al. Observational Health Data Sciences and Informatics (OHDSI): opportunities for observational researchers. Stud Health Technol Inform. 2015;216:574–578. doi:10.3233/978-1-61499-564-7-574.
16. Overhage JM, Ryan PB, Reich CG, Hartzema AG, Stang PE. Validation of a common data model for active safety surveillance research. J Am Med Inform Assoc. 2012;19(1):54–60. doi:10.1136/amiajnl-2011-000376.
17. Voss EA, Makadia R, Matcho A, et al. Feasibility and utility of applications of the common data model to multiple, disparate observational health databases. J Am Med Inform Assoc. 2015;22(3):553–564. doi:10.1093/jamia/ocu023.
18. Observational Health Data Sciences and Informatics. OMOP Common Data Model version 5.4. https://ohdsi.github.io/CommonDataModel/cdm54.html. Accessed August 5, 2026.
19. Observational Health Data Sciences and Informatics. The Book of OHDSI: Defining cohorts. https://ohdsi.github.io/TheBookOfOhdsi/Cohorts.html. Accessed August 5, 2026.
20. Health Level Seven International. Clinical Quality Language specification, release 1.5.3. https://cql.hl7.org/01-introduction.html. Accessed August 5, 2026.
21. JSON Schema. Draft 2020-12. https://json-schema.org/draft/2020-12. Accessed August 5, 2026.
22. Langan SM, Schmidt SAJ, Wing K, et al. The Reporting of studies Conducted using Observational Routinely collected health Data statement for pharmacoepidemiology (RECORD-PE). BMJ. 2018;363:k3532. doi:10.1136/bmj.k3532.
23. Wang SV, Pinheiro S, Hua W, et al. STaRT-RWE: structured template for planning and reporting on the implementation of real world evidence studies. BMJ. 2021;372:m4856. doi:10.1136/bmj.m4856.
24. Wang SV, Pottegård A, Crown W, et al. HARmonized Protocol Template to Enhance Reproducibility of Hypothesis Evaluating Real-World Evidence Studies on Treatment Effects: a good practices report of a joint ISPE/ISPOR task force. Value Health. 2022;25(10):1663–1672. doi:10.1016/j.jval.2022.09.001.
25. Benchimol EI, Smeeth L, Guttmann A, et al. The REporting of studies Conducted using Observational Routinely-collected health Data (RECORD) statement. PLoS Med. 2015;12(10):e1001885. doi:10.1371/journal.pmed.1001885.
26. von Elm E, Altman DG, Egger M, Pocock SJ, Gøtzsche PC, Vandenbroucke JP. The Strengthening the Reporting of Observational Studies in Epidemiology (STROBE) statement. Lancet. 2007;370(9596):1453–1457. doi:10.1016/S0140-6736(07)61602-X.
27. Johnson AEW, Bulgarelli L, Shen L, et al. MIMIC-IV, a freely accessible electronic health record dataset. Sci Data. 2023;10:1. doi:10.1038/s41597-022-01899-x.
28. Johnson A, Bulgarelli L, Pollard T, et al. MIMIC-IV (version 3.1). PhysioNet. 2024. doi:10.13026/kpb9-mt58.
29. Johnson A, Bulgarelli L, Pollard T, et al. MIMIC-IV Clinical Database Demo (version 2.2). PhysioNet. 2023. doi:10.13026/dp1f-ex47.
30. Bennett A, et al. MIMIC-IV on FHIR (version 2.1). PhysioNet. 2024. doi:10.13026/rrj1-ny66.
31. Kallfelz M, et al. MIMIC-IV-OMOP Clinical Database Demo (version 0.9). PhysioNet. 2021. doi:10.13026/p1f5-7x35.
32. Pollard TJ, Johnson AEW, Raffa JD, Celi LA, Mark RG, Badawi O. The eICU Collaborative Research Database, a freely available multi-center database for critical care research. Sci Data. 2018;5:180178. doi:10.1038/sdata.2018.178.
33. Nelson SJ, Zeng K, Kilbourne J, Powell T, Moore R. Normalized names for clinical drugs: RxNorm at 6 years. J Am Med Inform Assoc. 2011;18(4):441–448. doi:10.1136/amiajnl-2011-000116.
34. National Library of Medicine. RxNav APIs: RxNorm API. https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html. Accessed August 5, 2026.
35. Johnson AEW, Kramer AA, Clifford GD. A new severity of illness scale using a subset of Acute Physiology and Chronic Health Evaluation data elements shows comparable predictive accuracy. Crit Care Med. 2013;41(7):1711–1718. doi:10.1097/CCM.0b013e31828a24fe.
36. Muchintala R, Khan A, Kalia K, Baig SM. Missed venous thromboembolism prophylaxis in ICU patients: a retrospective cohort study using the Medical Information Mart for Intensive Care IV (MIMIC-IV). Cureus. 2025;17(6):e86370. doi:10.7759/cureus.86370.
37. Ma C, Zhang L, Wang M, Zhang F, Zhang L. Prophylactic proton pump inhibitor use and all-cause mortality in adult sepsis patients: a retrospective analysis based on the MIMIC-IV database. Front Pharmacol. 2025;16:1545533. doi:10.3389/fphar.2025.1545533.
38. Marsolo K, Curtis L, Qualls L, et al. Assessing the harmonization of structured electronic health record data to reference terminologies and data completeness through data provenance. Learn Health Syst. 2025;9(2):e10468. doi:10.1002/lrh2.10468.
39. Kahn MG, Brown JS, Chun AT, et al. Transparent reporting of data quality in distributed data networks. EGEMS (Wash DC). 2015;3(1):1052. doi:10.13063/2327-9214.1052.
40. Wilkinson MD, Dumontier M, Aalbersberg IJ, et al. The FAIR Guiding Principles for scientific data management and stewardship. Sci Data. 2016;3:160018. doi:10.1038/sdata.2016.18.
41. Sandve GK, Nekrutenko A, Taylor J, Hovig E. Ten simple rules for reproducible computational research. PLoS Comput Biol. 2013;9(10):e1003285. doi:10.1371/journal.pcbi.1003285.
42. Johnson AEW, Stone DJ, Celi LA, Pollard TJ. The MIMIC Code Repository: enabling reproducibility in critical care research. J Am Med Inform Assoc. 2018;25(1):32–39. doi:10.1093/jamia/ocx084.
