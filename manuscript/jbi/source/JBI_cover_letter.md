August 6, 2026

Editor-in-Chief  
Journal of Biomedical Informatics

Dear Editor,

We submit the Research Paper, “A Machine-Executable Provenance Operator for Medication-Exposure Phenotyping Across Electronic Health Record Representations,” for consideration in the Journal of Biomedical Informatics.

We developed and evaluated a machine-executable, fail-closed provenance operator that distinguishes non-exposure from non-measurability across medication data representations. The five-dimensional operator specifies source, identity, time, event semantics, and construct-required metadata, and the installable Python reference implementation (`medprov`) returns exposed, unexposed, unresolved, or unmeasurable rather than forcing incomplete provenance into a binary label.

We evaluated the method against record-existence, OMOP/ATLAS-style, and FHIR resource-role/status approaches. In the public OMOP demonstration, record existence classified 37/37 PPI person-visit units as exposed, while strict administration was unmeasurable for 37/37 because event state was absent. In matched native/FHIR demonstrations, top-level MedicationAdministration status classified 6,697 records positive, whereas relocated native semantics in `dosage.method` identified 5,740 strict positives—a 16.7% overcall. The operator therefore identifies when a stricter construct is unsupported instead of manufacturing a binary label.

The reference implementation reproduced a frozen MIMIC-IV analysis across 19 checks and 264,171 medication-order units, establishing implementation fidelity. Prespecified ablations localized reclassification to identity, time, event semantics, and route availability. None of 40 coded MIMIC medication studies reported a complete executable exposure operator. Two published-association anchors serve only as downstream measurement stress tests; no causal efficacy or safety claim is made.

The submission fits JBI as a generalizable informatics method with a formal specification, tested adapters, explicit state semantics, executable comparisons, and an installable public artifact. Version 0.1.0 source code, schemas, tests, synthetic fixtures, frozen contracts, aggregate validation outputs, and release artifacts are available at https://github.com/jiajunluo430-creator/mimic-exposure-provenance-operator/releases/tag/v0.1.0. Restricted patient-level data are not redistributed.

The work is original, is not under consideration elsewhere, and has been approved for submission by all authors. The authors declare no competing interests. Thank you for considering this submission.

Sincerely,

Xiaolong Liang, MD, PhD — Department of Gastrointestinal Surgery, The First Affiliated Hospital of Chongqing Medical University, Chongqing 400016, China; 204951@hospital.cqmu.edu.cn
Fanghui Lu, PhD — Department of Cancer Center, The Second Affiliated Hospital of Chongqing Medical University, Chongqing, China; lufh@cqmu.edu.cn

Joint corresponding authors, on behalf of all authors
