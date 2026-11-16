import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "rocky_run_counts", Path(__file__).resolve().parents[1] / "rocky-run-counts.py")
COUNTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COUNTS)

READING = {"social": "none", "danger": "none", "limit": "none", "needs": [], "question": "q"}


def body(decided="one_call", **metrics):
    return {"status": "complete", "answer": "SECRET ANSWER TEXT",
            "metrics": {"decidedBy": decided, "modelCalls": 7, "committedNusd": 1_500_000,
                        **metrics}}


def card(said=True, **more):
    return {"answerCard": {"card": "c1", "score": 0.9, "lead": 0.2, "said": said, **more}}


def read(*votes):
    return {"read": {**READING, "reads": [{**READING, **vote} for vote in votes]}}


ROWS = [
    {"id": "ht-01", "question": "SECRET QUESTION", "run": 1, "seconds": 0.4,
     "body": body("code", modelCalls=0, committedNusd=100_000, **card())},
    {"id": "ht-01", "question": "SECRET QUESTION", "run": 2, "seconds": 0.5,
     "body": body("code", modelCalls=0, committedNusd=100_000, **card())},
    {"id": "ht-02", "question": "SECRET QUESTION", "run": 1, "seconds": 9.0,
     "body": body(pageFacts={"writer": "ai", "fell_back": False}, pageFactPicks=[[1, 2], [1, 2], [1]],
                  oneCallPicks=[[1, 2, 3], [1, 2], [2, 3]], **card(False, why="not_clear"),
                  **read({}, {}, {"limit": "personal"}))},
    {"id": "ht-02", "question": "SECRET QUESTION", "run": 2, "seconds": 11.0,
     "body": body(oneCallPicks=[[1, 2], "late", None], **read({}, {}, {}))},
    {"id": "pp-01", "question": "SECRET QUESTION", "run": 1, "seconds": 3.0, "body": body("model")},
    {"id": "pp-01", "question": "SECRET QUESTION", "run": 2, "seconds": 3.0,
     "body": {"error": {"code": "timeout"}, "metrics": {"decidedBy": "error"}}},
]


def lines_of(rows, good=None):
    lines = []
    COUNTS.report(rows, good, out=lines.append)
    return "\n".join(lines)


class RunCountsTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run.json"
            path.write_text(json.dumps(data))
            return COUNTS.load(path)

    def test_each_try_is_put_on_the_path_that_wrote_it(self):
        tries = self.load(ROWS)
        self.assertEqual([COUNTS.path_of(one) for one in tries],
                         ["answer card", "answer card", "two-stage page answer",
                          "one-writer page answer", "tool loop", "failed"])

    def test_a_repeat_test_export_reads_like_rocky_rows(self):
        export = {"rows": [{"id": "ht-01", "question": "SECRET QUESTION", "tries": [
            {"seconds": row["seconds"], "raw": row["body"]} for row in ROWS[:2]]}]}
        tries = self.load(export)
        self.assertEqual([(one["id"], one["run"], COUNTS.path_of(one)) for one in tries],
                         [("ht-01", 1, "answer card"), ("ht-01", 2, "answer card")])

    def test_the_report_counts_cards_votes_and_grades(self):
        text = lines_of(self.load(ROWS), {"ht-01": True, "ht-02": False, "pp-01": True})
        self.assertIn("questions 3, tries 6, failed 1", text)
        self.assertIn("answer card: 2 of 6 (33%) tries; first tries 1; good 1 of 1 (100%)", text)
        self.assertIn("first tries said from a card (1): ht-01", text)
        self.assertIn("how-to: 2 first tries; good 1 of 2 (50%)", text)
        self.assertIn("why not: {'not_clear': 1}", text)
        # The read: one try's third vote split on the limit, and the first vote gave the decision.
        self.assertIn("all votes gave the same labels: 1 of 2 (50%)", text)
        self.assertIn("the first vote alone gave what was decided: 2 of 2 (100%)", text)
        self.assertIn("votes split on limit: 1 of 2 (50%)", text)
        # The section pick: 2 and 3... more than half of three votes chose 1, 2 and 3.
        self.assertIn("by votes back: {1: 1, 3: 1}; late votes 1, failed votes 1", text)
        self.assertIn("the first vote alone chose the decided set: 1 of 1 (100%)", text)

    def test_the_report_never_prints_a_question_or_an_answer(self):
        text = lines_of(self.load(ROWS), {"ht-01": True})
        self.assertNotIn("SECRET", text)

    def test_the_agreed_set_is_what_more_than_half_the_votes_chose(self):
        valid, kept = COUNTS.agreed([[1, 2, 3], [1, 2], None, "late", [2, 4]])
        self.assertEqual((len(valid), kept), (3, {1, 2}))


if __name__ == "__main__":
    unittest.main()
