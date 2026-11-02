#!/usr/bin/env python3
"""Keep a one-way copy of production's campus data for the local Brain.

Production is the truth. Each daily data run uploads the release it serves as the
`production-graph` artifact (rockygpt-data daily-data-update.yml): the release graph file, its
meaning index and `active.json`. This downloads that artifact when it is newer than the local
copy and installs it into one directory that a graph-only Brain serves (BRAIN_GRAPH_ONLY_DIR).
The local copy is never edited: the next newer artifact replaces it. Real data changes go
through the data repository's code.

The release files go in first and `active.json` is renamed into place last, so a running Brain
sees either the old release or the whole new one. The previous release's files are kept until
the next install, because a running Brain may still be reading them.

    python3 pull-production-graph.py DIR        download if newer, else keep DIR as it is

Uses the `gh` CLI, signed in as someone who can read Rocky-GPT/rockygpt-data's Actions. When the
download fails (offline, signed out) and DIR already holds a copy, that copy is used.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPOSITORY = "Rocky-GPT/rockygpt-data"
ARTIFACT = "production-graph"
POINTER = "active.json"
MARKER = "artifact.json"


class PullError(Exception):
    """Why the copy could not be refreshed."""


def latest_artifact() -> dict:
    """The newest unexpired production-graph artifact, from the GitHub API."""
    result = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/actions/artifacts?name={ARTIFACT}&per_page=10"],
        capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise PullError(f"gh could not list the {ARTIFACT} artifacts: {result.stderr.strip()[:200]}")
    artifacts = [a for a in json.loads(result.stdout).get("artifacts", []) if not a.get("expired")]
    if not artifacts:
        raise PullError(f"No unexpired {ARTIFACT} artifact: the daily data run has not shared one yet.")
    newest = max(artifacts, key=lambda a: a["created_at"])
    return {"id": newest["id"], "created_at": newest["created_at"],
            "run_id": newest["workflow_run"]["id"]}


def release_stem(pointer: dict) -> str:
    name = pointer["file"]
    if not isinstance(name, str) or Path(name).name != name or not name.startswith("release-"):
        raise PullError("The downloaded active.json does not name a release file.")
    return Path(name).stem


def install(download: Path, target: Path, artifact: dict) -> str:
    """Move a downloaded artifact's release into target; returns the release it serves."""
    pointer = json.loads((download / POINTER).read_text())
    stem = release_stem(pointer)
    if not (download / pointer["file"]).is_file():
        raise PullError(f"The artifact has no {pointer['file']}.")
    target.mkdir(parents=True, exist_ok=True)
    previous = None
    if (target / POINTER).is_file():
        previous = release_stem(json.loads((target / POINTER).read_text()))
    for item in download.iterdir():
        if item.name != POINTER and item.name.startswith(stem):
            os.replace(item, target / item.name)
    temp = target / f"{POINTER}.tmp"
    temp.write_text(json.dumps(pointer, indent=2) + "\n")
    os.replace(temp, target / POINTER)
    (target / MARKER).write_text(json.dumps(artifact, indent=2) + "\n")
    keep = {stem, previous}
    for item in target.iterdir():
        if item.name.startswith("release-") and not any(k and item.name.startswith(k) for k in keep):
            item.unlink()
    return pointer.get("dataset_version", stem)


def pull(target: Path) -> str:
    current = None
    if (target / MARKER).is_file():
        current = json.loads((target / MARKER).read_text())
    try:
        artifact = latest_artifact()
    except (PullError, OSError, subprocess.TimeoutExpired, ValueError, KeyError) as error:
        if current and (target / POINTER).is_file():
            return f"kept the local copy from {current['created_at']} ({error})"
        raise PullError(str(error)) from error
    if current and current.get("id") == artifact["id"] and (target / POINTER).is_file():
        return f"up to date (production data from {artifact['created_at']})"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        result = subprocess.run(
            ["gh", "run", "download", str(artifact["run_id"]), "-R", REPOSITORY,
             "-n", ARTIFACT, "-D", temp], capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            if current and (target / POINTER).is_file():
                return f"kept the local copy from {current['created_at']} (download failed)"
            raise PullError(f"gh could not download the artifact: {result.stderr.strip()[:200]}")
        version = install(Path(temp), target, artifact)
    return f"installed production release {version} (shared {artifact['created_at']})"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: pull-production-graph.py DIR", file=sys.stderr)
        return 2
    if not shutil.which("gh"):
        target = Path(argv[1])
        if (target / POINTER).is_file():
            print("production data: gh is not installed; kept the local copy")
            return 0
        print("production data: install the gh CLI and sign in (gh auth login) to download it",
              file=sys.stderr)
        return 1
    try:
        print(f"production data: {pull(Path(argv[1]))}")
    except PullError as error:
        print(f"production data: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
