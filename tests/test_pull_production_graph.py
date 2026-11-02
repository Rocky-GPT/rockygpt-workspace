import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "pull_production_graph", Path(__file__).resolve().parents[1] / "pull-production-graph.py")
PULL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PULL)


def release(folder: Path, stem: str, version: str) -> None:
    """A downloaded artifact: a release file, its meaning index and the pointer naming it."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}.lbug").write_text(version)
    (folder / f"{stem}.meaning.json").write_text("{}")
    (folder / f"{stem}.meaning.f32").write_bytes(b"\0")
    (folder / "active.json").write_text(json.dumps({"file": f"{stem}.lbug", "dataset_version": version}))


class PullProductionGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "production-graph"

    def install(self, stem, version, artifact_id):
        download = self.root / f"download-{artifact_id}"
        release(download, stem, version)
        return PULL.install(download, self.target, {"id": artifact_id, "created_at": "t", "run_id": 1})

    def test_install_serves_the_new_release_and_keeps_only_the_previous_one(self):
        self.assertEqual(self.install("release-aaa", "v1", 1), "v1")
        self.install("release-bbb", "v2", 2)
        self.install("release-ccc", "v3", 3)
        pointer = json.loads((self.target / "active.json").read_text())
        self.assertEqual(pointer["file"], "release-ccc.lbug")
        names = sorted(p.name for p in self.target.iterdir() if p.name.startswith("release-"))
        self.assertEqual(names, ["release-bbb.lbug", "release-bbb.meaning.f32", "release-bbb.meaning.json",
                                 "release-ccc.lbug", "release-ccc.meaning.f32", "release-ccc.meaning.json"])
        self.assertEqual(json.loads((self.target / "artifact.json").read_text())["id"], 3)

    def test_a_pointer_naming_a_path_or_a_missing_file_is_refused(self):
        bad = self.root / "bad"
        release(bad, "release-aaa", "v1")
        (bad / "active.json").write_text(json.dumps({"file": "../etc/passwd"}))
        with self.assertRaises(PULL.PullError):
            PULL.install(bad, self.target, {"id": 1})
        (bad / "active.json").write_text(json.dumps({"file": "release-zzz.lbug"}))
        with self.assertRaises(PULL.PullError):
            PULL.install(bad, self.target, {"id": 1})
        self.assertFalse((self.target / "active.json").exists())

    def test_the_same_artifact_is_not_downloaded_again(self):
        self.install("release-aaa", "v1", 7)
        with patch.object(PULL, "latest_artifact", return_value={"id": 7, "created_at": "t", "run_id": 1}), \
                patch.object(PULL.subprocess, "run") as run:
            self.assertIn("up to date", PULL.pull(self.target))
        run.assert_not_called()

    def test_offline_keeps_an_existing_copy_and_fails_without_one(self):
        offline = patch.object(PULL, "latest_artifact", side_effect=PULL.PullError("offline"))
        with offline:
            with self.assertRaises(PULL.PullError):
                PULL.pull(self.target)
        self.install("release-aaa", "v1", 7)
        with offline:
            self.assertIn("kept the local copy", PULL.pull(self.target))

    def test_a_newer_artifact_is_downloaded_and_installed(self):
        self.install("release-aaa", "v1", 7)

        def download(args, **_):
            release(Path(args[args.index("-D") + 1]), "release-bbb", "v2")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(PULL, "latest_artifact", return_value={"id": 8, "created_at": "t2", "run_id": 5}), \
                patch.object(PULL.subprocess, "run", side_effect=download):
            self.assertIn("installed production release v2", PULL.pull(self.target))
        self.assertEqual(json.loads((self.target / "active.json").read_text())["file"], "release-bbb.lbug")


if __name__ == "__main__":
    unittest.main()
