"""Asset filename tags must keep full official versions, and only pad short dates."""

import pathlib
import unittest

from scripts.ci.release_asset_tag import asset_tag

WORKFLOW = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "main.yml"
ANCHORED = r"^v([0-9]{4})\.([0-9]+)$"


class ReleaseAssetTagTests(unittest.TestCase):
    def test_short_date_tags_are_zero_padded(self):
        self.assertEqual(asset_tag("v2026.813"), "v2026.0813")
        self.assertEqual(asset_tag("v2026.1123"), "v2026.1123")

    def test_full_official_appdisplay_tag_is_kept(self):
        tag = "v2026.1123.185102.杂鱼.appdisplay"
        self.assertEqual(asset_tag(tag), tag)

    def test_legacy_and_unrelated_tags_are_kept(self):
        self.assertEqual(asset_tag("v4.3"), "v4.3")
        self.assertEqual(asset_tag("v2026.08.28-appdisplay.1"), "v2026.08.28-appdisplay.1")

    def test_the_workflow_anchors_the_short_date_pattern(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(f"[[ \"$TAG\" =~ {ANCHORED} ]]", text)
        self.assertNotIn("[[ \"$TAG\" =~ ^v([0-9]{4})\\.([0-9]+) ]]", text)


if __name__ == "__main__":
    unittest.main()
