"""Tests for README templates: section enforcement, copied examples and the diagram's place.

Run from agents/readme-drafter:  python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from readme_drafter.template import (  # noqa: E402
    DEFAULT_TEMPLATE, EXAMPLE_TODO_LINE, conform, headings, insert_diagram, is_unfilled_template,
    load_template, remove_copied_examples,
)

TEMPLATE = """# [Project Name]

> [One-sentence summary of what this project does.]

## Overview

### Problem Statement & Intended Users
- **Problem**: Explain the problem.

### Key Features
- Feature 1: Brief description of the capability.

## Installation & Setup

```bash
## not a heading, it is inside a code block
pip install -r requirements.txt
```

## Example Input & Output

### Example Input
### Example Output

## Future Improvements

- [ ] Add caching.

## License
"""


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("README_TEMPLATE", None)

    def tearDown(self):
        self.env.stop()

    def test_headings_skip_code_blocks(self):
        titles = [(h.level, h.title) for h in headings(TEMPLATE)]
        self.assertIn((2, "Installation & Setup"), titles)
        self.assertNotIn((2, "not a heading, it is inside a code block"), titles)

    def test_conform_renames_reorders_and_adds_missing_sections(self):
        draft = (
            "# demo\n> Does things.\n\n## Installation\npip install .\n\n## Overview\nIt works.\n\n"
            "### Key Features\n- Fast\n\n## Example Usage\n### Example Input\n`demo --help`\n\n## Extra Notes\nKept.\n"
        )
        result = conform(draft, TEMPLATE)
        sections = [line for line in result.splitlines() if line.startswith("## ")]
        self.assertEqual(sections, [
            "## Overview", "## Installation & Setup", "## Example Input & Output", "## Extra Notes",
            "## Future Improvements", "## License",
        ])
        self.assertTrue(result.startswith("# demo\n> Does things."))
        self.assertIn("### Problem Statement & Intended Users\n\nTODO: Add this section.", result)
        self.assertIn("### Example Output\n\nTODO: Add this section.", result)
        self.assertIn("## Future Improvements\n\nTODO: Add this section.", result)
        for kept in ("pip install .", "- Fast", "`demo --help`", "Kept."):
            self.assertIn(kept, result)

    def test_a_complete_draft_is_left_alone(self):
        draft = conform("# demo\n> x\n", TEMPLATE)
        self.assertEqual(conform(draft, TEMPLATE), draft)

    def test_copied_placeholders_become_todos(self):
        draft = (
            "# demo\n> [One-sentence summary of what this project does.]\n## Overview\n"
            "- Feature 1: Brief description of the capability.\n- Real feature\n"
        )
        result = remove_copied_examples(draft, TEMPLATE)
        self.assertNotIn("[One-sentence summary", result)
        self.assertNotIn("Feature 1:", result)
        self.assertIn("- Real feature", result)
        self.assertEqual(result.count(EXAMPLE_TODO_LINE), 2)

    def test_unfilled_template_readme_is_recognised(self):
        bundled = load_template()
        self.assertTrue(is_unfilled_template(bundled, bundled))
        self.assertFalse(is_unfilled_template("# demo\n\nA real README about demo.\n", bundled))

    def test_readme_template_env_var_picks_another_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team-template.md"
            path.write_text("# T\n## Usage\n")
            with mock.patch.dict(os.environ, {"README_TEMPLATE": str(path)}):
                self.assertEqual(load_template(), "# T\n## Usage\n")
            with mock.patch.dict(os.environ, {"README_TEMPLATE": str(Path(tmp) / "missing.md")}):
                with self.assertRaises(ValueError):
                    load_template()

    def test_bundled_template_matches_the_repository_template(self):
        repo_template = Path(__file__).resolve().parents[3] / "template" / "README.md"
        if not repo_template.is_file():
            self.skipTest("not inside the open-source-agents repository")
        self.assertEqual(headings(DEFAULT_TEMPLATE.read_text()), headings(repo_template.read_text()))

    def test_diagram_replaces_the_models_own_in_the_architecture_section(self):
        readme = "# demo\n## Architecture & Data Flow\nParts talk.\n```mermaid\ngraph TD\n  a --> b\n```\n## License\nMIT\n"
        result = insert_diagram(readme, 'graph TD\n  n0["a.py"]\n  n1["b.py"]\n  n0 --> n1')
        architecture, rest = result.split("## License")
        self.assertIn("Parts talk.", architecture)
        self.assertIn('n0["a.py"]', architecture)
        self.assertNotIn("a --> b", result)
        self.assertEqual(result.count("```mermaid"), 1)
        self.assertIn("MIT", rest)
        self.assertEqual(insert_diagram(result, 'graph TD\n  n0["a.py"]\n  n1["b.py"]\n  n0 --> n1'), result)

    def test_no_architecture_section_means_no_diagram(self):
        self.assertEqual(insert_diagram("# demo\n## Usage\nx\n", "graph TD"), "# demo\n## Usage\nx\n")


if __name__ == "__main__":
    unittest.main()
