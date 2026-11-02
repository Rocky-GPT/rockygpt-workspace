import importlib.machinery
import importlib.util
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("rocky", str(ROOT / "rocky"))
SPEC = importlib.util.spec_from_loader("rocky", LOADER)
ROCKY = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(ROCKY)


class Handler(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        Handler.seen.append((self.path, body))
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

    def test_prod_and_student_cannot_be_combined(self):
        result = subprocess.run([sys.executable, str(ROOT / "rocky"), "ask", "hi", "--prod", "--student"],
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
