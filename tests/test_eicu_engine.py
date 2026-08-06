from __future__ import annotations

import csv
import gzip
import io
import zipfile

from medprov.eicu_engine import run_eicu_reconciliation
from medprov.schema import load_document


def csv_gzip_bytes(fieldnames, rows):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(text.getvalue().encode("utf-8"))


def test_eicu_streaming_gate_and_same_class_window(repo_root, tmp_path):
    archive_path = tmp_path / "eicu-test.zip"
    patients = [
        {
            "patientunitstayid": str(index),
            "hospitalid": str((index - 1) % 10 + 1),
            "unittype": "Med-Surg ICU",
        }
        for index in range(1, 101)
    ]
    orders = [
        {
            "medicationid": str(index),
            "patientunitstayid": str(index),
            "drugorderoffset": "0",
            "drugstartoffset": "0",
            "drugname": "Metoclopramide",
            "dosage": "10 mg",
            "routeadmin": "IV",
            "frequency": "q6h",
            "drugstopoffset": "60",
        }
        for index in range(1, 101)
    ]
    infusions = [
        {
            "infusiondrugid": str(index),
            "patientunitstayid": str(index),
            "infusionoffset": "10",
            "drugname": "Metoclopramide",
            "drugrate": "1",
            "infusionrate": "",
            "drugamount": "",
            "volumeoffluid": "",
        }
        for index in range(1, 101)
    ]
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "eicu/patient.csv.gz",
            csv_gzip_bytes(["patientunitstayid", "hospitalid", "unittype"], patients),
        )
        archive.writestr(
            "eicu/medication.csv.gz",
            csv_gzip_bytes(list(orders[0]), orders),
        )
        archive.writestr(
            "eicu/infusionDrug.csv.gz",
            csv_gzip_bytes(list(infusions[0]), infusions),
        )
        archive.writestr(
            "eicu/hospital.csv.gz",
            csv_gzip_bytes(["hospitalid"], [{"hospitalid": str(i)} for i in range(1, 11)]),
        )
        archive.writestr(
            "eicu/treatment.csv.gz",
            csv_gzip_bytes(["treatmentid", "treatmentstring"], []),
        )

    spec = load_document(
        repo_root / "examples" / "transport" / "eicu_six_class_reconciliation.yaml"
    )
    result = run_eicu_reconciliation(archive_path, spec)

    prokinetic_gate = next(
        row
        for row in result["feasibility_gates"]
        if row["medication_class"] == "prokinetic"
    )
    prokinetic_result = next(
        row
        for row in result["class_reconciliation"]
        if row["medication_class"] == "prokinetic"
    )
    assert prokinetic_gate["gate_pass"] is True
    assert prokinetic_result["converted_orders_n"] == 100
    assert prokinetic_result["conversion_pct"] == 100.0
    assert result["counts"]["exposed"] == 100
    assert result["metrics"]["classes_passed"] == ["prokinetic"]
