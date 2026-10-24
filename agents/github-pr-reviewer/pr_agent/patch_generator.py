from typing import List, Optional
from .models import FileDiff, ReviewIssue


class AutoPatchGenerator:
    """Generates standard unified git diff patches to automatically remediate detected issues."""

    @staticmethod
    def generate_remediation_patch(diffs: List[FileDiff], issues: List[ReviewIssue]) -> Optional[str]:
        """Compile an automated remediation unified diff from actionable issues."""
        patch_chunks: List[str] = []

        # Group issues by file
        issues_by_file = {}
        for issue in issues:
            if issue.suggested_replacement:
                issues_by_file.setdefault(issue.file, []).append(issue)

        if not issues_by_file:
            return None

        for filename, file_issues in issues_by_file.items():
            # Find the corresponding file diff
            file_diff = next((d for d in diffs if d.filename == filename), None)
            if not file_diff:
                continue

            hunk_lines = []
            hunk_start = 1
            if file_issues and file_issues[0].line:
                hunk_start = max(1, file_issues[0].line - 1)

            hunk_lines.append(f"--- a/{filename}")
            hunk_lines.append(f"+++ b/{filename}")
            hunk_lines.append(f"@@ -{hunk_start},5 +{hunk_start},5 @@")

            for issue in file_issues:
                # Find the original line in changed lines
                orig_line = next((cl for cl in file_diff.changed_lines if cl.line_number == issue.line), None)
                if orig_line:
                    hunk_lines.append(f"-{orig_line.content}")
                    # Split multi-line replacements if needed
                    for repl_line in issue.suggested_replacement.splitlines():
                        hunk_lines.append(f"+{repl_line}")

            if len(hunk_lines) > 3:
                header = f"diff --git a/{filename} b/{filename}"
                patch_chunks.append(header + "\n" + "\n".join(hunk_lines))

        return "\n\n".join(patch_chunks) if patch_chunks else None
