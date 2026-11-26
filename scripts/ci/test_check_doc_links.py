#!/usr/bin/env python3
"""Unit tests for check-doc-links.py (relative-link classification)."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("check-doc-links.py")
spec = importlib.util.spec_from_file_location("check_doc_links", MODULE_PATH)
check_doc_links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_doc_links)


class IsLocalTests(unittest.TestCase):
    def test_absolute_urls_are_ignored(self):
        self.assertFalse(check_doc_links.is_local("https://example.com/release"))
        self.assertFalse(check_doc_links.is_local("mailto:dev@example.com"))

    def test_relative_paths_are_local(self):
        self.assertTrue(check_doc_links.is_local("docs/guide.md"))
        self.assertTrue(check_doc_links.is_local("../README.md"))

    def test_template_placeholders_are_not_local_paths(self):
        self.assertFalse(check_doc_links.is_local("{{UPSTREAM_RELEASE_URL}}"))


class TemplateFileTests(unittest.TestCase):
    def test_mustache_link_in_a_template_is_not_reported_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "notes-template.md"
            path.write_text("See [upstream]({{UPSTREAM_RELEASE_URL}}) and [real](missing.md).\n", encoding="utf-8")
            broken = check_doc_links.check(root, [path])
            self.assertEqual([(p.name, n, t) for p, n, t in broken], [("notes-template.md", 1, "missing.md")])


if __name__ == "__main__":
    unittest.main()
