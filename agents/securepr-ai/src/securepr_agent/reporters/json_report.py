"""JSON report formatter for SecurePR Agent."""
from securepr_agent.models import ScanReport


def generate_json_report(report: ScanReport, indent: int = 2) -> str:
    return report.model_dump_json(indent=indent)
