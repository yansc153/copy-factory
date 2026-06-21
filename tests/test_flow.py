from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from app import db
from app import adapters
from app import writer
from app.config import Config
from app.sync import run_sync
from app.web import Handler


class CopyFactoryFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(
            db_path=f"{self.tmp.name}/test.sqlite3",
            user="tester",
            password="secret",
            session_secret="test-secret",
            publish_token="worker-secret",
        )

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
            item_ids = [row["id"] for row in db_conn.execute("SELECT id FROM source_items ORDER BY id LIMIT 3")]
            db_conn.close()

            edited = "人工编辑后的花椒文案"
            for offset, item_id in enumerate(item_ids):
                save_body = json.dumps({"edited_copy": f"{edited} {offset}", "status": "approved"}, ensure_ascii=False).encode()
                conn.request("POST", f"/api/items/{item_id}/review", save_body, {"Content-Type": "application/json", "Cookie": cookie})
                saved = conn.getresponse()
                self.assertEqual(saved.status, 200)
                saved.read()

                scheduled_at = f"2000-01-01T00:0{offset}:00.000Z" if offset < 2 else "2999-01-01T00:00:00.000Z"
                schedule_body = json.dumps({"scheduled_at": scheduled_at}, ensure_ascii=False)
                conn.request("POST", f"/api/items/{item_id}/schedule", schedule_body, {"Content-Type": "application/json", "Cookie": cookie})
                scheduled = conn.getresponse()
                self.assertEqual(scheduled.status, 200)
                scheduled.read()

            conn.request("POST", "/api/publish/confirm_plan", b"{}", {"Content-Type": "application/json", "Cookie": cookie})
            confirmed = conn.getresponse()
            confirmed_payload = json.loads(confirmed.read().decode())
            self.assertEqual(confirmed.status, 200)
            self.assertEqual(confirmed_payload["confirmed"], 3)

            conn.request("GET", "/api/publish/queue", headers={"Cookie": cookie})
            queue = conn.getresponse()
            queue_payload = json.loads(queue.read().decode())
            self.assertEqual(queue.status, 200)
            self.assertEqual([task["status"] for task in queue_payload["tasks"]], ["confirmed", "confirmed", "confirmed"])

            worker_headers = {"Content-Type": "application/json", "Authorization": "Bearer worker-secret"}
            claim_body = json.dumps({"now": "9999-12-31T23:59:59Z", "limit": 1}).encode()
            conn.request("POST", "/api/publish/claim_due", claim_body, worker_headers)
            claimed = conn.getresponse()
            claimed_payload = json.loads(claimed.read().decode())
            self.assertEqual(claimed.status, 200)
            self.assertEqual(len(claimed_payload["tasks"]), 1)
            self.assertIn("claim_token", claimed_payload["tasks"][0])

            first_task = claimed_payload["tasks"][0]
            result_body = json.dumps(
                {"item_id": first_task["item_id"], "claim_token": first_task["claim_token"], "status": "published"}
            ).encode()
            conn.request("POST", "/api/publish/result", result_body, worker_headers)
            published = conn.getresponse()
            self.assertEqual(published.status, 200)
            self.assertEqual(json.loads(published.read().decode())["item"]["status"], "published")

            reschedule_body = json.dumps({"scheduled_at": "2000-01-02T00:00:00.000Z"}).encode()
            conn.request("POST", f"/api/items/{first_task['item_id']}/schedule", reschedule_body, {"Content-Type": "application/json", "Cookie": cookie})
            rescheduled = conn.getresponse()
            self.assertEqual(rescheduled.status, 409)
            rescheduled.read()

            resave_body = json.dumps({"edited_copy": "too late", "status": "approved"}).encode()
            conn.request("POST", f"/api/items/{first_task['item_id']}/review", resave_body, {"Content-Type": "application/json", "Cookie": cookie})
            resaved = conn.getresponse()
            self.assertEqual(resaved.status, 409)
            resaved.read()

            claim_body = json.dumps({"now": "9999-12-31T23:59:59Z", "limit": 10}).encode()
            conn.request("POST", "/api/publish/claim_due", claim_body, worker_headers)
            failed_claim = conn.getresponse()
            failed_tasks = json.loads(failed_claim.read().decode())["tasks"]
            self.assertEqual(len(failed_tasks), 1)
            failed_task = failed_tasks[0]
            result_body = json.dumps(
                {
                    "item_id": failed_task["item_id"],
                    "claim_token": failed_task["claim_token"],
                    "status": "failed",
                    "error": "mock publisher failed",
                }
            ).encode()
            conn.request("POST", "/api/publish/result", result_body, worker_headers)
            failed = conn.getresponse()
            self.assertEqual(failed.status, 200)
            self.assertEqual(json.loads(failed.read().decode())["item"]["status"], "failed")

            conn.request("POST", "/api/publish/claim_due", claim_body, worker_headers)
            no_future_claim = conn.getresponse()
            self.assertEqual(json.loads(no_future_claim.read().decode())["tasks"], [])

            db_conn = db.connect(self.config.db_path)
            row = db.get_item(db_conn, item_ids[0])
            db_conn.close()
            self.assertEqual(row["edited_copy"], f"{edited} 0")
            self.assertEqual(row["review_status"], "approved")
            self.assertEqual(row["schedule_status"], "scheduled")
            self.assertEqual(row["scheduled_at"], "2000-01-01T00:00:00.000Z")
            self.assertEqual(row["publish_status"], "published")
        finally:
            server.shutdown()
            server.server_close()

    def test_production_requires_deepseek_key_for_generation(self) -> None:
        old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        old_key_file = os.environ.pop("DEEPSEEK_API_KEY_FILE", None)
        try:
            config = Config(
                db_path=f"{self.tmp.name}/prod.sqlite3",
                app_env="production",
                user="u",
                password="p",
                session_secret="s",
                publish_token="worker-secret",
            )
            result = run_sync(config)
            self.assertEqual(result.generated, 0)
            self.assertTrue(any("DEEPSEEK" in error for error in result.errors))
        finally:
            if old_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_key
            if old_key_file is not None:
                os.environ["DEEPSEEK_API_KEY_FILE"] = old_key_file

    def test_production_requires_publish_token(self) -> None:
        config = Config(db_path=f"{self.tmp.name}/prod-token.sqlite3", app_env="production", user="u", password="p", session_secret="s")
        with self.assertRaisesRegex(RuntimeError, "COPY_FACTORY_PUBLISH_TOKEN"):
            config.validate_for_web()

    def test_local_writer_localizes_english_sources_to_chinese(self) -> None:
        item = adapters.mock_reddit()[0]
        copy = writer.fake_writer(item)
        self.assertIn("海外投资者讨论 AI 资本开支", copy)
        self.assertNotIn("Investors debate", copy)
        self.assertNotIn("A thread on large-cap tech", copy)

    def test_deepseek_smoke_requires_real_key_without_traceback(self) -> None:
        env = os.environ.copy()
        env.pop("DEEPSEEK_API_KEY", None)
        env.pop("DEEPSEEK_API_KEY_FILE", None)
        result = subprocess.run([sys.executable, "scripts/deepseek_smoke.py"], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("DEEPSEEK_API_KEY", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

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
