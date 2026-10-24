"""Offline evaluation for synthetic or locally labeled Cloud Run logs."""

import json
from pathlib import Path

from log_diagnosis import diagnose_log_file


EXPECTED_LABELS = {
    "port_failure.log": "PORT_BIND_FAILURE",
    "port_failure_alt.log": "PORT_BIND_FAILURE",
    "google_docs_port_failure.log": "PORT_BIND_FAILURE",
    "port_healthy_unknown.log": "UNCLASSIFIED_LOG",
    "missing_dependency.log": "MISSING_DEPENDENCY",
    "missing_dependency_alt.log": "MISSING_DEPENDENCY",
    "dependency_healthy_unknown.log": "UNCLASSIFIED_LOG",
    "build_dependency.log": "BUILD_DEPENDENCY_FAILURE",
    "build_dependency_alt.log": "BUILD_DEPENDENCY_FAILURE",
    "build_healthy_unknown.log": "UNCLASSIFIED_LOG",
    "startup_command.log": "STARTUP_COMMAND_FAILURE",
    "startup_command_alt.log": "STARTUP_COMMAND_FAILURE",
    "startup_healthy_unknown.log": "UNCLASSIFIED_LOG",
    "memory_limit.log": "MEMORY_LIMIT",
    "memory_limit_alt.log": "MEMORY_LIMIT",
    "google_docs_memory_limit.log": "MEMORY_LIMIT",
    "memory_healthy_unknown.log": "UNCLASSIFIED_LOG",
    "startup_probe.log": "STARTUP_PROBE_FAILURE",
    "startup_probe_alt.log": "STARTUP_PROBE_FAILURE",
    "google_docs_no_instance.log": "NO_AVAILABLE_INSTANCE",
    "probe_healthy_unknown.log": "UNCLASSIFIED_LOG",
    "unknown.log": "UNCLASSIFIED_LOG",
}


SUPPORTED_LABELS = set(EXPECTED_LABELS.values())


def load_labeled_dataset(manifest_path):
    """Load local JSON labels and ensure referenced logs stay beside the manifest."""
    manifest_path = Path(manifest_path).expanduser().resolve()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Cannot read dataset manifest '{}': {}".format(manifest_path, error)) from error

    if not isinstance(data, list) or not data:
        raise ValueError("Dataset manifest must be a non-empty JSON array.")

    cases = []
    case_ids = set()
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError("Dataset item {} must be a JSON object.".format(index))
        case_id = item.get("id")
        relative_path = item.get("file")
        expected = item.get("expected")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Dataset item {} needs a non-empty 'id'.".format(index))
        if case_id in case_ids:
            raise ValueError("Duplicate dataset case id: {}".format(case_id))
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("Dataset item '{}' needs a relative 'file'.".format(case_id))
        if Path(relative_path).is_absolute():
            raise ValueError("Dataset item '{}' file must be relative.".format(case_id))
        if expected not in SUPPORTED_LABELS:
            raise ValueError(
                "Dataset item '{}' has unsupported expected label: {!r}.".format(
                    case_id, expected
                )
            )

        log_path = (manifest_path.parent / relative_path).resolve()
        if not log_path.is_relative_to(manifest_path.parent):
            raise ValueError("Dataset item '{}' file must stay inside the dataset folder.".format(case_id))
        if not log_path.is_file():
            raise ValueError("Dataset log does not exist for case '{}': {}".format(case_id, relative_path))
        cases.append({"id": case_id, "file": relative_path, "path": log_path, "expected": expected})
        case_ids.add(case_id)
    return cases


def evaluate_cases(cases, dataset_name):
    """Return accuracy, per-class metrics, confusion matrix, and case results."""
    results = []

    for case in cases:
        diagnoses = diagnose_log_file(case["path"])
        predicted = diagnoses[0]["check"]
        results.append(
            {
                "id": case["id"],
                "expected": case["expected"],
                "predicted": predicted,
                "correct": case["expected"] == predicted,
            }
        )

    labels = sorted(SUPPORTED_LABELS | {result["predicted"] for result in results})
    matrix = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for result in results:
        matrix[result["expected"]][result["predicted"]] += 1

    per_class = {}
    for label in labels:
        true_positive = matrix[label].get(label, 0)
        false_positive = sum(
            matrix[actual].get(label, 0) for actual in labels if actual != label
        )
        false_negative = sum(
            count for predicted, count in matrix[label].items() if predicted != label
        )
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(matrix[label].values()),
        }

    count = len(results)
    accuracy = sum(result["correct"] for result in results) / count if count else 0.0
    macro_f1 = sum(item["f1"] for item in per_class.values()) / len(per_class) if per_class else 0.0
    return {
        "dataset": dataset_name,
        "cases": count,
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": matrix,
        "results": results,
    }


def evaluate_fixture_set(fixtures_dir=None):
    """Evaluate the checked-in synthetic regression fixtures."""
    if fixtures_dir is None:
        fixtures_dir = Path(__file__).parent / "tests" / "fixtures"
    fixtures_dir = Path(fixtures_dir).resolve()
    cases = [
        {
            "id": filename,
            "file": filename,
            "path": fixtures_dir / filename,
            "expected": expected,
        }
        for filename, expected in EXPECTED_LABELS.items()
    ]
    return evaluate_cases(cases, "synthetic_checked_in_fixtures")


def evaluate_labeled_dataset(manifest_path):
    """Evaluate a user-provided local dataset without copying its logs."""
    manifest_path = Path(manifest_path).expanduser().resolve()
    cases = load_labeled_dataset(manifest_path)
    return evaluate_cases(cases, "local_manifest:{}".format(manifest_path.name))