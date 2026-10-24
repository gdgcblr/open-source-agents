import unittest
from pathlib import Path


from agent import analyze


class AnalyzeTests(unittest.TestCase):
    def test_sample_exposes_expected_heuristics(self):
        sample = Path(__file__).parent / "test_samples" / "stm32_uart.c"
        findings = analyze(sample.read_text(encoding="utf-8"))
        checks = {finding.check for finding in findings}
        self.assertIn("peripheral-clock", checks)
        self.assertIn("volatile-mmio-pointer", checks)
        self.assertIn("register-read-modify-write", checks)
        self.assertIn("shift-width", checks)

    def test_clock_enable_before_register_access_avoids_clock_warning(self):
        source = """\
void init(void) {
    RCC->APB1ENR |= (1U << 17);
    uart->BRR = 3;
}
"""
        findings = analyze(source)
        self.assertNotIn("peripheral-clock", {finding.check for finding in findings})


if __name__ == "__main__":
    unittest.main()
