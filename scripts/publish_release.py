#!/usr/bin/env python3
"""Publish one tested commit through a resumable draft; published assets are immutable.

Requires gh authenticated through GH_TOKEN/GITHUB_TOKEN with contents:write.
The caller must serialize publications for a repository/tag (Actions concurrency).
All mutations use GitHub's API; no local git identity or working-tree writes occur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


class ReleaseError(RuntimeError):
    pass


def run_command(args: list[str], *, payload: str | None = None, missing_ok=False):
    result = subprocess.run(args, input=payload, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        # Authentication/network failures must never be mistaken for an absent tag.
        if missing_ok and re.search(r"\bHTTP 404\b", result.stderr):
            return None
        raise ReleaseError(f"{args[0]} command failed: {result.stderr.strip()}")
    return result.stdout


def expected_names(tag: str) -> set[str]:
    return {f"Sunshine.{tag}.WindowsInstaller.exe", f"Sunshine.{tag}.Portable-x64.zip",
            "Sunshine.Ds5Sidecar.x64.zip", "Sunshine.Ds5Sidecar.manifest.json",
            "SHA256SUMS.txt", "checksums.json"}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_files(directory: Path, tag: str) -> dict[str, tuple[int, str]]:
    """Check all packages against both checksum manifests and their embedded pin."""
    names = expected_names(tag)
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != names or any(
            entry.is_symlink() or not entry.is_file() for entry in entries):
        raise ReleaseError("Release directory must contain exactly the six expected files.")
    actual = {name: ((directory / name).stat().st_size, sha256(directory / name)) for name in names}
    if any(size <= 0 for size, _ in actual.values()):
        raise ReleaseError("Release assets must not be empty.")
    package_names = {name for name in names if name.endswith((".exe", ".zip"))}
    checksums = read_json(directory / "checksums.json")
    if not isinstance(checksums, list):
        raise ReleaseError("checksums.json must contain a package list.")
    json_hashes = {}
    for entry in checksums:
        if (not isinstance(entry, dict) or not isinstance(entry.get("File"), str)
                or not isinstance(entry.get("Hash"), str)):
            raise ReleaseError("Malformed entry in checksums.json.")
        name, digest = entry["File"], entry["Hash"].lower()
        if name in json_hashes:
            raise ReleaseError("Duplicate entry in checksums.json.")
        json_hashes[name] = digest
    text_hashes = {}
    for digest, name in re.findall(r"^([0-9a-fA-F]{64})[ \t]+(.+)$",
                                  (directory / "SHA256SUMS.txt").read_text(encoding="utf-8-sig"),
                                  re.MULTILINE):
        if name in text_hashes:
            raise ReleaseError("Duplicate entry in SHA256SUMS.txt.")
        text_hashes[name] = digest.lower()
    wanted = {name: actual[name][1] for name in package_names}
    if json_hashes != wanted or text_hashes != wanted:
        raise ReleaseError("Package hashes do not match both checksum files.")
    manifest = read_json(directory / "Sunshine.Ds5Sidecar.manifest.json")
    sidecar = "Sunshine.Ds5Sidecar.x64.zip"
    if (not isinstance(manifest, dict) or manifest.get("schema") != 1
            or type(manifest.get("protocol")) is not int or manifest["protocol"] <= 0
            or manifest.get("target") != "win-x64-self-contained"
            or manifest.get("license") != "GPL-3.0-only"
            or not isinstance(manifest.get("component_version"), str)
            or not manifest["component_version"]
            or manifest.get("asset_name") != sidecar
            or not isinstance(manifest.get("download_url"), str)
            or not re.fullmatch(r"https://github\.com/AlkaidLab/foundation-sunshine/releases/download/[^/]+/Sunshine\.Ds5Sidecar\.x64\.zip", manifest["download_url"])
            or manifest.get("size") != actual[sidecar][0]
            or manifest.get("sha256") != actual[sidecar][1]):
        raise ReleaseError("DualSense manifest does not match the component package.")
    for name in package_names:
        if not name.endswith(".zip"):
            continue
        with zipfile.ZipFile(directory / name) as archive:
            if archive.testzip() is not None:
                raise ReleaseError(f"Corrupt ZIP: {name}")
            if name.endswith(".Portable-x64.zip"):
                members = {member.filename.replace("\\", "/"): member for member in archive.infolist()}
                required = ["Sunshine/sunshine.exe", "Sunshine/assets/gui/sunshine-gui.exe",
                            "Sunshine/assets/gui/alkaidlab-plugin-stylus.dll"]
                if any(member not in members or members[member].file_size == 0 for member in required):
                    raise ReleaseError("Portable package lacks a required binary.")
                embedded = json.loads(archive.read(members["Sunshine/tools/ds5-sidecar-package.json"]).decode("utf-8-sig"))
                if embedded != manifest:
                    raise ReleaseError("Portable package's DualSense pin differs from the release manifest.")
    return actual


class Publisher:
    def __init__(self, repository: str, tag: str, commit: str, runner=run_command):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ReleaseError("Expected repository in owner/name form.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", tag) or ".." in tag or tag.endswith((".", ".lock")):
            raise ReleaseError("Expected a safe downstream version tag.")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ReleaseError("Expected a full lowercase commit SHA.")
        self.repository, self.tag, self.commit, self.run = repository, tag, commit, runner
        self.base = f"repos/{repository}"
        self.marker = "<!-- sunshine-appdisplay-release " + json.dumps(
            {"schema": 1, "tag": tag, "commit": commit}, separators=(",", ":")) + " -->"

    def api(self, path: str, method="GET", data=None, missing_ok=False):
        args = ["gh", "api", "--method", method, path]
        if data is not None:
            args += ["--input", "-"]
        output = self.run(args, payload=None if data is None else json.dumps(data), missing_ok=missing_ok)
        return None if output is None else json.loads(output) if output.strip() else None

    def tag_commit(self):
        ref = self.api(f"{self.base}/git/ref/tags/{quote(self.tag, safe='')}", missing_ok=True)
        if ref is None:
            return None
        obj = ref["object"]
        seen = set()
        while obj["type"] == "tag":
            if obj["sha"] in seen or len(seen) >= 8:
                raise ReleaseError("Invalid annotated tag chain.")
            seen.add(obj["sha"])
            obj = self.api(f"{self.base}/git/tags/{obj['sha']}")["object"]
        if obj["type"] != "commit":
            raise ReleaseError("Release tag must refer to a commit.")
        return obj["sha"]

    def get_release(self):
        release = self.api(f"{self.base}/releases/tags/{quote(self.tag, safe='')}", missing_ok=True)
        if release is not None:
            return release
        # GitHub's by-tag endpoint can omit unpublished drafts; list authenticated releases.
        page = 1
        while True:
            releases = self.api(f"{self.base}/releases?per_page=100&page={page}")
            matches = [item for item in releases if item["tag_name"] == self.tag]
            if len(matches) > 1:
                raise ReleaseError("Multiple releases use this tag.")
            if matches:
                return matches[0]
            if len(releases) < 100:
                return None
            page += 1

    def inspect(self):
        tagged_commit = self.tag_commit()
        if tagged_commit is not None and tagged_commit != self.commit:
            raise ReleaseError("Existing release tag points to a different commit; refusing to move it.")
        release = self.get_release()
        if release is not None:
            if tagged_commit is None or release["tag_name"] != self.tag:
                raise ReleaseError("Existing release is not bound to the expected tag.")
            if release["draft"] and self.marker not in (release.get("body") or "").splitlines():
                raise ReleaseError("Existing draft is not owned by this publication.")
        return tagged_commit, release

    def ensure_tag(self):
        existing = self.tag_commit()
        if existing is not None:
            if existing != self.commit:
                raise ReleaseError("Release tag changed to another commit.")
            return
        tag_object = self.api(f"{self.base}/git/tags", "POST", {
            "tag": self.tag, "message": f"Release {self.tag}", "object": self.commit, "type": "commit",
            "tagger": {"name": "github-actions[bot]", "email": "41898282+github-actions[bot]@users.noreply.github.com",
                       "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}})
        try:
            self.api(f"{self.base}/git/refs", "POST", {"ref": f"refs/tags/{self.tag}", "sha": tag_object["sha"]})
        except ReleaseError:
            if self.tag_commit() != self.commit:
                raise

    def verify_metadata(self, release, actual):
        assets = release["assets"]
        if len(assets) != len(actual) or {asset["name"] for asset in assets} != set(actual):
            raise ReleaseError("Remote release must contain exactly the six expected assets.")
        for asset in assets:
            size, digest = actual[asset["name"]]
            if (asset.get("state") != "uploaded" or asset.get("size") != size
                    or asset.get("digest") != f"sha256:{digest}"):
                raise ReleaseError(f"Remote asset verification failed: {asset['name']}")

    def verify_published(self, expected_prerelease=False):
        _, release = self.inspect()
        if release is None or release["draft"]:
            raise ReleaseError("Expected a published release.")
        if release["prerelease"] != expected_prerelease:
            raise ReleaseError("Published release has the wrong prerelease status.")
        if len(release["assets"]) != 6 or {a["name"] for a in release["assets"]} != expected_names(self.tag):
            raise ReleaseError("Published release is incomplete; it will not be modified automatically.")
        with tempfile.TemporaryDirectory(prefix="sunshine-release-verify-") as temporary:
            self.run(["gh", "release", "download", self.tag, "--repo", self.repository, "--dir", temporary])
            actual = verify_files(Path(temporary), self.tag)
            _, current = self.inspect()
            if (current is None or current["draft"] or current["id"] != release["id"]
                    or current["prerelease"] != expected_prerelease):
                raise ReleaseError("Release changed during verification.")
            self.verify_metadata(current, actual)
        return current

    def publish(self, name: str, artifacts: Path, notes: Path, prerelease=False):
        _, release = self.inspect()
        if release is not None and not release["draft"]:
            # Rebuilt binaries need not be byte-identical. Verify the published files themselves.
            return self.verify_published(prerelease)
        actual = verify_files(artifacts, self.tag)
        body = self.marker + "\n\n" + notes.read_text(encoding="utf-8-sig")
        self.ensure_tag()
        _, release = self.inspect()
        if release is not None and not release["draft"]:
            return self.verify_published(prerelease)
        metadata = {"name": name, "body": body, "prerelease": prerelease}
        if release is None:
            release = self.api(f"{self.base}/releases", "POST", {
                **metadata, "tag_name": self.tag, "target_commitish": self.commit, "draft": True})
        else:
            release = self.api(f"{self.base}/releases/{release['id']}", "PATCH", metadata)
        release_id = release["id"]
        for filename in sorted(actual):
            _, current = self.inspect()
            if current is None or current["id"] != release_id:
                raise ReleaseError("Draft changed during upload.")
            if not current["draft"]:
                return self.verify_published(prerelease)
            if any(asset["name"] not in actual for asset in current["assets"]):
                raise ReleaseError("Owned draft contains unexpected assets; refusing to remove them.")
            matching = [asset for asset in current["assets"] if asset["name"] == filename]
            if len(matching) > 1:
                raise ReleaseError("Draft has duplicate asset names.")
            if (matching and matching[0].get("digest") == "sha256:" + actual[filename][1]
                    and matching[0].get("size") == actual[filename][0]
                    and matching[0].get("state") == "uploaded"):
                continue
            self.run(["gh", "release", "upload", self.tag, str(artifacts / filename),
                      "--repo", self.repository, "--clobber"])
        _, release = self.inspect()
        if release is None or release["id"] != release_id:
            raise ReleaseError("Draft changed before publication.")
        if not release["draft"]:
            return self.verify_published(prerelease)
        self.verify_metadata(release, actual)
        self.api(f"{self.base}/releases/{release_id}", "PATCH", {
            "draft": False, "make_latest": "false" if prerelease else "true"})
        return self.verify_published(prerelease)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check-only", action="store_true")
    modes.add_argument("--verify-only", action="store_true")
    parser.add_argument("--name")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--prerelease", action="store_true")
    args = parser.parse_args()
    publisher = Publisher(args.repository, args.tag, args.commit)
    if args.check_only:
        _, release = publisher.inspect()
        print(json.dumps({"tag": args.tag, "commit": args.commit,
                          "state": "missing" if release is None else "draft" if release["draft"] else "published"}))
        return
    if args.verify_only:
        release = publisher.verify_published(args.prerelease)
    else:
        if not all((args.name, args.artifacts, args.notes)):
            parser.error("publication requires --name, --artifacts and --notes")
        release = publisher.publish(args.name, args.artifacts, args.notes, args.prerelease)
    print(json.dumps({"tag": args.tag, "commit": args.commit, "state": "published",
                      "url": release["html_url"], "prerelease": release["prerelease"],
                      "assets": len(release["assets"])}))


if __name__ == "__main__":
    try:
        main()
    except (ReleaseError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise SystemExit(f"Release verification/publication failed: {error}") from error
