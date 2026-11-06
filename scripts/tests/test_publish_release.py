"""Offline release state-machine tests; no GitHub or git writes are performed."""

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location("publish_release", Path(__file__).parents[1] / "publish_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
TAG = "v4.3"
COMMIT = "a" * 40
TAG_OBJECT = "b" * 40


def make_artifacts(directory):
    (directory / f"Sunshine.{TAG}.WindowsInstaller.exe").write_bytes(b"MZ installer fixture")
    with zipfile.ZipFile(directory / "Sunshine.Ds5Sidecar.x64.zip", "w") as archive:
        archive.writestr("Sunshine.Ds5Sidecar.exe", b"MZ sidecar fixture")
    sidecar = directory / "Sunshine.Ds5Sidecar.x64.zip"
    manifest = {"schema": 1, "component_version": "1.4.3", "protocol": 1,
                "target": "win-x64-self-contained", "license": "GPL-3.0-only",
                "asset_name": sidecar.name, "sha256": release.sha256(sidecar),
                "size": sidecar.stat().st_size,
                "download_url": "https://github.com/AlkaidLab/foundation-sunshine/releases/download/upstream/" + sidecar.name}
    (directory / "Sunshine.Ds5Sidecar.manifest.json").write_text(json.dumps(manifest), encoding="utf-8-sig")
    with zipfile.ZipFile(directory / f"Sunshine.{TAG}.Portable-x64.zip", "w") as archive:
        for filename in ["Sunshine/sunshine.exe", "Sunshine/assets/gui/sunshine-gui.exe",
                         "Sunshine/assets/gui/alkaidlab-plugin-stylus.dll"]:
            archive.writestr(filename, b"MZ portable fixture")
        archive.writestr("Sunshine/tools/ds5-sidecar-package.json", json.dumps(manifest))
    write_checksums(directory)


def write_checksums(directory):
    entries = [{"File": path.name, "Hash": release.sha256(path).upper(), "Size": "1.23 MB"}
               for path in sorted(directory.iterdir()) if path.suffix in (".exe", ".zip")]
    (directory / "checksums.json").write_text(json.dumps(entries), encoding="utf-8-sig")
    (directory / "SHA256SUMS.txt").write_text(
        "# Sunshine Release Package Checksums\nVerify your downloads with:\n  Get-FileHash your-file.zip\n" + "=" * 80 + "\n" +
        "\n".join(entry["Hash"].lower() + "  " + entry["File"] for entry in entries), encoding="utf-8-sig")


class FakeGitHub:
    def __init__(self):
        self.tag = None
        self.tag_objects = {}
        self.release = None
        self.files = {}
        self.calls = []
        self.mutations = []
        self.uploads = []
        self.fail_upload = None
        self.wrong_digest = None
        self.draft_by_tag_hidden = False

    def __call__(self, args, *, payload=None, missing_ok=False):
        assert isinstance(args, list)
        self.calls.append(args)
        if args[:2] == ["gh", "api"]:
            method, endpoint = args[3], args[4].removeprefix("repos/owner/repo")
            data = json.loads(payload) if payload is not None else None
            if method != "GET":
                self.mutations.append((method, endpoint))
            if endpoint.startswith("/git/ref/tags/"):
                return None if self.tag is None else json.dumps({"object": self.tag})
            if endpoint.startswith("/git/tags/"):
                return json.dumps({"object": self.tag_objects[endpoint.rsplit("/", 1)[1]]})
            if endpoint == "/git/tags" and method == "POST":
                self.tag_objects[TAG_OBJECT] = {"type": "commit", "sha": data["object"]}
                return json.dumps({"sha": TAG_OBJECT})
            if endpoint == "/git/refs" and method == "POST":
                assert self.tag is None, "never replace a tag"
                self.tag = {"type": "tag", "sha": data["sha"]}
                return "{}"
            if endpoint.startswith("/releases/tags/"):
                return None if self.release is None or (self.release["draft"] and self.draft_by_tag_hidden) else json.dumps(self.release)
            if endpoint.startswith("/releases?"):
                return json.dumps([] if self.release is None else [self.release])
            if endpoint == "/releases" and method == "POST":
                assert self.release is None
                self.release = {**data, "id": 1, "assets": [], "html_url": "https://github.com/owner/repo/releases/tag/" + TAG}
                return json.dumps(self.release)
            if endpoint == "/releases/1" and method == "PATCH":
                assert self.release["draft"], "published releases must never be changed"
                self.release.update(data)
                return json.dumps(self.release)
            raise AssertionError(args)
        if args[:3] == ["gh", "release", "upload"]:
            assert self.release["draft"], "published assets must never be changed"
            path = Path(args[4])
            self.uploads.append(path.name)
            if path.name == self.fail_upload:
                self.fail_upload = None
                raise release.ReleaseError("simulated interrupted upload")
            content = path.read_bytes()
            self.files[path.name] = content
            self.release["assets"] = [asset for asset in self.release["assets"] if asset["name"] != path.name]
            self.release["assets"].append({"name": path.name, "size": len(content), "state": "uploaded",
                                           "digest": "sha256:" + ("0" * 64 if path.name == self.wrong_digest else release.sha256(path))})
            return ""
        if args[:3] == ["gh", "release", "download"]:
            directory = Path(args[args.index("--dir") + 1])
            for name, content in self.files.items():
                (directory / name).write_bytes(content)
            return ""
        raise AssertionError(args)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        make_artifacts(self.artifacts)
        self.notes = self.root / "notes.md"
        self.notes.write_text("Release notes", encoding="utf-8")
        self.gh = FakeGitHub()
        self.publisher = release.Publisher("owner/repo", TAG, COMMIT, self.gh)

    def publish(self):
        return self.publisher.publish("App Display " + TAG, self.artifacts, self.notes)

    def test_create_annotated_tag_verify_and_publish(self):
        result = self.publish()
        self.assertFalse(result["draft"])
        self.assertEqual(self.publisher.tag_commit(), COMMIT)
        self.assertEqual(self.gh.tag["type"], "tag")
        self.assertEqual(len(self.gh.uploads), 6)
        self.assertIn(self.publisher.marker, result["body"])

    def test_nested_annotated_tag_mismatch_refused_without_mutations(self):
        self.gh.tag = {"type": "tag", "sha": TAG_OBJECT}
        self.gh.tag_objects[TAG_OBJECT] = {"type": "tag", "sha": "c" * 40}
        self.gh.tag_objects["c" * 40] = {"type": "commit", "sha": "d" * 40}
        with self.assertRaisesRegex(release.ReleaseError, "different commit"):
            self.publish()
        self.assertFalse(self.gh.mutations)
        self.assertFalse(self.gh.uploads)

    def test_same_sha_tag_only_resumes_without_recreating_tag(self):
        self.gh.tag = {"type": "commit", "sha": COMMIT}
        self.publisher.inspect()
        self.publish()
        self.assertFalse(any("/git/" in endpoint for _, endpoint in self.gh.mutations))

    def test_partial_upload_resumes_owned_hidden_draft_and_skips_good_assets(self):
        self.gh.fail_upload = sorted(release.expected_names(TAG))[2]
        self.gh.draft_by_tag_hidden = True
        with self.assertRaisesRegex(release.ReleaseError, "interrupted"):
            self.publish()
        self.assertTrue(self.gh.release["draft"])
        self.assertEqual(len(self.gh.files), 2)
        uploaded_before = set(self.gh.files)
        self.publish()
        self.assertFalse(self.gh.release["draft"])
        for filename in uploaded_before:
            self.assertEqual(self.gh.uploads.count(filename), 1)

    def test_unrelated_draft_is_not_touched(self):
        self.gh.tag = {"type": "commit", "sha": COMMIT}
        self.gh.release = {"id": 1, "tag_name": TAG, "draft": True, "body": "Human draft", "assets": []}
        with self.assertRaisesRegex(release.ReleaseError, "not owned"):
            self.publish()
        self.assertFalse(self.gh.mutations)

    def test_remote_digest_mismatch_stays_draft_and_retry_repairs(self):
        self.gh.wrong_digest = "checksums.json"
        with self.assertRaisesRegex(release.ReleaseError, "Remote asset verification failed"):
            self.publish()
        self.assertTrue(self.gh.release["draft"])
        self.gh.wrong_digest = None
        self.publish()
        self.assertEqual(self.gh.uploads.count("checksums.json"), 2)

    def test_published_rerun_uses_remote_bytes_never_local_rebuild(self):
        self.publish()
        before = copy.deepcopy(self.gh.release)
        self.gh.mutations.clear()
        self.gh.uploads.clear()
        (self.artifacts / f"Sunshine.{TAG}.WindowsInstaller.exe").write_bytes(b"different rebuilt binary")
        self.publish()
        self.assertEqual(self.gh.release, before)
        self.assertFalse(self.gh.mutations)
        self.assertFalse(self.gh.uploads)

    def test_published_missing_asset_fails_without_repair(self):
        self.publish()
        self.gh.release["assets"].pop()
        self.gh.mutations.clear()
        self.gh.uploads.clear()
        with self.assertRaisesRegex(release.ReleaseError, "incomplete"):
            self.publish()
        self.assertFalse(self.gh.mutations)
        self.assertFalse(self.gh.uploads)

    def test_published_download_corruption_fails_without_mutation(self):
        self.publish()
        self.gh.files[f"Sunshine.{TAG}.WindowsInstaller.exe"] = b"corrupted"
        self.gh.mutations.clear()
        with self.assertRaisesRegex(release.ReleaseError, "Package hashes"):
            self.publisher.verify_published()
        self.assertFalse(self.gh.mutations)

    def test_published_legacy_release_without_marker_still_requires_matching_digests(self):
        self.publish()
        self.gh.release["body"] = "Legacy release notes"
        self.publisher.verify_published()
        self.gh.release["assets"][0]["digest"] = "sha256:" + "0" * 64
        self.gh.mutations.clear()
        with self.assertRaisesRegex(release.ReleaseError, "Remote asset verification failed"):
            self.publisher.verify_published()
        self.assertFalse(self.gh.mutations)

    def test_published_remote_size_mismatch_is_rejected(self):
        self.publish()
        self.gh.release["assets"][0]["size"] += 1
        self.gh.mutations.clear()
        with self.assertRaisesRegex(release.ReleaseError, "Remote asset verification failed"):
            self.publisher.verify_published()
        self.assertFalse(self.gh.mutations)

    def test_stable_verification_refuses_prerelease_and_explicit_mode_accepts_it(self):
        result = self.publisher.publish("Preview", self.artifacts, self.notes, prerelease=True)
        self.assertTrue(result["prerelease"])
        self.gh.mutations.clear()
        with self.assertRaisesRegex(release.ReleaseError, "prerelease status"):
            self.publisher.verify_published()
        self.publisher.verify_published(expected_prerelease=True)
        self.assertFalse(self.gh.mutations)

    def test_unknown_draft_assets_are_preserved_and_block_publication(self):
        self.gh.fail_upload = sorted(release.expected_names(TAG))[0]
        with self.assertRaises(release.ReleaseError):
            self.publish()
        unexpected = {"name": "unrelated.txt", "size": 1, "digest": "sha256:" + "0" * 64, "state": "uploaded"}
        self.gh.release["assets"].append(unexpected)
        with self.assertRaisesRegex(release.ReleaseError, "unexpected assets"):
            self.publish()
        self.assertIn(unexpected, self.gh.release["assets"])
        self.assertTrue(self.gh.release["draft"])

    def test_local_bad_manifest_fails_before_tag_creation(self):
        path = self.artifacts / "Sunshine.Ds5Sidecar.manifest.json"
        value = release.read_json(path)
        value["sha256"] = "0" * 64
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(release.ReleaseError, "DualSense manifest"):
            self.publish()
        self.assertFalse(self.gh.mutations)

    def test_embedded_pin_mismatch_is_rejected_even_with_matching_checksums(self):
        path = self.artifacts / f"Sunshine.{TAG}.Portable-x64.zip"
        with zipfile.ZipFile(path, "r") as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        contents["Sunshine/tools/ds5-sidecar-package.json"] = b'{"schema":1}'
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in contents.items():
                archive.writestr(name, content)
        write_checksums(self.artifacts)
        with self.assertRaisesRegex(release.ReleaseError, "pin differs"):
            self.publish()
        self.assertFalse(self.gh.mutations)

    def test_windows_zip_member_separators_are_supported(self):
        path = self.artifacts / f"Sunshine.{TAG}.Portable-x64.zip"
        with zipfile.ZipFile(path, "r") as archive:
            contents = {name.replace("/", "\\"): archive.read(name) for name in archive.namelist()}
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in contents.items():
                archive.writestr(name, content)
        write_checksums(self.artifacts)
        self.assertFalse(self.publish()["draft"])

    def test_preflight_accepts_owned_draft_and_published_without_changing_them(self):
        self.gh.fail_upload = sorted(release.expected_names(TAG))[0]
        with self.assertRaises(release.ReleaseError):
            self.publish()
        before = len(self.gh.mutations)
        self.assertTrue(self.publisher.inspect()[1]["draft"])
        self.assertEqual(len(self.gh.mutations), before)
        self.publish()
        before = len(self.gh.mutations)
        self.assertFalse(self.publisher.inspect()[1]["draft"])
        self.assertEqual(len(self.gh.mutations), before)

    def test_command_errors_only_treat_http_404_as_missing(self):
        for stderr, absent in [("gh: Not Found (HTTP 404)", True), ("HTTP 403: forbidden", False),
                               ("network timeout", False)]:
            with self.subTest(stderr=stderr), mock.patch.object(release.subprocess, "run", return_value=
                    subprocess.CompletedProcess(["gh"], 1, "", stderr)):
                if absent:
                    self.assertIsNone(release.run_command(["gh", "api", "test"], missing_ok=True))
                else:
                    with self.assertRaises(release.ReleaseError):
                        release.run_command(["gh", "api", "test"], missing_ok=True)


if __name__ == "__main__":
    unittest.main()
