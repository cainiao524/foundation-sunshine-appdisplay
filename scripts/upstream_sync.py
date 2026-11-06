"""Prepare a stable upstream merge, then promote only its verified release.

The pending branch is a durable transaction: retries use the same source SHA and
version. The maintenance branch advances only after all published assets verify.
No third-party Python packages or long-lived credentials are required.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

UPSTREAM = "AlkaidLab/foundation-sunshine"
MAINTENANCE = "master"
PENDING = "codex/upstream-sync-pending"
STATE = ".github/upstream-sync-state.json"
PIN = ".github/upstream-stable-release"
COMMIT_PIN = ".github/upstream-stable-commit"
CI_CHANGES = ".github/upstream-workflow-changes.json"


def command(*args, check=True):
    result = subprocess.run(args, text=True, encoding="utf-8", capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed:\n{result.stdout}{result.stderr}")
    return result


def git(*args):
    return command("git", *args).stdout.strip()


def api(path):
    return json.loads(command("gh", "api", path).stdout)


def remote_head(branch):
    value = git("ls-remote", "--heads", "origin", f"refs/heads/{branch}")
    return value.split()[0] if value else None


def fetch_branch(branch):
    git("fetch", "--no-tags", "origin", f"refs/heads/{branch}")
    return git("rev-parse", "FETCH_HEAD^{commit}")


def is_ancestor(older, newer):
    result = command("git", "merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    return result.returncode == 0


def read_file(ref, path):
    return git("show", f"{ref}:{path}")


def read_state(ref):
    state = json.loads(read_file(ref, STATE))
    if (state.get("schema") != 1 or
            not re.fullmatch(r"v[0-9]+\.[0-9]+", state.get("version", "")) or
            not re.fullmatch(r"[0-9a-f]{40}", state.get("upstream_sha", ""))):
        raise ValueError("Invalid upstream sync state")
    tag = state.get("upstream_tag", "")
    git("check-ref-format", f"refs/tags/{tag}")
    if read_file(ref, PIN) != tag or read_file(ref, COMMIT_PIN) != state["upstream_sha"]:
        raise ValueError("Upstream pins disagree with sync state")
    if not is_ancestor(state["upstream_sha"], ref):
        raise ValueError("Pinned upstream commit is not contained in source history")
    return state


def upstream_release(tag=None):
    endpoint = f"tags/{quote(tag, safe='')}" if tag else "latest"
    release = api(f"repos/{UPSTREAM}/releases/{endpoint}")
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Only published upstream stable releases can be synchronized")
    tag = release["tag_name"]
    git("check-ref-format", f"refs/tags/{tag}")
    git("fetch", "--no-tags", f"https://github.com/{UPSTREAM}.git", f"refs/tags/{tag}")
    return tag, git("rev-parse", "FETCH_HEAD^{commit}")


def next_version(current, tags):
    major, minor = map(int, current[1:].split("."))
    for tag in tags:
        match = re.fullmatch(rf"v{major}\.([0-9]+)", tag)
        if match:
            minor = max(minor, int(match[1]))
    return f"v{major}.{minor + 1}"


def output(**values):
    text = "".join(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n"
                   for key, value in values.items())
    print(text, end="")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(text)


def summary(message):
    print(message)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(message + "\n")


def emit_candidate(repository, candidate, base, state):
    # The publication helper distinguishes 404 from authentication/network errors.
    from publish_release import Publisher
    _, release = Publisher(repository, state["version"], candidate).inspect()
    output(changed=True, needs_build=release is None or release["draft"],
           source_sha=candidate, base_sha=base, version=state["version"])
    summary(f"Candidate `{state['version']}`: `{candidate}`; upstream `{state['upstream_tag']}`.")


def prepare(repository, check_only=False):
    base = fetch_branch(MAINTENANCE)
    state = read_state(base)
    pending = remote_head(PENDING)
    if pending:
        pending = fetch_branch(PENDING)
        if not is_ancestor(pending, base):
            candidate_state = read_state(pending)
            if candidate_state.get("previous_sha") != base or not is_ancestor(base, pending):
                raise ValueError("Maintenance branch changed while a candidate was pending; reconcile manually")
            if git("diff", "--name-only", base, pending, "--", ".github/workflows"):
                raise ValueError("Pending candidate changes downstream workflows; review manually")
            tag, sha = upstream_release(candidate_state["upstream_tag"])
            if sha != candidate_state["upstream_sha"]:
                raise ValueError("Pending upstream tag has moved; refusing to resume")
            if check_only:
                output(changed=False)
                summary(f"Pending candidate `{candidate_state['version']}` would resume (check only).")
            else:
                emit_candidate(repository, pending, base, candidate_state)
            return

    # Detect rewritten deployed tags even when the latest release has changed.
    _, pinned_sha = upstream_release(state["upstream_tag"])
    if pinned_sha != state["upstream_sha"]:
        raise ValueError("Previously synchronized upstream tag has moved")
    tag, sha = upstream_release()
    if tag == state["upstream_tag"]:
        output(changed=False)
        summary(f"Already synchronized with upstream stable `{tag}`; no build or release needed.")
        return
    if sha == state["upstream_sha"] or not is_ancestor(state["upstream_sha"], sha):
        raise ValueError("New upstream tag does not advance the deployed history; review manually")
    if check_only:
        output(changed=False)
        summary(f"New upstream stable `{tag}` at `{sha}` is available (check only).")
        return

    remote_tags = git("ls-remote", "--tags", "--refs", "origin")
    version = next_version(state["version"], [line.split("refs/tags/", 1)[1]
                                           for line in remote_tags.splitlines()])
    git("checkout", "--detach", base)
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    upstream_ci_changes = git("diff", "--name-only", state["upstream_sha"], sha,
                              "--", ".github/workflows").splitlines()
    merged = command("git", "merge", "--no-ff", "--no-commit", sha, check=False)
    if merged.returncode not in (0, 1) or not Path(git("rev-parse", "--git-path", "MERGE_HEAD")).exists():
        command("git", "merge", "--abort", check=False)
        raise RuntimeError(f"Cannot prepare upstream merge:\n{merged.stdout}{merged.stderr}")
    # CI is downstream-owned: preserve our release gates and avoid requiring a
    # long-lived credential with workflow-edit privileges. Record upstream CI
    # changes for separate maintenance rather than silently importing them.
    git("restore", "--source", base, "--staged", "--worktree", "--", ".github/workflows")
    conflicts = git("diff", "--name-only", "--diff-filter=U")
    if conflicts:
        git("merge", "--abort")
        raise RuntimeError(f"Upstream merge requires manual resolution:\n{conflicts}")
    if git("diff", "--cached", "--name-only", base, "--", ".github/workflows"):
        git("merge", "--abort")
        raise RuntimeError("Automatic synchronization must preserve downstream workflow files")
    candidate_state = {"schema": 1, "upstream_tag": tag, "upstream_sha": sha,
                       "version": version, "previous_sha": base}
    Path(STATE).write_text(json.dumps(candidate_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(PIN).write_text(tag + "\n", encoding="utf-8")
    Path(COMMIT_PIN).write_text(sha + "\n", encoding="utf-8")
    Path(CI_CHANGES).write_text(json.dumps({"upstream_tag": tag, "files": upstream_ci_changes},
                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    git("add", STATE, PIN, COMMIT_PIN, CI_CHANGES)
    git("commit", "-m", f"Merge upstream stable {tag} for {version}")
    candidate = git("rev-parse", "HEAD")
    if remote_head(MAINTENANCE) != base:
        raise ValueError("Maintenance branch changed during preparation; retry from its new head")
    # Explicit lease prevents two operators from silently replacing a candidate.
    git("push", f"--force-with-lease=refs/heads/{PENDING}:{pending or ''}",
        "origin", f"{candidate}:refs/heads/{PENDING}")
    emit_candidate(repository, candidate, base, candidate_state)
    if upstream_ci_changes:
        summary("Downstream CI retained; upstream workflow changes for separate review: " +
                ", ".join(f"`{path}`" for path in upstream_ci_changes))


def finalize(repository, source_sha, base_sha, version):
    candidate = fetch_branch(PENDING)
    if candidate != source_sha:
        raise ValueError("Pending branch no longer matches the tested source")
    state = read_state(candidate)
    if state["version"] != version or state.get("previous_sha") != base_sha:
        raise ValueError("Candidate version or baseline does not match the build")
    if not is_ancestor(base_sha, candidate):
        raise ValueError("Candidate is not a fast-forward of the baseline")
    if git("diff", "--name-only", base_sha, candidate, "--", ".github/workflows"):
        raise ValueError("Candidate changes downstream workflows; refusing automatic promotion")
    command(sys.executable, str(Path(__file__).with_name("publish_release.py")),
            "--repository", repository, "--tag", version, "--commit", candidate, "--verify-only")
    current = remote_head(MAINTENANCE)
    if current == candidate:
        summary(f"Release `{version}` already verified and promoted.")
        return
    if current != base_sha:
        raise ValueError("Maintenance branch changed during the build; release is retained, promotion needs review")
    # Non-force push preserves any changes racing with this final check.
    git("push", "origin", f"{candidate}:refs/heads/{MAINTENANCE}")
    summary(f"Verified all release assets and promoted `{version}` (`{candidate}`) to `{MAINTENANCE}`.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "finalize"))
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY"), required=not os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--source-sha")
    parser.add_argument("--base-sha")
    parser.add_argument("--version")
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.repository, args.check_only)
    else:
        if not all((args.source_sha, args.base_sha, args.version)):
            parser.error("finalize requires --source-sha, --base-sha and --version")
        finalize(args.repository, args.source_sha, args.base_sha, args.version)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError) as error:
        print(f"::error::{error}", file=sys.stderr)
        sys.exit(1)
