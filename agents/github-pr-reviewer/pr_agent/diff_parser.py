import re
from typing import List, Optional
from .models import FileDiff, ChangedLine


def parse_unified_diff(diff_text: str) -> List[FileDiff]:
    """Parse standard unified git diff format into structured FileDiff objects."""
    files: List[FileDiff] = []
    
    # Split diff text into per-file chunks
    file_chunks = re.split(r"(?=diff --git )", diff_text)
    
    for chunk in file_chunks:
        chunk = chunk.strip()
        if not chunk or not chunk.startswith("diff --git"):
            continue

        lines = chunk.splitlines()
        first_line = lines[0]
        # Match "diff --git a/filename b/filename"
        match = re.match(r"diff --git a/(.*?) b/(.*)", first_line)
        if match:
            old_file, new_file = match.group(1), match.group(2)
        else:
            old_file, new_file = "unknown", "unknown"

        additions = 0
        deletions = 0
        changed_lines: List[ChangedLine] = []
        current_new_line_num: Optional[int] = None

        for line in lines:
            if line.startswith("@@"):
                # Hunk header: @@ -10,6 +10,24 @@
                hunk_match = re.search(r"\+(\d+)(?:,(\d+))?", line)
                if hunk_match:
                    current_new_line_num = int(hunk_match.group(1))
                continue

            if current_new_line_num is not None:
                if line.startswith("+") and not line.startswith("+++"):
                    additions += 1
                    changed_lines.append(ChangedLine(
                        line_number=current_new_line_num,
                        line_type="+",
                        content=line[1:]
                    ))
                    current_new_line_num += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1
                    changed_lines.append(ChangedLine(
                        line_number=None,
                        line_type="-",
                        content=line[1:]
                    ))
                elif line.startswith(" "):
                    changed_lines.append(ChangedLine(
                        line_number=current_new_line_num,
                        line_type=" ",
                        content=line[1:]
                    ))
                    current_new_line_num += 1

        files.append(FileDiff(
            filename=new_file,
            old_filename=old_file if old_file != new_file else None,
            additions=additions,
            deletions=deletions,
            patch=chunk,
            changed_lines=changed_lines
        ))

    return files
