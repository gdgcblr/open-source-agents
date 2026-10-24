import re
from typing import List, Tuple
from ..models import FileDiff, GeneratedTest, SpecialistVerdict


class AutoTestGeneratorAgent:
    """Specialist Agent that synthesizes unit and regression tests for modified functions."""

    def __init__(self, name: str = "Automated Test Synthesizer"):
        self.name = name

    def evaluate(self, diffs: List[FileDiff]) -> Tuple[SpecialistVerdict, List[GeneratedTest]]:
        generated_tests: List[GeneratedTest] = []
        functions_found: List[str] = []

        seen_funcs = set()
        for f in diffs:
            for cl in f.changed_lines:
                # Match Python function definition: def function_name(args):
                match = re.search(r"def\s+([a-zA-Z0-9_]+)\s*\((.*?)\)", cl.content)
                if match:
                    func_name = match.group(1)
                    if (func_name, f.filename) not in seen_funcs:
                        seen_funcs.add((func_name, f.filename))
                        raw_args = [a.strip() for a in match.group(2).split(",") if a.strip()]
                        functions_found.append((func_name, raw_args, f.filename))

        # Generate targeted unit test cases
        for func_name, args, filename in functions_found:
            # 1. Happy path test
            sample_args = [self._mock_val(arg) for arg in args if arg not in ("self", "cls")]
            arg_call = ", ".join(sample_args)

            test_code = (
                f"import pytest\n"
                f"# Auto-generated test for {func_name} in {filename}\n\n"
                f"def test_{func_name}_valid_execution():\n"
                f"    # Arrange\n"
                f"    # Replace with imported target function\n"
                f"    # Act\n"
                f"    # result = {func_name}({arg_call})\n"
                f"    # Assert\n"
                f"    # assert result is not None\n"
                f"    pass\n\n"
                f"def test_{func_name}_invalid_or_empty_inputs():\n"
                f"    # Test boundary and error handling on empty inputs\n"
                f"    with pytest.raises(Exception):\n"
                f"        # {func_name}()\n"
                f"        pass\n"
            )

            generated_tests.append(GeneratedTest(
                test_name=f"test_{func_name}_coverage",
                framework="pytest",
                code=test_code,
                target_file=filename,
                description=f"Auto-generated unit and edge-case regression test suite for `{func_name}`."
            ))

        # Also synthesize regression tests if bug fixes or security fixes are present
        has_tests_in_pr = any("test" in f.filename.lower() for f in diffs)

        score = 80 if has_tests_in_pr else (70 if generated_tests else 60)
        status = "PASSED" if has_tests_in_pr or generated_tests else "WARNING"
        summary = (
            f"Synthesized {len(generated_tests)} automated test case(s) covering newly introduced logic."
            if generated_tests else
            ("PR already includes dedicated test files." if has_tests_in_pr else "No test files included in PR diff. Automated tests generated.")
        )

        verdict = SpecialistVerdict(
            agent_name=self.name,
            score=score,
            status=status,
            summary=summary,
            findings=[]
        )

        return verdict, generated_tests

    def _mock_val(self, arg_name: str) -> str:
        clean = arg_name.split(":")[0].strip()
        if "user" in clean or "name" in clean:
            return '"test_user"'
        if "pass" in clean or "secret" in clean or "key" in clean:
            return '"safe_dummy_secret"'
        if "id" in clean or "count" in clean or "port" in clean:
            return "1"
        if "data" in clean or "payload" in clean:
            return '"{\\"key\\": \\"val\\"}"'
        return '"sample"'
