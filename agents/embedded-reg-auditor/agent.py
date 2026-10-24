"""Heuristic and LLM-powered static checks for bare-metal C/C++ register access."""

from __future__ import annotations

import socket

_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    family = socket.AF_INET
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _ipv4_getaddrinfo

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


@dataclass
class Finding:
    line: int
    check: str
    severity: str
    risk: str
    remediation: str
    snippet: str


PERIPHERAL_ACCESS = re.compile(
    r"\b\w+\s*->\s*(?:CR\w*|DR\w*|SR\w*|MODER|OTYPER|OSPEEDR|PUPDR|"
    r"IDR|ODR|BRR|BSRR|DATA|STATUS|CTRL|CONTROL|CONFIG|BAUD\w*)\b",
    re.IGNORECASE,
)
CLOCK_ENABLE = re.compile(
    r"\b(?:RCC|CLK|CLOCK|CMU|SYSCON|PRCM|PERIPH(?:ERAL)?_CLK)\w*\b"
    r".*(?:ENR|ENABLE|GATE|CLKEN|CLK_EN)|(?:ENR|ENABLE|GATE|CLKEN|CLK_EN).*"
    r"\b(?:RCC|CLK|CLOCK|CMU|SYSCON|PRCM)\w*\b",
    re.IGNORECASE,
)
MMIO_POINTER = re.compile(
    r"\b((?:[A-Za-z_]\w*(?:\s+\w+)?|unsigned\s+(?:char|short|int|long)))"
    r"\s*\*\s*(\w+)\s*=\s*\(\s*([^)]*\*)\s*\)\s*(0x[\da-fA-F]+|\w+)",
)
REGISTER_RMW = re.compile(
    r"(?:\w+\s*->\s*\w+|\w+\.\w+|\b\w*(?:REG|CR|DR|SR|R|CTRL|CONTROL|MODER|ODR|IDR|IER|ISR)\w*)"
    r"\s*(\|=|&=|\^=)",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """You are an expert embedded firmware security and static analysis auditor specializing in bare-metal C/C++ MCU code (ARM Cortex-M, STM32, ESP32, NXP, RISC-V).
Your goal is to inspect hardware register access code for dangerous low-level bugs, hardware undefined behavior, and race conditions.

You must specifically inspect:
1. Peripheral clock gating: Ensure peripheral bus clocks (e.g., RCC AHB/APB enable registers, SYSCON, PRCM, CLKEN) are enabled before accessing peripheral registers (CR, DR, BRR, etc.).
2. Volatile qualification on MMIO: Verify memory-mapped hardware pointers or struct pointers have 'volatile' qualified target types (e.g., `volatile USART_TypeDef *`) so the compiler does not optimize away or reorder hardware reads/writes.
3. Concurrency & non-atomic Read-Modify-Write (RMW) hazards: Flag non-atomic bitwise read-modify-writes (`|=`, `&=`, `^=`) on shared registers that can lead to race conditions with interrupts or clobber hardware status flags. Recommend atomic set/clear registers (e.g., BSRR) or critical sections where appropriate.
4. Shift width overflow & signed UB: Check constant shifts like `(1 << 31)` which cause signed 32-bit overflow in C99/C11. Recommend unsigned constants like `(1U << 31)` or `UINT32_C(1) << 31`.
5. Interrupt priority ranges: Validate Cortex-M NVIC priority values against typical `__NVIC_PRIO_BITS` limits (e.g. 0-15 for 4 bits).

Output your report in clean GitHub-flavored Markdown formatted as follows:
# Embedded Register Audit (Gemini LLM Analysis)

File: `{filename}`
Model: `{model}`

## Executive Summary
[High-level summary of the file health, detected risks, and overall firmware quality.]

## Findings Table
| Line | Check | Severity | Risk | Remediation |
| ---: | --- | --- | --- | --- |
[One row per finding with exact line numbers, check name, severity (Critical/Warning/Info), risk explanation, and remediation guidance.]

## Detailed Findings & Context
[For each finding, provide the line number, code snippet, in-depth root cause explanation, and target MCU architectural considerations.]

## Remediated Code Snippet
```c
[Provide the full corrected C code snippet fixing all identified hazards.]
```
"""

FALLBACK_MODEL = "gemini-3.5-flash"


def analyze(source: str) -> list[Finding]:
    """Run conservative text-based checks; results require datasheet review."""
    lines = source.splitlines()
    findings: list[Finding] = []

    first_access = next(
        (index for index, line in enumerate(lines) if PERIPHERAL_ACCESS.search(line)), None
    )
    if first_access is not None and not any(
        CLOCK_ENABLE.search(line) for line in lines[: first_access + 1]
    ):
        findings.append(
            Finding(
                line=first_access + 1,
                check="peripheral-clock",
                severity="warning",
                risk="The peripheral may be accessed before its clock is enabled; register writes may be ignored or the peripheral may not respond.",
                remediation="Confirm the MCU clock tree and enable this peripheral's bus clock before configuring it.",
                snippet=lines[first_access].strip(),
            )
        )

    for index, line in enumerate(lines):
        for match in MMIO_POINTER.finditer(line):
            if "volatile" not in match.group(1) and "volatile" not in match.group(3):
                findings.append(
                    Finding(
                        line=index + 1,
                        check="volatile-mmio-pointer",
                        severity="warning",
                        risk=f"Memory-mapped pointer '{match.group(2)}' is not declared volatile, so the compiler may elide or reorder hardware accesses.",
                        remediation=f"Declare the pointed-to type volatile, for example: volatile {match.group(1)} *{match.group(2)} = (volatile {match.group(1)} *){match.group(4)};",
                        snippet=line.strip(),
                    )
                )

        if REGISTER_RMW.search(line):
            findings.append(
                Finding(
                    line=index + 1,
                    check="register-read-modify-write",
                    severity="info",
                    risk="This read-modify-write can lose concurrent updates or have side effects on write-sensitive registers; behavior depends on the MCU and interrupt usage.",
                    remediation="Check the register's write semantics and concurrency requirements. Prefer vendor-provided atomic set/clear registers or a documented critical section when appropriate.",
                    snippet=line.strip(),
                )
            )

        for match in re.finditer(r"\b(\d+)\s*<<\s*(\d+)\b", line):
            base, shift = map(int, match.groups())
            if shift >= 32 or (base == 1 and shift >= 31):
                findings.append(
                    Finding(
                        line=index + 1,
                        check="shift-width",
                        severity="warning",
                        risk=f"The constant expression shifts by {shift}; it may overflow a signed int or use a shift count outside the operand width.",
                        remediation="Use an explicitly sized unsigned constant (for example, UINT32_C(1)) and verify the shift is smaller than the destination type width.",
                        snippet=line.strip(),
                    )
                )

        priority = re.search(r"NVIC_SetPriority\s*\([^,]+,\s*(\d+)\s*\)", line)
        if priority and int(priority.group(1)) > 15:
            findings.append(
                Finding(
                    line=index + 1,
                    check="interrupt-priority-range",
                    severity="warning",
                    risk="The literal priority exceeds the common 4-bit Cortex-M priority range; CMSIS may mask it or the value may be invalid for this MCU.",
                    remediation="Check __NVIC_PRIO_BITS and the device reference manual, then clamp or validate the priority against that device's supported range.",
                    snippet=line.strip(),
                )
            )

    return findings


def render_markdown(path: Path, findings: list[Finding]) -> str:
    """Format heuristic findings into clean Markdown with summary, table, and remediated code."""
    if not findings:
        return f"# Embedded Register Audit\n\nFile: `{path}`\n\nNo heuristic findings. This is not proof of hardware correctness.\n"

    rows = [
        "# Embedded Register Audit",
        "",
        f"File: `{path}`",
        "",
        "## Executive Summary",
        f"Scanned `{path}` in offline heuristic mode. Identified {len(findings)} advisory register access hazard(s) requiring hardware review.",
        "",
        "| Line | Check | Severity | Risk | Remediation |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for finding in findings:
        values = [finding.risk, finding.remediation]
        risk, remediation = [value.replace("|", "\\|").replace("\n", " ") for value in values]
        rows.append(
            f"| {finding.line} | {finding.check} | {finding.severity} | {risk} | {remediation} |"
        )
    rows.extend(["", "## Detailed Findings & Context", ""])
    for finding in findings:
        rows.extend(
            [
                f"### Line {finding.line}: {finding.check}",
                "",
                "```c",
                finding.snippet,
                "```",
                "",
                f"Suggested action: {finding.remediation}",
                "",
            ]
        )

    rows.extend(
        [
            "## Remediated Code Snippet",
            "",
            "Below is a remediated reference pattern illustrating proper peripheral clock gating, volatile MMIO qualification, safe bitfield manipulation, and unsigned constant shifts:",
            "",
            "```c",
            "// 1. Enable peripheral bus clock before accessing peripheral registers",
            "RCC->APB1ENR |= (1U << 17); // e.g. USART2 clock enable",
            "",
            "// 2. Ensure MMIO pointers are volatile-qualified",
            "volatile USART_TypeDef *uart = (volatile USART_TypeDef *)USART2_BASE;",
            "",
            "// 3. Configure peripheral registers safely",
            "uart->BRR = UART_BAUD_RATE;",
            "",
            "// 4. Use unsigned constant shifts within type width (avoid signed overflow)",
            "uart->CR1 |= (1U << 31);",
            "```",
            "",
        ]
    )
    return "\n".join(rows)


def analyze_llm(
    source: str,
    file_path: Path,
    api_key: str,
    model: str = "gemini-3.8-flash",
) -> str:
    """Analyze source code using the Google GenAI SDK (Gemini)."""
    if not GENAI_AVAILABLE:
        raise RuntimeError("google-genai package is not installed. Install requirements.txt.")

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=20.0,
            retry_options=types.HttpRetryOptions(attempts=2, initial_delay=1.0),
        ),
    )
    prompt = (
        f"Audit the following embedded C/C++ source file ({file_path.name}):\n\n"
        f"```c\n{source}\n```"
    )
    system_instruction = SYSTEM_PROMPT.format(filename=str(file_path), model=model)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
        ),
    )
    return response.text or ""


