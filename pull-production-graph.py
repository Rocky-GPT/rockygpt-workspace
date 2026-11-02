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

    python3 pull-production-graph.py DIR             download if newer, else keep DIR as it is
    python3 pull-production-graph.py DIR --force     download production's copy again and replace
    python3 pull-production-graph.py DIR --events    also print each step as a JSON line (the dev
                                                     UI's "Sync from production" button reads them)

It downloads from GitHub, never from the production database, so it costs no Neon transfer.
`./run-local.sh sync-prod` runs it; `start` does not, so the copy changes only when asked.

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
import threading
import time
from typing import Callable
import zipfile

REPOSITORY = "Rocky-GPT/rockygpt-data"
ARTIFACT = "production-graph"
POINTER = "active.json"
MARKER = "artifact.json"


class PullError(Exception):
    """Why the copy could not be refreshed."""


Emit = Callable[..., None]


def quiet(step: str, **_: object) -> None:
    """The default: no step events."""


def json_events(step: str, **fields: object) -> None:
    """One JSON line per step on stdout, flushed so a reader sees it at once."""
    print(json.dumps({"step": step, **fields}), flush=True)


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
            "run_id": newest["workflow_run"]["id"], "size_in_bytes": newest.get("size_in_bytes")}


def download_zip(artifact: dict, zip_path: Path, emit: Emit) -> None:
    """Stream the artifact's zip into zip_path, reporting the bytes received as they arrive."""
    total = artifact.get("size_in_bytes")
    with zip_path.open("wb") as out:
        process = subprocess.Popen(
            ["gh", "api", f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip"],
            stdout=out, stderr=subprocess.PIPE, text=True)
        errors: list[str] = []
        reader = threading.Thread(target=lambda: errors.append(process.stderr.read()), daemon=True)
        reader.start()
        deadline = time.monotonic() + 600
        while process.poll() is None:
            if time.monotonic() > deadline:
                process.kill()
                raise PullError("The download took longer than 10 minutes.")
            emit("downloading", received=zip_path.stat().st_size, total=total)
            time.sleep(0.5)
        reader.join(5)
    if process.returncode != 0:
        raise PullError(f"gh could not download the artifact: {''.join(errors).strip()[:200]}")
    emit("downloading", received=zip_path.stat().st_size, total=total)


def extract(zip_path: Path, folder: Path) -> None:
    """Unpack the artifact's files (flat names only) into folder."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                name = member.filename
                if member.is_dir():
                    continue
                if Path(name).name != name or name.startswith("."):
                    raise PullError(f"The artifact holds an unexpected path: {name[:80]}")
                with archive.open(member) as source, (folder / name).open("wb") as target:
                    shutil.copyfileobj(source, target)
    except zipfile.BadZipFile as error:
        raise PullError("The downloaded artifact is not a readable zip.") from error


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


def pull(target: Path, force: bool = False, emit: Emit = quiet) -> str:
    current = None
    if (target / MARKER).is_file():
        current = json.loads((target / MARKER).read_text())
    emit("checking")
    try:
        artifact = latest_artifact()
    except (PullError, OSError, subprocess.TimeoutExpired, ValueError, KeyError) as error:
        if current and (target / POINTER).is_file() and not force:
            return f"kept the local copy from {current['created_at']} ({error})"
        raise PullError(str(error)) from error
    emit("found", shared=artifact["created_at"], total=artifact.get("size_in_bytes"))
    if (not force and current and current.get("id") == artifact["id"]
            and (target / POINTER).is_file()):
        return f"up to date (production data from {artifact['created_at']})"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        folder = Path(temp) / "files"
        folder.mkdir()
        try:
            download_zip(artifact, Path(temp) / "artifact.zip", emit)
        except (PullError, OSError) as error:
            if current and (target / POINTER).is_file() and not force:
                return f"kept the local copy from {current['created_at']} (download failed)"
            raise PullError(str(error)) from error
        emit("installing")
        extract(Path(temp) / "artifact.zip", folder)
        version = install(folder, target, artifact)
    return f"installed production release {version} (shared {artifact['created_at']})"


def main(argv: list[str]) -> int:
    flags = {arg for arg in argv[1:] if arg.startswith("--")}
    paths = [arg for arg in argv[1:] if not arg.startswith("--")]
    if len(paths) != 1 or flags - {"--force", "--events"}:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: pull-production-graph.py DIR [--force] [--events]", file=sys.stderr)
        return 2
    target, force = Path(paths[0]), "--force" in flags
    emit = json_events if "--events" in flags else quiet
    if not shutil.which("gh"):
        if (target / POINTER).is_file() and not force:
            print("production data: gh is not installed; kept the local copy")
            return 0
        message = "install the gh CLI and sign in (gh auth login) to download it"
        emit("error", message=message)
        print(f"production data: {message}", file=sys.stderr)
        return 1
    try:
        message = pull(target, force, emit)
    except (PullError, OSError) as error:
        emit("error", message=str(error))
        print(f"production data: {error}", file=sys.stderr)
        return 1
    release = None
    if (target / POINTER).is_file():
        release = json.loads((target / POINTER).read_text()).get("dataset_version")
    emit("done", message=message, release=release)
    if not flags & {"--events"}:
        print(f"production data: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
