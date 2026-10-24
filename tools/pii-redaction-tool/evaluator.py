"""Evaluation system for PII detection and redaction."""
import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path

from sklearn.metrics import precision_score, recall_score, f1_score, classification_report
import pandas as pd

from pii_detector import PIIDetector, PIIEntity
from redaction_engine import ComplianceRedactor


@dataclass
class EvaluationResult:
    """Result of PII detection evaluation."""
    precision: float
    recall: float
    f1_score: float
    false_positives: int
    false_negatives: int
    true_positives: int
    category_metrics: Dict[str, Dict[str, float]]


@dataclass
class TestCase:
    """Test case for evaluation."""
    text: str
    expected_entities: List[Dict]
    description: str


class PIIEvaluator:
    """Evaluator for PII detection and redaction."""

    def __init__(self, detector: PIIDetector, redactor: ComplianceRedactor):
        """Initialize evaluator."""
        self.detector = detector
        self.redactor = redactor

    def evaluate_detection(
        self,
        test_cases: List[TestCase]
    ) -> EvaluationResult:
        """
        Evaluate PII detection performance.

        Args:
            test_cases: List of test cases with expected entities

        Returns:
            EvaluationResult with metrics
        """
        all_predicted = []
        all_expected = []
        category_predictions = {}
        category_expected = {}

        for test_case in test_cases:
            # Detect PII
            detected = self.detector.detect_pii(test_case.text)

            # Convert to binary labels for each character
            predicted_labels = self._text_to_labels(test_case.text, detected)
            expected_labels = self._text_to_labels(
                test_case.text,
                self._dict_to_entities(test_case.expected_entities)
            )

            all_predicted.extend(predicted_labels)
            all_expected.extend(expected_labels)

            # Track by category
            for entity in detected:
                if entity.category not in category_predictions:
                    category_predictions[entity.category] = []
                    category_expected[entity.category] = []
                category_predictions[entity.category].append(1)

            for entity in test_case.expected_entities:
                if entity['category'] not in category_expected:
                    category_expected[entity['category']] = []
                category_expected[entity['category']].append(1)

        # Calculate overall metrics
        precision = precision_score(all_expected, all_predicted, zero_division=0)
        recall = recall_score(all_expected, all_predicted, zero_division=0)
        f1 = f1_score(all_expected, all_predicted, zero_division=0)

        # Calculate counts
        fp = sum(1 for p, e in zip(all_predicted, all_expected) if p == 1 and e == 0)
        fn = sum(1 for p, e in zip(all_predicted, all_expected) if p == 0 and e == 1)
        tp = sum(1 for p, e in zip(all_predicted, all_expected) if p == 1 and e == 1)

        # Calculate category-specific metrics
        category_metrics = {}
        for category in set(list(category_predictions.keys()) + list(category_expected.keys())):
            cat_pred = category_predictions.get(category, [])
            cat_exp = category_expected.get(category, [])

            if len(cat_exp) > 0:
                cat_precision = len([p for p in cat_pred if p]) / max(len(cat_pred), 1)
                cat_recall = len([e for e in cat_exp if e]) / max(len(cat_exp), 1)
                cat_f1 = 2 * (cat_precision * cat_recall) / (cat_precision + cat_recall) if (cat_precision + cat_recall) > 0 else 0

                category_metrics[category] = {
                    "precision": cat_precision,
                    "recall": cat_recall,
                    "f1_score": cat_f1
                }

        return EvaluationResult(
            precision=precision,
            recall=recall,
            f1_score=f1,
            false_positives=fp,
            false_negatives=fn,
            true_positives=tp,
            category_metrics=category_metrics
        )

    def evaluate_redaction(
        self,
        test_cases: List[TestCase]
    ) -> Dict:
        """
        Evaluate redaction quality.

        Args:
            test_cases: List of test cases

        Returns:
            Dict with redaction metrics
        """
        results = {
            "total_cases": len(test_cases),
            "successful_redactions": 0,
            "leaked_entities": 0,
            "over_redactions": 0,
            "case_details": []
        }

        for test_case in test_cases:
            detected = self.detector.detect_pii(test_case.text)
            redaction_result = self.redactor.redact_with_compliance(
                test_case.text,
                detected
            )

            # Check if any expected entities are still present
            redacted_text = redaction_result["redacted_text"]
            leaked = 0
            for entity in test_case.expected_entities:
                entity_text = entity['text']
                if entity_text in redacted_text:
                    leaked += 1

            case_result = {
                "description": test_case.description,
                "entities_detected": len(detected),
                "entities_expected": len(test_case.expected_entities),
                "leaked_entities": leaked,
                "redaction_percentage": redaction_result["compliance_report"]["redaction_percentage"]
            }

            results["case_details"].append(case_result)

            if leaked == 0:
                results["successful_redactions"] += 1

            results["leaked_entities"] += leaked

        return results

    def _text_to_labels(self, text: str, entities: List[PIIEntity]) -> List[int]:
        """Convert text and entities to binary labels per character."""
        labels = [0] * len(text)

        for entity in entities:
            for i in range(entity.start, min(entity.end, len(text))):
                labels[i] = 1

        return labels

    def _dict_to_entities(self, entity_dicts: List[Dict]) -> List[PIIEntity]:
        """Convert dict entities to PIIEntity objects."""
        entities = []
        for entity_dict in entity_dicts:
            entities.append(PIIEntity(
                text=entity_dict['text'],
                category=entity_dict['category'],
                confidence=entity_dict.get('confidence', 1.0),
                start=entity_dict['start'],
                end=entity_dict['end'],
                detection_method="test"
            ))
        return entities

    def generate_report(self, detection_result: EvaluationResult, redaction_result: Dict) -> str:
        """Generate comprehensive evaluation report."""
        report = []
        report.append("=" * 80)
        report.append("PII REDACTION AGENT - EVALUATION REPORT")
        report.append("=" * 80)
        report.append("")

        # Detection Metrics
        report.append("DETECTION METRICS")
        report.append("-" * 40)
        report.append(f"Precision: {detection_result.precision:.4f}")
        report.append(f"Recall: {detection_result.recall:.4f}")
        report.append(f"F1 Score: {detection_result.f1_score:.4f}")
        report.append(f"True Positives: {detection_result.true_positives}")
        report.append(f"False Positives: {detection_result.false_positives}")
        report.append(f"False Negatives: {detection_result.false_negatives}")
        report.append("")

        # Category Metrics
        report.append("CATEGORY-SPECIFIC METRICS")
        report.append("-" * 40)
        for category, metrics in detection_result.category_metrics.items():
            report.append(f"{category}:")
            report.append(f"  Precision: {metrics['precision']:.4f}")
            report.append(f"  Recall: {metrics['recall']:.4f}")
            report.append(f"  F1 Score: {metrics['f1_score']:.4f}")
        report.append("")

        # Redaction Metrics
        report.append("REDACTION METRICS")
        report.append("-" * 40)
        report.append(f"Total Test Cases: {redaction_result['total_cases']}")
        report.append(f"Successful Redactions: {redaction_result['successful_redactions']}")
        report.append(f"Leaked Entities: {redaction_result['leaked_entities']}")
        report.append("")

        # Case Details
        report.append("CASE DETAILS")
        report.append("-" * 40)
        for case in redaction_result['case_details']:
            report.append(f"Case: {case['description']}")
            report.append(f"  Detected: {case['entities_detected']}, Expected: {case['entities_expected']}")
            report.append(f"  Leaked: {case['leaked_entities']}")
            report.append(f"  Redaction %: {case['redaction_percentage']}%")
            report.append("")

        return "\n".join(report)