def _should_try_fallback(error: Exception) -> bool:
    """Return whether the model error is likely transient or model-specific."""
    if "timeout" in type(error).__name__.lower():
        return True

    status = getattr(error, "status_code", getattr(error, "status", None))
    code = getattr(error, "code", None)
    if status in (404, 503) or code in (404, 503):
        return True

    details = f"{status} {code} {error}".upper()
    return any(
        marker in details
        for marker in (
            "404",
            "503",
            "NOT_FOUND",
            "UNAVAILABLE",
            "TIMEOUT",
            "TIMED OUT",
            "DEADLINE EXCEEDED",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous LLM-powered and heuristic static auditor for bare-metal C/C++ register access."
    )
    parser.add_argument("--file", required=True, type=Path, help="C/C++ source file to inspect")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="Write report to a file instead of stdout")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force local offline heuristic scan without calling Gemini API",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        help="Gemini model identifier (default: gemini-3.8-flash or GEMINI_MODEL env)",
    )
    args = parser.parse_args(argv)

    try:
        source = args.file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        parser.error(f"cannot read {args.file}: {error}")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    use_llm = bool(api_key) and not args.offline and GENAI_AVAILABLE

    if not args.offline and not api_key:
        print(
            "Note: GEMINI_API_KEY is not set. Operating in offline heuristic mode.",
            file=sys.stderr,
        )

    report_markdown = ""
    findings: list[Finding] = []
    used_model = args.model

    if use_llm:
        try:
            report_markdown = analyze_llm(
                source=source,
                file_path=args.file,
                api_key=api_key,
                model=args.model,
            )
        except Exception as error:
            if args.model != FALLBACK_MODEL and _should_try_fallback(error):
                print(
                    f"Advisory: Gemini model '{args.model}' failed ({error}). "
                    f"Retrying with '{FALLBACK_MODEL}'.",
                    file=sys.stderr,
                )
                try:
                    report_markdown = analyze_llm(
                        source=source,
                        file_path=args.file,
                        api_key=api_key,
                        model=FALLBACK_MODEL,
                    )
                    used_model = FALLBACK_MODEL
                except Exception as fallback_error:
                    print(
                        f"Warning: Gemini fallback model '{FALLBACK_MODEL}' failed "
                        f"({fallback_error}). Falling back to offline heuristic scan.",
                        file=sys.stderr,
                    )
                    use_llm = False
            else:
                print(
                    f"Warning: Gemini API call failed ({error}). "
                    "Falling back to offline heuristic scan.",
                    file=sys.stderr,
                )
                use_llm = False

    if not use_llm:
        findings = analyze(source)
        report_markdown = render_markdown(args.file, findings)

    if args.format == "json":
        if use_llm:
            data = {
                "file": str(args.file),
                "mode": "llm",
                "model": used_model,
                "report": report_markdown,
            }
        else:
            data = {
                "file": str(args.file),
                "mode": "offline-heuristic",
                "findings": [asdict(item) for item in findings],
            }
        report_output = json.dumps(data, indent=2)
    else:
        report_output = report_markdown

    if args.output:
        args.output.write_text(report_output + "\n", encoding="utf-8")
    else:
        print(report_output)

    # Return exit code 1 if findings or issues were identified, 0 otherwise
    if use_llm:
        # LLM reports with findings contain findings tables or hazard keywords
        has_issues = "Findings Table" in report_markdown and (
            "| warning |" in report_markdown.lower()
            or "| critical |" in report_markdown.lower()
            or "| info |" in report_markdown.lower()
            or "| high |" in report_markdown.lower()
            or "| medium |" in report_markdown.lower()
        )
        return 1 if has_issues else 0
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
