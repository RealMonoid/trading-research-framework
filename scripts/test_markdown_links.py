#!/usr/bin/env python3
"""Regression tests for repository Markdown-link validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from validate_markdown_links import validate_markdown_links


class MarkdownLinkValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, relative_path: str, content: str = "") -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_accepts_files_directories_anchors_images_and_external_links(self) -> None:
        readme = self.write(
            "README.md",
            """# Start

[Guide](docs/guide.md#data-fitness)
[Folder](docs/)
![Image](assets/chart.png)
[Same page](#start)
[Website](https://example.com/missing)
[Email](mailto:owner@example.com)
""",
        )
        self.write("docs/guide.md", "# Data fitness\n")
        self.write("assets/chart.png", "synthetic image placeholder")

        self.assertEqual(validate_markdown_links(self.root, [readme]), [])

    def test_reports_missing_file_with_source_line(self) -> None:
        readme = self.write("README.md", "first line\n[Missing](docs/missing.md)\n")

        errors = validate_markdown_links(self.root, [readme])

        self.assertEqual(len(errors), 1)
        self.assertIn("README.md:2", errors[0])
        self.assertIn("docs/missing.md", errors[0])

    def test_reports_missing_markdown_anchor(self) -> None:
        readme = self.write("README.md", "[Guide](docs/guide.md#absent)\n")
        self.write("docs/guide.md", "# Present\n")

        errors = validate_markdown_links(self.root, [readme])

        self.assertEqual(len(errors), 1)
        self.assertIn("missing anchor '#absent'", errors[0])

    def test_checks_reference_definitions_and_decodes_paths(self) -> None:
        readme = self.write(
            "README.md",
            "See [the report][report].\n\n[report]: <docs/My%20Report.md#results>\n",
        )
        self.write("docs/My Report.md", "# Results\n")

        self.assertEqual(validate_markdown_links(self.root, [readme]), [])

    def test_ignores_links_inside_code_and_comments(self) -> None:
        readme = self.write(
            "README.md",
            """`[inline](missing-inline.md)`

```markdown
[fenced](missing-fenced.md)
```

<!-- [commented](missing-commented.md) -->
""",
        )

        self.assertEqual(validate_markdown_links(self.root, [readme]), [])

    def test_rejects_link_that_escapes_repository(self) -> None:
        outside = self.root.parent / "outside.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        readme = self.write("README.md", "[Outside](../outside.md)\n")

        errors = validate_markdown_links(self.root, [readme])

        self.assertEqual(len(errors), 1)
        self.assertIn("escapes the repository", errors[0])


if __name__ == "__main__":
    unittest.main()
