import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "pull_production_graph", Path(__file__).resolve().parents[1] / "pull-production-graph.py")
PULL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PULL)


class PullProductionGraphTests(unittest.TestCase):
    def test_it_runs_the_brains_own_download_code_with_the_graph_sync_secrets(self):
        command = PULL.command(Path("/tmp/copy"), ["--force", "--events"])
        self.assertEqual(command[1:4], [str(PULL.ROOT / "local-env.py"), "graph-sync", "--"])
        self.assertEqual(command[5:8], ["-m", "rockygpt_brain.retrieval.graph_sync", "/tmp/copy"])
        self.assertEqual(command[-2:], ["--force", "--events"])

    def test_unknown_flags_are_refused(self):
        self.assertEqual(PULL.main(["pull", "DIR", "--everything"]), 2)
        self.assertEqual(PULL.main(["pull"]), 2)

    def test_the_child_gets_the_brain_source_on_its_path(self):
        with patch.object(PULL.Path, "is_file", return_value=True), \
                patch.object(PULL.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(PULL.main(["pull", "DIR"]), 0)
        self.assertEqual(run.call_args.kwargs["env"]["PYTHONPATH"], str(PULL.BRAIN / "src"))


if __name__ == "__main__":
    unittest.main()
