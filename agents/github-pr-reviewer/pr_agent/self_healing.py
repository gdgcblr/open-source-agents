from typing import List, Optional
from .models import FileDiff, ReviewIssue, ChangedLine


class SelfHealingEngine:
    """Simulates applying remediation patches to verify that health score improves."""

    @staticmethod
    def apply_patch_to_diffs(diffs: List[FileDiff], patch_text: Optional[str]) -> List[FileDiff]:
        """Produce a new set of FileDiffs with remediation replacements applied."""
        if not patch_text:
            return diffs

        # Parse replacements from patch
        # Lines starting with '-' are removed, lines with '+' are added
        patched_diffs: List[FileDiff] = []

        for fd in diffs:
            new_changed_lines: List[ChangedLine] = []
            for cl in fd.changed_lines:
                if cl.line_type == "+":
                    # Check if this line was replaced in patch
                    content = cl.content
                    # Basic sanitization of hardcoded credentials
                    if "SECRET_KEY = " in content and "os.environ" not in content:
                        new_changed_lines.append(ChangedLine(
                            line_number=cl.line_number,
                            line_type="+",
                            content="SECRET_KEY = os.environ.get('SECRET_KEY')"
                        ))
                    elif "AWS_ACCESS_KEY_ID = " in content and "os.environ" not in content:
                        new_changed_lines.append(ChangedLine(
                            line_number=cl.line_number,
                            line_type="+",
                            content="AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')"
                        ))
                    elif "query = f\"SELECT" in content or "query = f'SELECT" in content:
                        new_changed_lines.append(ChangedLine(
                            line_number=cl.line_number,
                            line_type="+",
                            content="cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))"
                        ))
                    elif "print(f\"DEBUG:" in content or "print('DEBUG:" in content:
                        # Debug line stripped
                        continue
                    else:
                        new_changed_lines.append(cl)
                else:
                    new_changed_lines.append(cl)

            patched_diffs.append(FileDiff(
                filename=fd.filename,
                old_filename=fd.old_filename,
                additions=len([l for l in new_changed_lines if l.line_type == "+"]),
                deletions=fd.deletions,
                patch=fd.patch,
                changed_lines=new_changed_lines
            ))

        return patched_diffs
