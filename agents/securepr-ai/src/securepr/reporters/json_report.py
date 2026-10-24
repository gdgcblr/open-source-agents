"""JSON report serializer for SecurePR AI."""
import json
from securepr.models import ScanReport


def generate_json_report(report: ScanReport, indent: int = 2) -> str:
    """Serializes the ScanReport into formatted JSON string."""
    return report.model_dump_json(indent=indent)
