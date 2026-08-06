August 5, 2026

Editor-in-Chief  
Journal of Biomedical Informatics

Dear Editor,

We submit the Research Paper, “A Machine-Executable Provenance Operator for Medication-Exposure Phenotyping Across Electronic Health Record Representations,” for consideration in the Journal of Biomedical Informatics.

The manuscript addresses a recurring informatics problem: medication exposure is usually reported as if selecting a table or resource completed the phenotype definition. In practice, source role, cross-layer medication identity, workflow time, native event semantics, and dose/route requirements jointly determine whether an EHR record supports the intended exposure construct. We formalize those decisions as a five-dimensional operator and provide an installable Python reference implementation, `medprov`, that returns exposed, unexposed, unresolved, or unmeasurable rather than forcing missing provenance into a binary label.

The submission offers four method-level contributions that we believe fit JBI’s emphasis on innovative and generalizable biomedical informatics methods:

1. a versioned YAML/JSON specification and deterministic compiler/executor for medication-exposure provenance;
2. exact reference parity across 19 frozen MIMIC-IV checks and prespecified ablations that localize the effects of identity, time, event semantics, and metadata;
3. bounded functional evaluation across matched native/FHIR demonstrations, an OMOP demonstration, and eICU interface semantics, explicitly distinguishing equivalence, semantic relocation, and non-measurability; and
4. a structured reporting validator showing that none of 40 coded MIMIC medication studies supplied a complete executable exposure operator.

The key positive result is constructive. The method reproduced 264,171 frozen MIMIC-IV order units exactly, identified 56,465 additional conversions introduced by replacing same-order identity with same-class/window matching, and correctly classified an administration-based prophylactic-anticoagulation construct as unmeasurable when route was absent from 87,569 qualifying eMAR events. In matched native/FHIR demonstrations, it identified exact dispense identity transport, partial request transport, and relocation of administration semantics to `dosage.method`. These results show the method’s range of applicability rather than presenting another single-database use case.

Two previously published MIMIC associations are retained only as downstream measurement stress tests. We report how estimates move under prespecified operators and make no causal efficacy or safety claims. eICU is an interface-semantic comparison, not external validation. Restricted patient-level data are not distributed.

The work is original, is not under consideration elsewhere, and has been approved for submission by all authors. The authors declare no competing interests. Deidentified MIMIC-IV and eICU data were accessed under their governing credentialing and data-use requirements. The complete source code, schemas, synthetic fixtures, tests, frozen contracts, aggregate validation outputs, and figure-generation scripts are available at https://github.com/jiajunluo430-creator/mimic-exposure-provenance-operator.

OpenAI GPT-based tools assisted with English-language editing, code drafting, document assembly, and quality-control scripting. The authors reviewed and edited all outputs and take full responsibility. These tools did not define the frozen scientific contracts, select analyses based on results, access restricted patient-level data, or determine conclusions. Submitted figures were generated programmatically from aggregate tables; no generative-image system was used.

Thank you for considering this submission.

Sincerely,

Xiaolong Liang, MD, PhD  
Department of Gastrointestinal Surgery  
The First Affiliated Hospital of Chongqing Medical University  
Chongqing 400016, China  
Email: 204951@hospital.cqmu.edu.cn

Fanghui Lu, PhD  
Department of Cancer Center  
The Second Affiliated Hospital of Chongqing Medical University  
Chongqing, China  
Email: lufh@cqmu.edu.cn

Joint corresponding authors, on behalf of all authors

