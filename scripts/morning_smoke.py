#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Config
from app.web import Handler


class QuietHandler(Handler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def request(host: str, port: int, method: str, path: str, body: object = None, headers: dict[str, str] | None = None):
    conn = http.client.HTTPConnection(host, port, timeout=10)
    payload = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, dict) else body
    conn.request(method, path, payload, headers or {})
    response = conn.getresponse()
    data = response.read().decode()
    conn.close()
    parsed = json.loads(data) if data else {}
    if response.status >= 400:
        raise RuntimeError(f"{method} {path} failed: {response.status} {parsed}")
    return response, parsed


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config = Config(db_path=f"{tmp}/morning.sqlite3", user="smoke", password="secret", session_secret="smoke-secret")
        QuietHandler.config = config
        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            body = urlencode({"user": config.user, "password": config.password})
            login_conn = http.client.HTTPConnection(host, port, timeout=10)
            login_conn.request("POST", "/login", body, {"Content-Type": "application/x-www-form-urlencoded"})
            login = login_conn.getresponse()
            cookie = login.getheader("Set-Cookie") or ""
            login.read()
            login_conn.close()
            if login.status != 303 or "copy_factory=" not in cookie:
                raise RuntimeError(f"login failed: {login.status}")

            headers = {"Content-Type": "application/json", "Cookie": cookie}
            _, sync = request(host, port, "POST", "/api/sync/run", {}, headers)
            _, items_payload = request(host, port, "GET", "/api/items", headers={"Cookie": cookie})
            items = items_payload["items"]
            item = next((row for row in items if row["generated_copy"]), None)
            if not item:
                raise RuntimeError("sync produced no generated_copy")

            edited = item["generated_copy"] + "\n\n本地 morning-smoke 已确认。"
            request(host, port, "POST", f"/api/items/{item['id']}/review", {"edited_copy": edited, "status": "approved"}, headers)
            request(host, port, "POST", f"/api/items/{item['id']}/schedule", {"scheduled_at": "2099-01-01T01:00:00.000Z"}, headers)
            _, confirmed = request(host, port, "POST", "/api/publish/confirm_plan", {}, headers)
            _, queue = request(host, port, "GET", "/api/publish/queue", headers={"Cookie": cookie})
            confirmed_tasks = [task for task in queue["tasks"] if task["status"] == "confirmed"]
            if not confirmed_tasks:
                raise RuntimeError("confirm plan produced no confirmed task")

            evidence = {
                "url": f"http://{host}:{port}",
                "sync": sync["result"],
                "item_id": item["id"],
                "generated_copy": bool(item["generated_copy"]),
                "confirmed": confirmed["confirmed"],
                "queue": [{"item_id": task["item_id"], "status": task["status"]} for task in confirmed_tasks],
            }
            print(json.dumps(evidence, ensure_ascii=False, indent=2))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
