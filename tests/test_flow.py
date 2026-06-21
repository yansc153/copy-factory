from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from app import db
from app import adapters
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
            self.assertIn("app.js", review_html)

            conn.request("GET", "/api/items", headers={"Cookie": cookie})
            items_response = conn.getresponse()
            items_payload = json.loads(items_response.read().decode())
            self.assertEqual(items_response.status, 200)
            self.assertTrue(any("央行继续净投放" in item["title"] for item in items_payload["items"]))

            db_conn = db.connect(self.config.db_path)
            item_id = db_conn.execute("SELECT id FROM source_items ORDER BY id LIMIT 1").fetchone()["id"]
            db_conn.close()

            edited = "人工编辑后的花椒文案"
            save_body = json.dumps({"edited_copy": edited, "status": "approved"}, ensure_ascii=False).encode()
            conn.request("POST", f"/api/items/{item_id}/review", save_body, {"Content-Type": "application/json", "Cookie": cookie})
            saved = conn.getresponse()
            self.assertEqual(saved.status, 200)

            schedule_body = json.dumps({"scheduled_at": "2026-06-21T09:00"}, ensure_ascii=False)
            conn.request("POST", f"/api/items/{item_id}/schedule", schedule_body, {"Content-Type": "application/json", "Cookie": cookie})
            scheduled = conn.getresponse()
            self.assertEqual(scheduled.status, 200)

            db_conn = db.connect(self.config.db_path)
            row = db.get_item(db_conn, item_id)
            db_conn.close()
            self.assertEqual(row["edited_copy"], edited)
            self.assertEqual(row["review_status"], "approved")
            self.assertEqual(row["schedule_status"], "scheduled")
            self.assertEqual(row["scheduled_at"], "2026-06-21T09:00")
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

    def test_real_export_uses_health_generated_at_gate(self) -> None:
        calls = {"export": 0}
        old_health = adapters.fetch_health
        old_export = adapters.fetch_export

        def fake_health(config):
            return {"generated_at": "2026-06-20T13:27:07Z"}

        def fake_export(config, sources, limit=500):
            calls["export"] += 1
            self.assertEqual(sources, ["xueqiu", "reddit"])
            return [
                {
                    "source": "xueqiu_hot",
                    "source_id": "xq-real-1",
                    "url": "https://xueqiu.example/real/1",
                    "title": "真实快照标题",
                    "text": "真实快照正文",
                    "author": "",
                    "published_at": "2026-06-20T13:00:00Z",
                    "media_urls": ["https://xueqiu.example/img.png"],
                }
            ]

        adapters.fetch_health = fake_health
        adapters.fetch_export = fake_export
        try:
            config = Config(db_path=f"{self.tmp.name}/real.sqlite3", sources=("xueqiu", "reddit"))
            first = run_sync(config)
            second = run_sync(config)
        finally:
            adapters.fetch_health = old_health
            adapters.fetch_export = old_export

        self.assertEqual(first.inserted, 1)
        self.assertFalse(first.skipped)
        self.assertTrue(second.skipped)
        self.assertEqual(calls["export"], 1)

    def test_preview_does_not_pull_export_when_health_is_unchanged(self) -> None:
        calls = {"export": 0}
        old_health = adapters.fetch_health
        old_export = adapters.fetch_export

        def fake_health(config):
            return {"generated_at": "2026-06-20T13:27:07Z"}

        def fake_export(config, sources, limit=500):
            calls["export"] += 1
            return []

        adapters.fetch_health = fake_health
        adapters.fetch_export = fake_export
        try:
            from app.sync import preview_sync

            config = Config(db_path=f"{self.tmp.name}/preview.sqlite3", sources=("xueqiu", "reddit"))
            first = run_sync(config)
            preview = preview_sync(config)
        finally:
            adapters.fetch_health = old_health
            adapters.fetch_export = old_export

        self.assertEqual(first.inserted, 0)
        self.assertTrue(preview.skipped)
        self.assertEqual(calls["export"], 1)

    def test_real_export_filters_by_import_window_before_generation(self) -> None:
        old_health = adapters.fetch_health
        old_export = adapters.fetch_export

        def fake_health(config):
            return {"generated_at": "2026-06-20T13:27:07Z"}

        def fake_export(config, sources, limit=500):
            self.assertEqual(limit, 2)
            return [
                {
                    "source": "reddit",
                    "source_id": "old",
                    "url": "https://reddit.example/old",
                    "title": "old",
                    "text": "old",
                    "author": "",
                    "published_at": "2026-06-19T23:59:59Z",
                    "media_urls": [],
                },
                {
                    "source": "reddit",
                    "source_id": "kept",
                    "url": "https://reddit.example/kept",
                    "title": "kept",
                    "text": "kept",
                    "author": "",
                    "published_at": "2026-06-20T08:00:00Z",
                    "media_urls": [],
                },
            ]

        adapters.fetch_health = fake_health
        adapters.fetch_export = fake_export
        try:
            config = Config(
                db_path=f"{self.tmp.name}/window.sqlite3",
                sources=("reddit",),
                export_limit=2,
                import_since="2026-06-20",
                import_until="2026-06-21",
            )
            result = run_sync(config)
        finally:
            adapters.fetch_health = old_health
            adapters.fetch_export = old_export

        self.assertEqual(result.fetched, 2)
        self.assertEqual(result.filtered, 1)
        self.assertEqual(result.inserted, 1)


if __name__ == "__main__":
    unittest.main()
