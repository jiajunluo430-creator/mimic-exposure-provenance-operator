from __future__ import annotations

import json

from medprov.adapters import get_adapter
from medprov.schema import load_document


def test_request_resources_deduplicate_by_retained_native_identifier(repo_root, tmp_path):
    spec = load_document(repo_root / "examples" / "transport" / "fhir_demo_request.yaml")
    resources = []
    for resource_id, status in (("request-a", "completed"), ("request-b", "draft")):
        resources.append(
            {
                "resourceType": "MedicationRequest",
                "id": resource_id,
                "status": status,
                "medprovMedicationClass": "insulin",
                "identifier": [
                    {
                        "system": (
                            "http://mimic.mit.edu/fhir/mimic/identifier/"
                            "medication-request-phid"
                        ),
                        "value": "same-native-pharmacy-id",
                    }
                ],
            }
        )
    path = tmp_path / "MimicMedicationRequest.ndjson"
    path.write_text(
        "".join(json.dumps(resource) + "\n" for resource in resources),
        encoding="utf-8",
    )

    result = get_adapter("mimic_fhir").execute(spec, tmp_path)

    assert result.status == "executed"
    assert result.counts["analysis_units"] == 1
    assert result.counts["exposed"] == 1
    assert result.counts["by_class"] == [
        {
            "medication_class": "insulin",
            "exposed": 1,
            "unexposed": 0,
            "unresolved": 0,
            "unmeasurable": 0,
        }
    ]
