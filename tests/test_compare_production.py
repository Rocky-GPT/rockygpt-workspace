import importlib.util
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import threading
import unittest

SPEC = importlib.util.spec_from_file_location(
    "compare_production", Path(__file__).resolve().parents[1] / "compare-production.py")
COMPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARE)


def reply(**overrides):
    base = {"answer": "Open 8-5.", "status": "complete", "datasetVersion": "v2-1",
            "requestId": "r1", "citations": [{"url": "https://www.ramapo.edu/a/", "urls": ["https://www.ramapo.edu/a/"]}],
            "facts": {"request": {"asOf": "2026-11-02T03:00:00-05:00", "intent": "hours"},
                      "derived_facts": [{"open_now": {"state": "open", "now": "3:00 AM"}}],
                      "facts": [{"predicate": "hours", "value": "8-5"}]}}
    return base | overrides


class CompareTests(unittest.TestCase):
    def test_same_facts_at_different_moments_match(self):
        later = reply(requestId="r2", answer="It's open from 8 to 5.")
        later["facts"] = json.loads(json.dumps(later["facts"]))
        later["facts"]["request"]["asOf"] = "2026-11-02T03:00:09-05:00"
        later["facts"]["derived_facts"][0]["open_now"]["now"] = "3:01 AM"
        self.assertEqual(COMPARE.compare(reply(), later), [])

    def test_each_kind_of_gap_is_named(self):
        other = reply(status="not_found", datasetVersion="v2-0",
                      citations=[{"url": "https://www.ramapo.edu/b/"}])
        other["facts"] = {**reply()["facts"], "facts": [{"predicate": "hours", "value": "9-5"}]}
        found = COMPARE.compare(reply(), other)
        self.assertEqual(len(found), 4)
        self.assertIn("status: laptop complete, production not_found", found[0])
        self.assertIn("v2-1", found[1])
        self.assertEqual(found[2], "facts differ at facts.facts[0].value")
        self.assertIn("/a/", found[3])
        self.assertIn("/b/", found[3])

    def test_unreachable_side_is_a_difference_not_a_crash(self):
        found = COMPARE.compare(reply(), {"status": "unreachable", "_seconds": 0})
        self.assertTrue(found[0].startswith("status:"))

    def test_questions_skip_comments_and_honor_limit(self):
        path = Path(self.id().replace(".", "_") + ".txt")
        self.addCleanup(path.unlink)
        path.write_text("# note\nOne?\n\nTwo?\nThree?\n")
        self.assertEqual(COMPARE.read_questions(path, 2), ["One?", "Two?"])


class AskTests(unittest.TestCase):
    """ask() against a local fake Brain: the token goes only where it is given."""

    def setUp(self):
        seen = self.seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append((self.headers.get(COMPARE.TOKEN_HEADER), body))
                status = 200 if body["messages"][0]["content"] != "fail" else 503
                payload = json.dumps(reply() if status == 200 else {"status": "failed", "message": "down"})
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload.encode())

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def test_token_sent_only_to_the_side_that_needs_it(self):
        COMPARE.ask(self.url, "Hi?")
        COMPARE.ask(self.url, "Hi?", token="secret")
        self.assertEqual([token for token, _ in self.seen], [None, "secret"])
        self.assertEqual(self.seen[0][1], {"messages": [{"role": "user", "content": "Hi?"}]})

    def test_http_error_keeps_its_code(self):
        self.assertEqual(COMPARE.ask(self.url, "fail")["status"], "http_503")

    def test_nothing_listening_is_unreachable(self):
        self.server.shutdown()
        self.server.server_close()
        self.assertEqual(COMPARE.ask(self.url, "Hi?", timeout=2)["status"], "unreachable")


if __name__ == "__main__":
    unittest.main()
