"""Performance benchmarks for PII Redaction Tool."""
import time
import statistics
from typing import List, Dict
from dataclasses import dataclass

from pii_detector import PIIDetector
from redaction_engine import ComplianceRedactor
from guardrails import SecurityGuardrails


@dataclass
class BenchmarkResult:
    """Benchmark result."""
    operation: str
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float
    std_dev_ms: float
    throughput_per_sec: float


class PerformanceBenchmark:
    """Performance benchmarking suite."""

    def __init__(self):
        """Initialize benchmark suite."""
        self.detector = PIIDetector()
        self.redactor = ComplianceRedactor()
        self.guardrails = SecurityGuardrails()

    def benchmark_detection(self, text: str, iterations: int = 50) -> BenchmarkResult:
        """Benchmark PII detection."""
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            entities = self.detector.detect_pii(text)
            end = time.perf_counter()
            times.append((end - start) * 1000)  # Convert to ms

        avg_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        std_dev = statistics.stdev(times) if len(times) > 1 else 0
        throughput = iterations / (sum(times) / 1000)

        return BenchmarkResult(
            operation="PII Detection",
            avg_time_ms=avg_time,
            min_time_ms=min_time,
            max_time_ms=max_time,
            std_dev_ms=std_dev,
            throughput_per_sec=throughput
        )

    def benchmark_redaction(self, text: str, iterations: int = 50) -> BenchmarkResult:
        """Benchmark PII redaction."""
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            # Skip rate limiting for benchmarks
            self.guardrails.validator.validate_content_type(text)
            self.guardrails.validator.validate_text_encoding(text)
            self.guardrails.validator.validate_input_size(text)
            entities = self.detector.detect_pii(text)
            filtered = self.guardrails.filter_entities(entities)
            result = self.redactor.redact_with_compliance(text, filtered)
            end = time.perf_counter()
            times.append((end - start) * 1000)

        avg_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        std_dev = statistics.stdev(times) if len(times) > 1 else 0
        throughput = iterations / (sum(times) / 1000)

        return BenchmarkResult(
            operation="PII Redaction",
            avg_time_ms=avg_time,
            min_time_ms=min_time,
            max_time_ms=max_time,
            std_dev_ms=std_dev,
            throughput_per_sec=throughput
        )

    def benchmark_full_pipeline(self, text: str, iterations: int = 50) -> BenchmarkResult:
        """Benchmark full pipeline (detect + redact + guardrails)."""
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            # Skip rate limiting for benchmarks
            self.guardrails.validator.validate_content_type(text)
            self.guardrails.validator.validate_text_encoding(text)
            self.guardrails.validator.validate_input_size(text)
            entities = self.detector.detect_pii(text)
            filtered = self.guardrails.filter_entities(entities)
            result = self.redactor.redact_with_compliance(text, filtered)
            self.guardrails.log_detection(text, filtered)
            end = time.perf_counter()
            times.append((end - start) * 1000)

        avg_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        std_dev = statistics.stdev(times) if len(times) > 1 else 0
        throughput = iterations / (sum(times) / 1000)

        return BenchmarkResult(
            operation="Full Pipeline",
            avg_time_ms=avg_time,
            min_time_ms=min_time,
            max_time_ms=max_time,
            std_dev_ms=std_dev,
            throughput_per_sec=throughput
        )

    def run_all_benchmarks(self, text_samples: List[str]) -> Dict[str, List[BenchmarkResult]]:
        """Run all benchmarks on multiple text samples."""
        results = {
            "detection": [],
            "redaction": [],
            "full_pipeline": []
        }

        for i, text in enumerate(text_samples):
            print(f"Benchmarking sample {i + 1}/{len(text_samples)}...")

            detection_result = self.benchmark_detection(text)
            redaction_result = self.benchmark_redaction(text)
            pipeline_result = self.benchmark_full_pipeline(text)

            results["detection"].append(detection_result)
            results["redaction"].append(redaction_result)
            results["full_pipeline"].append(pipeline_result)

        return results

    def print_results(self, results: Dict[str, List[BenchmarkResult]]):
        """Print benchmark results."""
        print("\n" + "=" * 80)
        print("PERFORMANCE BENCHMARK RESULTS")
        print("=" * 80 + "\n")

        for operation, result_list in results.items():
            print(f"\n{operation.upper()}")
            print("-" * 80)

            avg_times = [r.avg_time_ms for r in result_list]
            avg_throughput = [r.throughput_per_sec for r in result_list]

            print(f"Average Time: {statistics.mean(avg_times):.2f} ms")
            print(f"Min Time: {min(avg_times):.2f} ms")
            print(f"Max Time: {max(avg_times):.2f} ms")
            print(f"Std Dev: {statistics.stdev(avg_times):.2f} ms")
            print(f"Throughput: {statistics.mean(avg_throughput):.2f} ops/sec")


def get_test_samples() -> List[str]:
    """Get test samples for benchmarking."""
    return [
        "Contact John Smith at john.smith@example.com or 555-123-4567. SSN: 123-45-6789",
        "Email: test@example.com, Phone: 555-987-6543, Credit Card: 4532-1234-5678-9010",
        "Patient: Jane Doe, DOB: 01/15/1980, Medical ID: MED-12345. Contact: jane@hospital.com",
        "Employee: Robert Johnson, Email: robert.j@company.com, Passport: AB1234567",
        "No PII in this text. Just regular information for benchmarking.",
        "Multiple emails: user1@example.com, user2@example.com, user3@example.com",
        "IP addresses: 192.168.1.1, 10.0.0.1, 172.16.0.1",
        "SSNs: 123-45-6789, 987-65-4321, 555-44-3333",
        "Phone numbers: (555) 123-4567, 555.123.4567, 5551234567",
        "Mixed: Contact john@example.com at 555-123-4567. SSN: 123-45-6789. IP: 192.168.1.1"
    ]


if __name__ == "__main__":
    benchmark = PerformanceBenchmark()
    samples = get_test_samples()

    print("Running performance benchmarks...")
    print(f"Testing {len(samples)} samples with 50 iterations each")

    results = benchmark.run_all_benchmarks(samples)
    benchmark.print_results(results)