class TestDataManager:
    """Manages test data for evaluation."""

    def __init__(self, data_path: str = "test_data/"):
        """Initialize test data manager."""
        self.data_path = Path(data_path)
        self.data_path.mkdir(parents=True, exist_ok=True)

    def load_test_cases(self, filename: str = "test_cases.json") -> List[TestCase]:
        """Load test cases from JSON file."""
        file_path = self.data_path / filename

        if not file_path.exists():
            return self._create_default_test_cases()

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        test_cases = []
        for item in data:
            test_cases.append(TestCase(
                text=item['text'],
                expected_entities=item['expected_entities'],
                description=item.get('description', '')
            ))

        return test_cases

    def save_test_cases(self, test_cases: List[TestCase], filename: str = "test_cases.json"):
        """Save test cases to JSON file."""
        file_path = self.data_path / filename

        data = []
        for test_case in test_cases:
            data.append({
                'text': test_case.text,
                'expected_entities': test_case.expected_entities,
                'description': test_case.description
            })

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def _create_default_test_cases(self) -> List[TestCase]:
        """Create default test cases."""
        return [
            TestCase(
                text="Contact John Smith at john.smith@example.com or 555-123-4567. SSN: 123-45-6789",
                expected_entities=[
                    {"text": "John Smith", "category": "PERSON", "start": 8, "end": 18, "confidence": 1.0},
                    {"text": "john.smith@example.com", "category": "EMAIL_ADDRESS", "start": 23, "end": 45, "confidence": 1.0},
                    {"text": "555-123-4567", "category": "PHONE_NUMBER", "start": 49, "end": 60, "confidence": 1.0},
                    {"text": "123-45-6789", "category": "US_SSN", "start": 67, "end": 78, "confidence": 1.0}
                ],
                description="Basic PII detection test"
            ),
            TestCase(
                text="Credit card: 4532-1234-5678-9010. IP: 192.168.1.1",
                expected_entities=[
                    {"text": "4532-1234-5678-9010", "category": "CREDIT_CARD", "start": 13, "end": 32, "confidence": 1.0},
                    {"text": "192.168.1.1", "category": "IP_ADDRESS", "start": 38, "end": 49, "confidence": 1.0}
                ],
                description="Financial and network PII"
            ),
            TestCase(
                text="No PII in this text. Just regular information.",
                expected_entities=[],
                description="Negative test - no PII"
            )
        ]
