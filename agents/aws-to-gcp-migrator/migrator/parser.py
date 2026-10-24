import re
from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class AWSResource:
    resource_type: str
    resource_name: str
    raw_block: str
    attributes: Dict[str, Any] = field(default_factory=dict)


class TerraformParser:
    """Extracts AWS Terraform resource blocks and attributes."""

    # Matches: resource "aws_resource_type" "resource_name" { ... }
    RESOURCE_PATTERN = re.compile(
        r'resource\s+"(aws_[a-zA-Z0-9_]+)"\s+"([a-zA-Z0-9_-]+)"\s*\{',
        re.MULTILINE
    )

    def parse_file(self, file_path: str) -> List[AWSResource]:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return self.parse_content(content)

    def parse_content(self, content: str) -> List[AWSResource]:
        resources = []
        matches = list(self.RESOURCE_PATTERN.finditer(content))

        for i, match in enumerate(matches):
            resource_type = match.group(1)
            resource_name = match.group(2)
            start_idx = match.start()

            # Find matching closing brace for this resource block
            brace_count = 0
            open_idx = match.end() - 1
            end_idx = len(content)

            for char_idx in range(open_idx, len(content)):
                if content[char_idx] == "{":
                    brace_count += 1
                elif content[char_idx] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = char_idx + 1
                        break

            raw_block = content[start_idx:end_idx]
            attributes = self._extract_attributes(raw_block)

            resources.append(AWSResource(
                resource_type=resource_type,
                resource_name=resource_name,
                raw_block=raw_block,
                attributes=attributes
            ))

        return resources

    def _extract_attributes(self, block: str) -> Dict[str, Any]:
        attrs = {}
        # Simple regex for key = value
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            if "=" in line:
                parts = line.split("=", 1)
                key = parts[0].strip()
                val = parts[1].strip().strip('"').strip("'")
                if key and not key.startswith("resource"):
                    attrs[key] = val
        return attrs
