from __future__ import annotations

import http.client
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from app import db
from app.config import Config
from app.sync import run_sync
from app.web import Handler


class CopyFactoryFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(db_path=f"{self.tmp.name}/test.sqlite3", user="tester", password="secret", session_secret="test-secret")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_mock_sync_dedupes_generates_and_review_save_updates_status(self) -> None:
        first = run_sync(self.config)
        second = run_sync(self.config)
        self.assertEqual((first.inserted, first.generated, second.duplicates), (3, 3, 3))

        Handler.config = self.config
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            conn = http.client.HTTPConnection(host, port)
            body = urlencode({"user": "tester", "password": "secret"})
            conn.request("POST", "/login", body, {"Content-Type": "application/x-www-form-urlencoded"})
            login = conn.getresponse()
            cookie = login.getheader("Set-Cookie")
            self.assertEqual(login.status, 303)
            self.assertIn("copy_factory=", cookie)

            conn.request("GET", "/review", headers={"Cookie": cookie})
            review = conn.getresponse()
            review_html = review.read().decode()
            self.assertIn("今日待审核池", review_html)
            self.assertIn("央行继续净投放", review_html)

            db_conn = db.connect(self.config.db_path)
            item_id = db_conn.execute("SELECT id FROM source_items ORDER BY id LIMIT 1").fetchone()["id"]
            db_conn.close()

            edited = "人工编辑后的花椒文案"
            save_body = urlencode({"edited_copy": edited, "status": "approved"})
            conn.request("POST", f"/items/{item_id}/save", save_body, {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie})
            saved = conn.getresponse()
            self.assertEqual(saved.status, 303)

            db_conn = db.connect(self.config.db_path)
            row = db.get_item(db_conn, item_id)
            db_conn.close()
            self.assertEqual(row["edited_copy"], edited)
            self.assertEqual(row["review_status"], "approved")
        finally:
            server.shutdown()
            server.server_close()

    def test_production_requires_deepseek_key_for_generation(self) -> None:
        old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        old_key_file = os.environ.pop("DEEPSEEK_API_KEY_FILE", None)
        try:
            config = Config(db_path=f"{self.tmp.name}/prod.sqlite3", app_env="production", user="u", password="p", session_secret="s")
            result = run_sync(config)
            self.assertEqual(result.generated, 0)
            self.assertTrue(any("DEEPSEEK" in error for error in result.errors))
        finally:
            if old_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_key
            if old_key_file is not None:
                os.environ["DEEPSEEK_API_KEY_FILE"] = old_key_file


if __name__ == "__main__":
    unittest.main()
