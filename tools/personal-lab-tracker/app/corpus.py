"""Fictional lab visits used to generate sample PDFs and expected rows.

The header of each PDF carries bait identifiers on purpose. Tests check that
those strings never reach the stored rows or the summary fact sheet. An
extraction model, when one is selected, does receive the PDF text as printed.
"""

from __future__ import annotations

BAIT = {
    "name": "Demo User",
    "phone": "00000 00000",
    "email": "demo.user@example.com",
    "record_id": "DEMO-0001",
}

# name, value, unit, reference interval, flag letter printed on the PDF
VISITS: list[dict] = [
    {
        "file": "visit-1.pdf",
        "collected_on": "2025-11-02",
        "panel": "Complete blood count",
        "rows": [
            ("Hemoglobin", "12.4", "g/dL", "13.0-17.0", "L"),
            ("WBC", "6.1", "10^3/uL", "4.0-11.0", ""),
            ("Platelet count", "210", "10^3/uL", "150-450", ""),
        ],
    },
    {
        "file": "visit-2.pdf",
        "collected_on": "2026-02-18",
        "panel": "CBC and lipid profile",
        "rows": [
            ("Hemoglobin", "13.6", "g/dL", "13.0-17.0", ""),
            ("WBC", "7.4", "10^3/uL", "4.0-11.0", ""),
            ("Platelet count", "198", "10^3/uL", "150-450", ""),
            ("LDL cholesterol", "142", "mg/dL", "<100", "H"),
            ("HDL cholesterol", "46", "mg/dL", ">40", ""),
            ("Triglycerides", "160", "mg/dL", "<150", "H"),
        ],
    },
    {
        "file": "visit-3.pdf",
        "collected_on": "2026-06-09",
        "panel": "Glycemic and LDL follow-up",
        "rows": [
            ("HbA1c", "5.4", "%", "4.0-5.6", ""),
            ("Fasting glucose", "92", "mg/dL", "70-99", ""),
            ("LDL cholesterol", "138", "mg/dL", "<100", "H"),
        ],
    },
]
