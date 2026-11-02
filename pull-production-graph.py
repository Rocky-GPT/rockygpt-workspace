#!/usr/bin/env python3
"""Copy production's campus data to the laptop: the very file production's Brain serves.

Each daily data run puts the active release's graph file and meaning index in the file store
(rockygpt-brain scripts/publish_graph.py, under brain-graph/ in the raw-archive bucket).
Production's Brain downloads that copy by itself; this downloads the same copy into DIR with the
same Brain code (rockygpt_brain.retrieval.graph_sync), checking every file's sha256 and renaming
active.json into place last. The copy changes only when you run this.

    python3 pull-production-graph.py DIR             download what changed, else keep DIR as it is
    python3 pull-production-graph.py DIR --force     re-check every file and install again
    python3 pull-production-graph.py DIR --events    also print each step as a JSON line (the dev
                                                     UI's "Sync from production" button reads them)

It reads the file store, never the production database, so it costs no Neon transfer. The store
settings come from rockygpt-infra's manifest and the keys from 1Password, through local-env.py
(service `graph-sync`). `./run-local.sh sync-prod` runs it; `start` does not.
"""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BRAIN = ROOT / "rockygpt-brain"


def command(target: Path, flags: list[str]) -> list[str]:
    python = str(BRAIN / ".venv" / "bin" / "python")
    return [python, str(ROOT / "local-env.py"), "graph-sync", "--",
            python, "-m", "rockygpt_brain.retrieval.graph_sync", str(target.resolve()), *flags]


def main(argv: list[str]) -> int:
    flags = [arg for arg in argv[1:] if arg.startswith("--")]
    paths = [arg for arg in argv[1:] if not arg.startswith("--")]
    if len(paths) != 1 or set(flags) - {"--force", "--events"}:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: pull-production-graph.py DIR [--force] [--events]", file=sys.stderr)
        return 2
    if not (BRAIN / ".venv" / "bin" / "python").is_file():
        print("production data: rockygpt-brain/.venv is missing; run ./run-local.sh start once",
              file=sys.stderr)
        return 1
    environment = dict(os.environ, PYTHONPATH=str(BRAIN / "src"))
    return subprocess.run(command(Path(paths[0]), flags), env=environment).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
