"""Best-effort redaction before observations leave memory."""

import re

SECRET_NAME = re.compile(r"KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL|AUTH", re.I)
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


class Redactor:
    def __init__(self, environment):
        self.secrets = sorted(
            {v for k, v in environment.items() if SECRET_NAME.search(k) and v},
            key=len,
            reverse=True,
        )

    def text(self, value):
        text = str(value)
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", text)
        text = re.sub(
            r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", text
        )
        text = re.sub(
            r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]+|"
            r"sk-[A-Za-z0-9_-]{20,})\b",
            "[REDACTED]",
            text,
        )
        return CONTROL.sub("", text)

    def object(self, value):
        if isinstance(value, dict):
            return {self.text(k): self.object(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.object(v) for v in value]
        return self.text(value) if isinstance(value, str) else value

    def log(self, data, truncated=False):
        # A truncated final line may contain only a secret prefix: discard that line.
        if truncated:
            data = data.rsplit(b"\n", 1)[0] if b"\n" in data else b""
        value = self.text(data.decode("utf-8", errors="replace"))
        return value + ("\n[output truncated]" if truncated else "")
