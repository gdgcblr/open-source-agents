import re
from typing import List
from ..models import FileDiff, ReviewIssue, SpecialistVerdict

PERFORMANCE_RULES = [
    (
        r"(?i)sqlite3\.connect\s*\(.*?\)(?!.*\bwith\b)",
        "Unmanaged Database Connection (Resource Leak Risk)",
        "MEDIUM",
        "Database connection opened without context manager (`with sqlite3.connect(...) as conn:`). Connection or cursor may leak on unhandled exceptions.",
        "Use context manager: `with sqlite3.connect('db.sqlite') as conn:` to ensure automatic cleanup and transaction management."
    ),
    (
        r"(?i)\bopen\s*\([^)]+\)(?!.*\bwith\b)",
        "File opened without context manager",
        "LOW",
        "File opened without `with open(...)` context manager. Risk of unclosed file descriptor leak.",
        "Wrap file I/O in context manager: `with open(filepath, 'r') as f:`."
    ),
    (
        r"(?i)async\s+def.*?time\.sleep\s*\(",
        "Synchronous blocking sleep in asynchronous function",
        "HIGH",
        "Calling `time.sleep()` blocks the entire asyncio event loop, stalling concurrent tasks.",
        "Use `await asyncio.sleep(...)` instead of blocking `time.sleep(...)`."
    ),
    (
        r"(?i)SELECT\s+\*\s+FROM\s+[a-zA-Z0-9_]+(?!\s+WHERE|\s+LIMIT)",
        "Unbounded full-table scan query",
        "MEDIUM",
        "`SELECT *` without pagination or `LIMIT` clause may exhaust server memory on growing datasets.",
        "Add pagination (`LIMIT ? OFFSET ?`) or filter by specific indexed keys."
    ),
    (
        r"(?i)print\s*\(\s*f?[\"'].*?debug",
        "Debug print statement left in production code",
        "LOW",
        "Unbuffered print statements degrade throughput and clutter server logs.",
        "Replace print statement with structured logging (`logger.debug(...)`)."
    ),
    (
        r"(?i)console\.log\s*\(",
        "JavaScript console.log in production code",
        "LOW",
        "Console logging impacts browser rendering and server-side Node.js event-loop throughput.",
        "Remove console.log before merging to production."
    ),
]


class PerformanceArchitectAgent:
    """Specialist Agent focusing on algorithmic complexity, resource leaks, and I/O efficiency."""

    def __init__(self, name: str = "Performance & Reliability Architect"):
        self.name = name

    def evaluate(self, diffs: List[FileDiff]) -> SpecialistVerdict:
        findings: List[ReviewIssue] = []

        for f in diffs:
            for cl in f.changed_lines:
                if cl.line_type != "+":
                    continue
                content = cl.content

                for pattern, title, severity, desc, fix in PERFORMANCE_RULES:
                    if re.search(pattern, content):
                        findings.append(ReviewIssue(
                            file=f.filename,
                            line=cl.line_number,
                            severity=severity,
                            category="PERFORMANCE",
                            title=title,
                            description=f"Performance review on line {cl.line_number}: {desc}",
                            suggestion=fix
                        ))

        # Calculate performance score
        score = 100
        for issue in findings:
            if issue.severity == "HIGH":
                score -= 20
            elif issue.severity == "MEDIUM":
                score -= 10
            elif issue.severity == "LOW":
                score -= 5
        score = max(0, score)

        if score < 70:
            status = "WARNING"
            summary = f"Flagged {len(findings)} performance or resource management concern(s)."
        else:
            status = "PASSED"
            summary = "Resource management and I/O patterns meet production performance standards."

        return SpecialistVerdict(
            agent_name=self.name,
            score=score,
            status=status,
            summary=summary,
            findings=findings
        )
