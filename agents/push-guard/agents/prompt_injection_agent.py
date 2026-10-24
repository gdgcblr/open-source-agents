import os
import re
import json
from google import genai
from models import Finding, Severity

_INJECTION_INDICATORS = [
    (r'(?i)"role"\s*:\s*"system"', "System Message in Code"),
    (r"(?i)system[_\s\-]?prompt\s*[:=]", "System Prompt Assignment"),
    (r"(?i)SystemMessage\s*\(", "LangChain SystemMessage"),
    (r"(?i)HumanMessage\s*\(", "LangChain HumanMessage"),
    (r"(?i)messages\s*=\s*\[", "Hardcoded Message List"),
    (r"(?i)\.system\s*\(", "System Role Call"),
    (r"(?i)SYSTEM_PROMPT\s*[:=]", "Hardcoded System Prompt"),
    (r"(?i)system_message\s*[:=]", "System Message Assignment"),
    (r"(?i)ignore\s+(previous|all|above|prior)\s+instructions", "Prompt Injection Payload"),
    (r"(?i)you\s+are\s+(now\s+)?a(n)?\s+\w", "Role Override"),
    (r"(?i)\bDAN\b", "DAN Jailbreak"),
    (r"(?i)jailbreak", "Jailbreak Attempt"),
    (r"(?i)override\s+(safety|guidelines|rules|restrictions)", "Safety Override"),
    (r"(?i)disregard\s+(your|all|any)\s+", "Instruction Disregard"),
    (r"(?i)act\s+as\s+(if\s+)?\w", "Act As Injection"),
    (r"(?i)\[INST\]", "Instruction Tag"),
    (r"(?i)<\|system\|>", "System Token"),
    (r"(?i)chat_template\s*[:=]", "Chat Template Assignment"),
    (r"(?i)prompt_template\s*[:=]", "Prompt Template Assignment"),
]
_COMPILED = [(re.compile(p), label) for p, label in _INJECTION_INDICATORS]

_ATTACK_PATTERNS = {
    "Prompt Injection Payload", "Role Override", "DAN Jailbreak",
    "Jailbreak Attempt", "Safety Override", "Instruction Disregard", "Act As Injection"
}


def run(diff: str) -> list[Finding]:
    hits: list[tuple[str, str, str]] = []  # (line_ref, content, label)

    for i, line in enumerate(diff.splitlines(), 1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        content = line[1:].strip()
        for pattern, label in _COMPILED:
            if pattern.search(line):
                hits.append((f"line {i}", content, label))
                break

    if not hits:
        return []

    # Rule-based: attack patterns are HIGH/CRITICAL without needing Gemini
    findings = []
    for line_ref, content, label in hits:
        if label in _ATTACK_PATTERNS:
            findings.append(Finding(
                agent="PromptInjectionAgent",
                severity=Severity.HIGH,
                title=label,
                description=f"Potential prompt injection payload committed to repository. Content: `{content[:120]}`",
                line_ref=line_ref,
                confidence=0.85,
            ))

    # LLM-based: ask Gemini to assess the rest (system prompts, templates)
    llm_hits = [(ref, c, lbl) for ref, c, lbl in hits if lbl not in _ATTACK_PATTERNS]
    if llm_hits:
        try:
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            lines_text = "\n".join(f"[{ref}] ({lbl}) {c}" for ref, c, lbl in llm_hits)
            prompt = f"""You are an LLM security auditor. These lines from a git diff contain system prompts, message templates, or LLM configurations committed to a repository.

{lines_text}

Committing system prompts and LLM configs to a repo is a real security concern because it:
- Exposes business logic and model behaviour to anyone with repo access
- Creates a permanent record that's hard to rotate if the prompt is sensitive
- Can reveal the AI's guardrails, making it easier to bypass them

For each line, respond with a JSON array:
{{
  "line_ref": "<ref>",
  "severity": "HIGH|MEDIUM|LOW",
  "title": "<short title>",
  "description": "<one sentence: what is exposed and why it matters>",
  "confidence": 0.5-0.95
}}

Classify ALL entries — every system prompt committed to code is at minimum LOW severity.
"""
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            results = json.loads(raw)
            for r in results:
                findings.append(Finding(
                    agent="PromptInjectionAgent",
                    severity=Severity(r.get("severity", "MEDIUM")),
                    title=r.get("title", "LLM Config Exposure"),
                    description=r.get("description", ""),
                    line_ref=r.get("line_ref"),
                    confidence=float(r.get("confidence", 0.7)),
                ))
        except Exception:
            # Fallback: create MEDIUM findings without Gemini
            for line_ref, content, label in llm_hits:
                findings.append(Finding(
                    agent="PromptInjectionAgent",
                    severity=Severity.MEDIUM,
                    title=f"{label} in Repository",
                    description=f"LLM configuration committed to repository exposes model behaviour. Content: `{content[:120]}`",
                    line_ref=line_ref,
                    confidence=0.7,
                ))

    return findings
