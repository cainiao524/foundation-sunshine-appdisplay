"""Offline transaction tests: real Git history, fake release API/publication."""

from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import upstream_sync as sync
import publish_release


class UpstreamTransactionTests(unittest.TestCase):
    repository = "example/downstream"
    old_tag = "v2026.0101.杂鱼"
    new_tag = "v2026.0201.杂鱼"

    def setUp(self):
        self.previous_directory = Path.cwd()
        self.build_root = SCRIPTS.parent / "build"
        self.build_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="test-upstream-sync-", dir=self.build_root)
        self.root = Path(self.temporary.name).resolve()
        self.stack = ExitStack()
        self.addCleanup(self.cleanup)
        self.stack.enter_context(patch.dict(os.environ, {
            "GITHUB_OUTPUT": "", "GITHUB_STEP_SUMMARY": "",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }))
        self.upstream = self.root / "upstream"
        self.remote = self.root / "origin.git"
        self.work = self.root / "checkout"
        self.raw_git(self.root, "init", "--initial-branch=master", str(self.upstream))
        self.configure(self.upstream)
        (self.upstream / "shared.txt").write_text("baseline\n", encoding="utf-8")
        (self.upstream / ".github/workflows").mkdir(parents=True)
        (self.upstream / ".github/workflows/build.yml").write_text("name: Upstream original\n", encoding="utf-8")
        (self.upstream / ".github/workflows/old.yml").write_text("name: Original auxiliary job\n", encoding="utf-8")
        self.old_sha = self.commit(self.upstream, "upstream baseline")
        self.raw_git(self.upstream, "tag", self.old_tag)
        self.raw_git(self.root, "init", "--bare", str(self.remote))
        self.raw_git(self.root, "clone", "--no-hardlinks", str(self.upstream), str(self.work))
        self.configure(self.work)
        self.raw_git(self.work, "remote", "set-url", "origin", str(self.remote))
        (self.work / ".github/workflows/build.yml").write_text("name: Downstream guarded pipeline\n", encoding="utf-8")
        self.write_state(self.work, self.old_tag, self.old_sha, "v4.2")
        (self.work / "custom.txt").write_text("App Display customization\n", encoding="utf-8")
        self.base = self.commit(self.work, "downstream baseline")
        self.raw_git(self.work, "push", "origin", "master")
        self.raw_git(self.work, "tag", "v4.2")
        self.raw_git(self.work, "push", "origin", "refs/tags/v4.2")
        self.latest = self.old_tag
        self.release_metadata = {}
        self.api_calls = []
        self.publication_checks = []
        self.verification_error = None
        self.published_release = None
        self.original_command = sync.command
        self.stack.enter_context(patch.object(sync, "command", self.fake_command))
        self.stack.enter_context(patch.object(sync, "api", self.fake_api))
        self.release_lookup = self.stack.enter_context(patch.object(
            publish_release.Publisher, "inspect", side_effect=lambda: (None, self.published_release)))
        os.chdir(self.work)

    def cleanup(self):
        os.chdir(self.previous_directory)
        self.stack.close()
        if not self.root.is_relative_to(self.build_root.resolve()):
            raise AssertionError("Test cleanup escaped the workspace build directory")
        self.temporary.cleanup()

    @staticmethod
    def raw_git(directory, *args):
        result = subprocess.run(["git", *args], cwd=directory, capture_output=True,
                                text=True, encoding="utf-8", check=False)
        if result.returncode:
            raise AssertionError(f"Git fixture failed: {args}\n{result.stdout}{result.stderr}")
        return result.stdout.strip()

    def configure(self, directory):
        for name, value in (("user.name", "Transaction Test"), ("user.email", "test@example.invalid"),
                            ("commit.gpgsign", "false"), ("tag.gpgsign", "false"),
                            ("core.autocrlf", "false")):
            self.raw_git(directory, "config", name, value)

    def commit(self, directory, message):
        self.raw_git(directory, "add", ".")
        self.raw_git(directory, "commit", "-m", message)
        return self.raw_git(directory, "rev-parse", "HEAD")

    @staticmethod
    def write_state(directory, tag, sha, version, previous=None):
        state = {"schema": 1, "upstream_tag": tag, "upstream_sha": sha, "version": version}
        if previous:
            state["previous_sha"] = previous
        (directory / sync.STATE).write_text(json.dumps(state) + "\n", encoding="utf-8")
        (directory / sync.PIN).write_text(tag + "\n", encoding="utf-8")
        (directory / sync.COMMIT_PIN).write_text(sha + "\n", encoding="utf-8")

    def fake_command(self, *args, check=True):
        args = list(args)
        if args[0] == sys.executable and Path(args[1]).name == "publish_release.py":
            self.publication_checks.append(args)
            if self.verification_error:
                raise RuntimeError(self.verification_error)
            return subprocess.CompletedProcess(args, 0, "verified", "")
        if args[:2] == ["git", "fetch"]:
            url = f"https://github.com/{sync.UPSTREAM}.git"
            args = [str(self.upstream) if arg == url else arg for arg in args]
        if any(str(arg).startswith(("https://", "http://")) for arg in args):
            raise AssertionError(f"Network access attempted by offline test: {args}")
        if args[0] == "gh":
            raise AssertionError(f"Unexpected live GitHub command: {args}")
        return self.original_command(*args, check=check)

    def fake_api(self, path):
        self.api_calls.append(path)
        prefix = f"repos/{sync.UPSTREAM}/releases/"
        if not path.startswith(prefix):
            raise AssertionError(f"Unexpected API request: {path}")
        suffix = path[len(prefix):]
        tag = self.latest if suffix == "latest" else unquote(suffix.removeprefix("tags/"))
        return {"tag_name": tag, "draft": False, "prerelease": False,
                **self.release_metadata.get(tag, {})}

    def new_upstream(self, *, tag=None, file="upstream-new.txt", text="new upstream\n"):
        tag = tag or self.new_tag
        (self.upstream / file).write_text(text, encoding="utf-8")
        sha = self.commit(self.upstream, f"upstream {tag}")
        self.raw_git(self.upstream, "tag", tag)
        self.latest = tag
        return sha

    def refs(self):
        return self.raw_git(self.remote, "for-each-ref", "--format=%(refname) %(objectname)")

    def remote_sha(self, branch):
        return self.raw_git(self.remote, "rev-parse", f"refs/heads/{branch}")

    def prepare(self, check_only=False):
        output = io.StringIO()
        with redirect_stdout(output):
            sync.prepare(self.repository, check_only)
        return output.getvalue()

    def finalize(self, candidate, version="v4.3"):
        with redirect_stdout(io.StringIO()):
            sync.finalize(self.repository, candidate, self.base, version)

    def prepare_candidate(self):
        upstream_sha = self.new_upstream()
        self.prepare()
        return self.remote_sha(sync.PENDING), upstream_sha

    def advance_master(self):
        self.raw_git(self.work, "checkout", "--detach", self.base)
        (self.work / "human-change.txt").write_text("manual update\n", encoding="utf-8")
        changed = self.commit(self.work, "manual maintenance update")
        self.raw_git(self.work, "push", "origin", f"{changed}:refs/heads/master")
        return changed

    def test_no_new_release_does_not_change_refs_or_worktree(self):
        before_refs = self.refs()
        before_head = self.raw_git(self.work, "rev-parse", "HEAD")
        self.assertIn("changed=false", self.prepare())
        self.assertEqual(self.refs(), before_refs)
        self.assertEqual(self.raw_git(self.work, "rev-parse", "HEAD"), before_head)
        self.assertEqual(self.raw_git(self.work, "status", "--porcelain"), "")
        self.release_lookup.assert_not_called()

    def test_check_only_detects_new_release_without_reserving_candidate(self):
        self.new_upstream()
        before_refs = self.refs()
        self.assertIn("check only", self.prepare(check_only=True))
        self.assertEqual(self.refs(), before_refs)
        self.assertEqual(self.raw_git(self.work, "rev-parse", "HEAD"), self.base)

    def test_draft_and_prerelease_cannot_be_synchronized(self):
        self.new_upstream()
        for field in ("draft", "prerelease"):
            with self.subTest(field=field):
                self.release_metadata[self.new_tag] = {field: True}
                before_refs = self.refs()
                with self.assertRaisesRegex(ValueError, "Only published upstream stable"):
                    self.prepare()
                self.assertEqual(self.refs(), before_refs)

    def test_moved_deployed_upstream_tag_is_rejected(self):
        changed = self.new_upstream()
        self.raw_git(self.upstream, "tag", "--force", self.old_tag, changed)
        before_refs = self.refs()
        with self.assertRaisesRegex(ValueError, "Previously synchronized upstream tag has moved"):
            self.prepare()
        self.assertEqual(self.refs(), before_refs)

    def test_unrelated_upstream_history_is_rejected(self):
        self.raw_git(self.upstream, "checkout", "--orphan", "unrelated")
        self.raw_git(self.upstream, "rm", "-rf", ".")
        self.new_upstream(file="unrelated.txt")
        before_refs = self.refs()
        with self.assertRaisesRegex(ValueError, "does not advance the deployed history"):
            self.prepare()
        self.assertEqual(self.refs(), before_refs)

    def test_clean_merge_preserves_customization_and_reserves_next_free_version(self):
        self.new_upstream()
        self.raw_git(self.work, "tag", "v4.7")
        self.raw_git(self.work, "push", "origin", "refs/tags/v4.7")
        result = self.prepare()
        candidate = self.remote_sha(sync.PENDING)
        state = sync.read_state(candidate)
        self.assertEqual(state["version"], "v4.8")
        self.assertEqual(state["previous_sha"], self.base)
        self.assertEqual(sync.read_file(candidate, "custom.txt"), "App Display customization")
        self.assertEqual(sync.read_file(candidate, "upstream-new.txt"), "new upstream")
        self.assertEqual(self.remote_sha(sync.MAINTENANCE), self.base)
        self.assertTrue(sync.is_ancestor(self.base, candidate))
        self.assertIn(f"source_sha={candidate}", result)
        self.assertIn("needs_build=true", result)

    def test_merge_conflict_aborts_without_publishing_candidate(self):
        (self.work / "shared.txt").write_text("custom display logic\n", encoding="utf-8")
        self.base = self.commit(self.work, "custom conflicting change")
        self.raw_git(self.work, "push", "origin", "master")
        (self.upstream / ".github/workflows/build.yml").write_text("name: Upstream changed pipeline\n", encoding="utf-8")
        self.new_upstream(file="shared.txt", text="upstream conflicting logic\n")
        before_refs = self.refs()
        with self.assertRaisesRegex(RuntimeError, "manual resolution.*\nshared.txt"):
            self.prepare()
        self.assertEqual(self.refs(), before_refs)
        self.assertEqual(self.raw_git(self.work, "status", "--porcelain"), "")
        self.assertEqual((self.work / "shared.txt").read_text(encoding="utf-8"), "custom display logic\n")

    def test_upstream_workflow_add_modify_delete_preserves_downstream_ci(self):
        (self.upstream / ".github/workflows/build.yml").write_text("name: Upstream changed pipeline\n", encoding="utf-8")
        (self.upstream / ".github/workflows/old.yml").unlink()
        (self.upstream / ".github/workflows/new.yml").write_text("name: Newly added upstream job\n", encoding="utf-8")
        self.new_upstream()
        result = self.prepare()
        candidate = self.remote_sha(sync.PENDING)
        self.assertEqual(sync.read_file(candidate, ".github/workflows/build.yml"), "name: Downstream guarded pipeline")
        self.assertEqual(sync.read_file(candidate, ".github/workflows/old.yml"), "name: Original auxiliary job")
        workflows = self.raw_git(self.work, "ls-tree", "-r", "--name-only", candidate, ".github/workflows")
        self.assertNotIn("new.yml", workflows)
        self.assertEqual(self.raw_git(self.work, "diff", "--name-only", self.base, candidate,
                                      "--", ".github/workflows"), "")
        report = json.loads(sync.read_file(candidate, ".github/upstream-workflow-changes.json"))
        self.assertEqual(report["upstream_tag"], self.new_tag)
        self.assertEqual(set(report["files"]), {
            ".github/workflows/build.yml", ".github/workflows/old.yml", ".github/workflows/new.yml"})
        self.assertIn("Downstream CI retained", result)
        self.assertEqual(sync.read_file(candidate, "upstream-new.txt"), "new upstream")

    def test_pending_candidate_is_reused_even_when_newer_upstream_exists(self):
        candidate, _ = self.prepare_candidate()
        self.new_upstream(tag="v2026.0301.杂鱼", file="upstream-later.txt")
        self.api_calls.clear()
        before_refs = self.refs()
        result = self.prepare()
        self.assertEqual(self.refs(), before_refs)
        self.assertIn(f"source_sha={candidate}", result)
        self.assertIn("version=v4.3", result)
        self.assertFalse(any(path.endswith("/latest") for path in self.api_calls))

    def test_published_pending_candidate_skips_rebuild_but_still_needs_finalization(self):
        candidate, _ = self.prepare_candidate()
        self.published_release = {"draft": False}
        result = self.prepare()
        self.assertIn("changed=true", result)
        self.assertIn("needs_build=false", result)
        self.assertIn(f"source_sha={candidate}", result)
        self.assertEqual(self.remote_sha(sync.MAINTENANCE), self.base)

    def test_moved_pending_upstream_tag_blocks_retry(self):
        self.prepare_candidate()
        changed = self.new_upstream(tag="v2026.0301.杂鱼", file="upstream-later.txt")
        self.raw_git(self.upstream, "tag", "--force", self.new_tag, changed)
        before_refs = self.refs()
        with self.assertRaisesRegex(ValueError, "Pending upstream tag has moved"):
            self.prepare()
        self.assertEqual(self.refs(), before_refs)

    def test_pending_retry_does_not_replace_a_changed_maintenance_branch(self):
        self.prepare_candidate()
        changed = self.advance_master()
        before_refs = self.refs()
        with self.assertRaisesRegex(ValueError, "Maintenance branch changed while a candidate was pending"):
            self.prepare()
        self.assertEqual(self.refs(), before_refs)
        self.assertEqual(self.remote_sha(sync.MAINTENANCE), changed)

    def test_verified_release_promotes_exact_candidate_and_finalize_is_idempotent(self):
        candidate, _ = self.prepare_candidate()
        self.finalize(candidate)
        self.assertEqual(self.remote_sha(sync.MAINTENANCE), candidate)
        self.assertEqual(len(self.publication_checks), 1)
        self.assertIn("--verify-only", self.publication_checks[0])
        self.assertEqual(self.publication_checks[0][self.publication_checks[0].index("--commit") + 1], candidate)
        self.finalize(candidate)
        self.assertEqual(self.remote_sha(sync.MAINTENANCE), candidate)
        self.assertEqual(len(self.publication_checks), 2)
        self.assertIn("changed=false", self.prepare())

    def test_failed_asset_verification_keeps_candidate_and_can_retry(self):
        candidate, _ = self.prepare_candidate()
        before_refs = self.refs()
        self.verification_error = "asset digest mismatch"
        with self.assertRaisesRegex(RuntimeError, "asset digest mismatch"):
            self.finalize(candidate)
        self.assertEqual(self.refs(), before_refs)
        self.verification_error = None
        self.finalize(candidate)
        self.assertEqual(self.remote_sha(sync.MAINTENANCE), candidate)

    def test_changed_master_prevents_promotion_of_verified_release(self):
        candidate, _ = self.prepare_candidate()
        changed = self.advance_master()
        before_refs = self.refs()
        with self.assertRaisesRegex(ValueError, "Maintenance branch changed during the build"):
            self.finalize(candidate)
        self.assertEqual(self.refs(), before_refs)
        self.assertEqual(self.remote_sha(sync.MAINTENANCE), changed)

    def test_changed_pending_branch_prevents_verification_and_promotion(self):
        candidate, _ = self.prepare_candidate()
        (self.work / "unexpected.txt").write_text("concurrent candidate edit\n", encoding="utf-8")
        replacement = self.commit(self.work, "candidate changed concurrently")
        self.raw_git(self.work, "push", "origin", f"{replacement}:refs/heads/{sync.PENDING}")
        before_refs = self.refs()
        with self.assertRaisesRegex(ValueError, "Pending branch no longer matches"):
            self.finalize(candidate)
        self.assertEqual(self.refs(), before_refs)
        self.assertEqual(self.publication_checks, [])


if __name__ == "__main__":
    unittest.main()
