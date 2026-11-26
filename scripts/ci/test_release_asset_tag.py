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

    def test_full_official_appdisplay_tag_drops_non_ascii_for_filenames(self):
        tag = "v2026.1123.185102.杂鱼.appdisplay"
        self.assertEqual(asset_tag(tag), "v2026.1123.185102.appdisplay")

    def test_matches_publish_release(self):
        from scripts.publish_release import asset_file_tag
        for tag in ("v2026.1123.185102.杂鱼.appdisplay", "v4.3", "v2026.1125.34136.杂鱼.appdisplay.2"):
            self.assertEqual(asset_tag(tag), asset_file_tag(tag))

    def test_the_workflow_strips_non_ascii_from_asset_names(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("LC_ALL=C sed -e 's/[^A-Za-z0-9._-]//g'", text)

    def test_legacy_and_unrelated_tags_are_kept(self):
        self.assertEqual(asset_tag("v4.3"), "v4.3")
        self.assertEqual(asset_tag("v2026.08.28-appdisplay.1"), "v2026.08.28-appdisplay.1")

    def test_the_workflow_anchors_the_short_date_pattern(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(f"[[ \"$TAG\" =~ {ANCHORED} ]]", text)
        self.assertNotIn("[[ \"$TAG\" =~ ^v([0-9]{4})\\.([0-9]+) ]]", text)


if __name__ == "__main__":
    unittest.main()
