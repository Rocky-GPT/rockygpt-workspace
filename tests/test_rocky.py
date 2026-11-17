import importlib.machinery
import importlib.util
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("rocky", str(ROOT / "rocky"))
SPEC = importlib.util.spec_from_loader("rocky", LOADER)
ROCKY = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(ROCKY)


class Handler(BaseHTTPRequestHandler):
    seen = []
    headers = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        Handler.seen.append((self.path, body))
        Handler.headers.append({key.lower(): value for key, value in self.headers.items()})
        payload = json.dumps({"answer": "Open 8-5.", "status": "complete",
                              "citations": [{"title": "Hours", "url": "https://www.ramapo.edu/a/"}]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class RockyTests(unittest.TestCase):
    def test_each_target_uses_its_chat_route(self):
        env = {"ROCKY_DEV_UI": "http://dev:1/", "ROCKY_STUDENT_UI": "http://student:2",
               "ROCKY_PROD_SITE": "https://site.example"}
        old = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        try:
            self.assertEqual(ROCKY.chat_url("dev"), "http://dev:1/api/brain/chat")
            self.assertEqual(ROCKY.chat_url("student"), "http://student:2/api/chat")
            self.assertEqual(ROCKY.chat_url("prod"), "https://site.example/api/chat")
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_prod_flag_asks_the_site_chat_route(self):
        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            env = os.environ | {"ROCKY_PROD_SITE": f"http://127.0.0.1:{server.server_port}"}
            Handler.seen.clear()
            result = subprocess.run([sys.executable, str(ROOT / "rocky"), "ask", "library hours?", "--prod"],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Open 8-5.", result.stdout)
            self.assertEqual(Handler.seen, [("/api/chat", {"messages": [{"role": "user", "content": "library hours?"}]})])
        finally:
            server.shutdown()

    def test_no_flag_asks_the_dev_ui(self):
        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            env = os.environ | {"ROCKY_DEV_UI": f"http://127.0.0.1:{server.server_port}"}
            Handler.seen.clear()
            for command in (["ask", "library hours?"], ["ask", "library hours?", "--writer", "ai"]):
                result = subprocess.run([sys.executable, str(ROOT / "rocky"), *command],
                                        env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Open 8-5.", result.stdout)
            self.assertEqual([path for path, _ in Handler.seen], ["/api/brain/chat", "/api/brain/chat"])
            self.assertEqual(Handler.seen[1][1]["writer"], "ai")
        finally:
            server.shutdown()

    def bulk(self, *args, set_dir=None):
        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        Handler.seen.clear()
        Handler.headers.clear()
        try:
            out = Path(set_dir) / "out.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "rocky"), "bulk", "file", *args,
                 "--brain", str(server.server_port), "--out", str(out)],
                capture_output=True, text=True, timeout=30)
            return result, (json.loads(out.read_text()) if out.exists() else None)
        finally:
            server.shutdown()

    def test_bulk_saves_every_reply_from_a_frozen_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            blob = json.dumps([{"id": "a-1", "area": "howto", "question": "library hours?"},
                               {"id": "a-2", "area": "people", "question": "who is the registrar?"}])
            (Path(folder) / "questions-frozen.json").write_text(blob)
            (Path(folder) / "questions-frozen.sha256").write_text(
                __import__("hashlib").sha256(blob.encode()).hexdigest() + "  questions-frozen.json\n")
            result, rows = self.bulk(folder, "--repeat", "2", set_dir=folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(rows), 4)
            self.assertEqual(sorted((row["id"], row["run"]) for row in rows),
                             [("a-1", 1), ("a-1", 2), ("a-2", 1), ("a-2", 2)])
            row = rows[0]
            self.assertEqual(row["body"]["status"], "complete")
            self.assertIn("answered_at", row)
            self.assertIn("seconds", row)
            self.assertTrue(all(path == "/v1/chat" for path, _ in Handler.seen))
            self.assertTrue(all(h.get("x-rockygpt-diagnostics") == "1" for h in Handler.headers))

    def test_bulk_refuses_a_changed_frozen_set(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "questions-frozen.json").write_text('[{"id": "a", "question": "q"}]')
            (Path(folder) / "questions-frozen.sha256").write_text("0" * 64 + "\n")
            result, rows = self.bulk(folder, set_dir=folder)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("changed since it was frozen", result.stderr)
            self.assertIsNone(rows)
            self.assertEqual(Handler.seen, [])

    def test_bulk_feeds_each_answer_back_in_a_conversation(self):
        with tempfile.TemporaryDirectory() as folder:
            questions = Path(folder) / "q.txt"
            questions.write_text("# a comment\nlibrary hours? || and on sunday?\n")
            result, rows = self.bulk(str(questions), set_dir=folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([row["id"] for row in rows], ["q1"])
            self.assertEqual(Handler.seen[1][1]["messages"], [
                {"role": "user", "content": "library hours?"},
                {"role": "assistant", "content": "Open 8-5."},
                {"role": "user", "content": "and on sunday?"}])

    def test_prod_and_student_cannot_be_combined(self):
        result = subprocess.run([sys.executable, str(ROOT / "rocky"), "ask", "hi", "--prod", "--student"],
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)

    def test_writer_is_sent_to_a_laptop_brain_and_refused_for_the_student_site(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "q.txt").write_text("library hours?\n")
            result, rows = self.bulk(str(Path(folder) / "q.txt"), "--writer", "ai", set_dir=folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Handler.seen[-1][1]["writer"], "ai")
            self.assertNotIn("_writer", rows[0])
        result = subprocess.run([sys.executable, str(ROOT / "rocky"), "ask", "hi", "--prod", "--writer", "ai"],
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("never takes it", result.stderr)


if __name__ == "__main__":
    unittest.main()
