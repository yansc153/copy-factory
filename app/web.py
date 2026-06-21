from __future__ import annotations

import argparse
from dataclasses import replace
import hmac
import json
import mimetypes
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app import db, writer
from app.config import Config
from app.sync import preview_sync, run_sync


STATIC_DIR = Path(__file__).with_name("static")


def sign(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.encode(), "sha256").hexdigest()


def valid_session(header: str | None, config: Config) -> bool:
    jar = cookies.SimpleCookie(header or "")
    morsel = jar.get("copy_factory")
    if not morsel or ":" not in morsel.value:
        return False
    value, sig = morsel.value.split(":", 1)
    return value == config.user and hmac.compare_digest(sig, sign(value, config.session_secret))


def valid_publish_token(header: str | None, config: Config) -> bool:
    token = config.mac_mini_token()
    prefix = "Bearer "
    if not token or not header or not header.startswith(prefix):
        return False
    return hmac.compare_digest(header.removeprefix(prefix), token)


class Handler(BaseHTTPRequestHandler):
    config = Config()

    def send_json(self, payload: dict[str, object], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, html: str, status: int = 200, headers: dict[str, str] | None = None) -> None:
        data = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def send_static(self, name: str) -> None:
        path = (STATIC_DIR / name).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, path: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", path)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def require_login(self) -> bool:
        if valid_session(self.headers.get("Cookie"), self.config):
            return True
        if self.path.startswith("/api/"):
            self.send_json({"error": "unauthorized"}, 401)
        else:
            self.redirect("/login")
        return False

    def require_publish_api(self) -> bool:
        if valid_session(self.headers.get("Cookie"), self.config) or valid_publish_token(self.headers.get("Authorization"), self.config):
            return True
        self.send_json({"error": "unauthorized"}, 401)
        return False

    def read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode()
        return {k: v[0] for k, v in parse_qs(raw).items()}

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode()) if length else {}

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/login":
            self.login_page()
        elif path == "/logout":
            self.redirect("/login", {"Set-Cookie": "copy_factory=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
        elif path in {"/", "/review", "/app"} or path.startswith("/items/"):
            if self.require_login():
                self.send_static("index.html")
        elif path.startswith("/static/"):
            if path == "/static/app.css" or self.require_login():
                self.send_static(path.removeprefix("/static/"))
        elif path.startswith("/api/"):
            if (path.startswith("/api/publish/") and self.require_publish_api()) or (
                not path.startswith("/api/publish/") and self.require_login()
            ):
                self.api_get(path)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/login":
            form = self.read_form()
            if form.get("user") == self.config.user and form.get("password") == self.config.password:
                value = self.config.user
                self.redirect(
                    "/review",
                    {"Set-Cookie": f"copy_factory={value}:{sign(value, self.config.session_secret)}; Path=/; HttpOnly; SameSite=Lax"},
                )
            else:
                self.login_page("登录失败")
        elif path.startswith("/api/"):
            if path == "/api/publish/confirm_plan":
                if self.require_login():
                    self.api_post(path)
            elif path.startswith("/api/publish/"):
                if self.require_publish_api():
                    self.api_post(path)
            elif self.require_login():
                self.api_post(path)
        else:
            self.send_error(404)

    def login_page(self, message: str = "") -> None:
        self.send_html(
            f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Copy Factory Login</title><link rel="icon" href="data:,"><link rel="stylesheet" href="/static/app.css"></head><body class="login-body"><form class="login-card" method="post" action="/login"><h1>Copy Factory</h1><p>{message or "登录内容工作台"}</p><input name="user" autocomplete="username" placeholder="账号" required><input name="password" type="password" autocomplete="current-password" placeholder="密码" required><button type="submit">进入工作台</button></form></body></html>"""
        )

    def api_get(self, path: str) -> None:
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        try:
            if path == "/api/items":
                self.send_json({"items": [row_to_item(row) for row in db.today_items(conn)]})
            elif path.startswith("/api/items/"):
                item = db.get_item(conn, int(path.split("/")[3]))
                self.send_json({"item": row_to_item(item) if item else None}, 200 if item else 404)
            elif path == "/api/schedule":
                items = [row_to_item(row) for row in db.today_items(conn)]
                self.send_json({"items": items, "scheduled": [item for item in items if item["schedule_status"] == "scheduled"]})
            elif path == "/api/settings/status":
                self.send_json(
                    {
                        "db_path": self.config.db_path,
                        "sources": list(self.config.sources),
                        "export_limit": self.config.export_limit,
                        "has_export_token": bool(self.config.news_harness_token()),
                        "has_deepseek_key": writer.has_deepseek_key(),
                        "has_publish_token": bool(self.config.mac_mini_token()),
                        "runs": [row_to_run(row) for row in db.recent_sync_runs(conn)],
                    }
                )
            elif path == "/api/publish/queue":
                self.send_json({"tasks": [row_to_publish_task(row) for row in db.publish_queue(conn)]})
            else:
                self.send_error(404)
        finally:
            conn.close()

    def api_post(self, path: str) -> None:
        payload = self.read_json()
        if path == "/api/sync/preview":
            self.send_json({"result": result_to_json(preview_sync(self.config_from_payload(payload)))})
        elif path == "/api/sync/run":
            self.send_json({"result": result_to_json(run_sync(self.config_from_payload(payload)))})
        elif path.startswith("/api/items/") and path.endswith("/review"):
            self.save_review_api(path, payload)
        elif path.startswith("/api/items/") and path.endswith("/schedule"):
            self.save_schedule_api(path, payload)
        elif path.startswith("/api/items/") and path.endswith("/unschedule"):
            self.clear_schedule_api(path)
        elif path == "/api/publish/confirm_plan":
            self.confirm_publish_plan_api()
        elif path == "/api/publish/claim_due":
            self.claim_due_api(payload)
        elif path == "/api/publish/result":
            self.publish_result_api(payload)
        else:
            self.send_error(404)

    def config_from_payload(self, payload: dict[str, object]) -> Config:
        return replace(
            self.config,
            export_limit=int(payload.get("limit") or self.config.export_limit),
            import_since=str(payload.get("since") or self.config.import_since),
            import_until=str(payload.get("until") or self.config.import_until),
        )

    def save_review_api(self, path: str, payload: dict[str, object]) -> None:
        item_id = int(path.split("/")[3])
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        try:
            if not db.save_review(
                conn,
                item_id,
                str(payload.get("edited_copy", "")),
                str(payload.get("status", "draft")),
                str(payload["selected_media_url"]) if "selected_media_url" in payload else None,
            ):
                self.send_json({"error": "item is locked for publishing"}, 409)
                return
            self.send_json({"item": row_to_item(db.get_item(conn, item_id))})
        finally:
            conn.close()

    def save_schedule_api(self, path: str, payload: dict[str, object]) -> None:
        item_id = int(path.split("/")[3])
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        try:
            if not db.save_schedule(conn, item_id, str(payload.get("scheduled_at", ""))):
                self.send_json({"error": "item is locked for publishing"}, 409)
                return
            self.send_json({"item": row_to_item(db.get_item(conn, item_id))})
        finally:
            conn.close()

    def clear_schedule_api(self, path: str) -> None:
        item_id = int(path.split("/")[3])
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        try:
            if not db.clear_schedule(conn, item_id):
                self.send_json({"error": "item is locked for publishing"}, 409)
                return
            self.send_json({"item": row_to_item(db.get_item(conn, item_id))})
        finally:
            conn.close()

    def confirm_publish_plan_api(self) -> None:
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        try:
            confirmed = db.confirm_publish_plan(conn)
            self.send_json({"confirmed": confirmed, "tasks": [row_to_publish_task(row) for row in db.publish_queue(conn)]})
        finally:
            conn.close()

    def claim_due_api(self, payload: dict[str, object]) -> None:
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        try:
            tasks = db.claim_due(conn, db.due_now(), int(payload.get("limit") or 1))
            self.send_json({"tasks": [row_to_publish_task(row, token) for row, token in tasks]})
        finally:
            conn.close()

    def publish_result_api(self, payload: dict[str, object]) -> None:
        item_id = int(payload.get("item_id") or 0)
        claim_token = str(payload.get("claim_token") or "")
        status = str(payload.get("status") or "")
        error = str(payload.get("error") or "")
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        try:
            if not db.save_publish_result(conn, item_id, claim_token, status, error):
                self.send_json({"error": "claim not found"}, 409)
                return
            self.send_json({"item": row_to_publish_task(db.get_item(conn, item_id))})
        finally:
            conn.close()


def row_to_item(row) -> dict[str, object]:
    return {
        "id": row["id"],
        "source": row["source"],
        "source_id": row["source_id"],
        "url": row["url"],
        "title": row["title"],
        "text": row["text"],
        "author": row["author"],
        "published_at": row["published_at"],
        "media_urls": json.loads(row["media_urls"]),
        "selected_media_url": row["selected_media_url"],
        "generation_status": row["generation_status"],
        "generation_error": row["generation_error"],
        "generated_copy": row["generated_copy"],
        "review_status": row["review_status"],
        "edited_copy": row["edited_copy"],
        "schedule_status": row["schedule_status"],
        "scheduled_at": row["scheduled_at"],
        "publish_status": row["publish_status"],
        "publish_confirmed_at": row["publish_confirmed_at"],
        "publish_claimed_at": row["publish_claimed_at"],
        "publish_result_at": row["publish_result_at"],
        "publish_error": row["publish_error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def row_to_publish_task(row, claim_token: str = "") -> dict[str, object]:
    item = row_to_item(row)
    task = {
        "item_id": item["id"],
        "scheduled_at": item["scheduled_at"],
        "status": item["publish_status"],
        "copy": item["edited_copy"] or item["generated_copy"],
        "source": item["source"],
        "source_id": item["source_id"],
        "source_url": item["url"],
        "title": item["title"],
        "media_urls": item["media_urls"],
        "selected_media_url": item["selected_media_url"],
        "confirmed_at": item["publish_confirmed_at"],
        "claimed_at": item["publish_claimed_at"],
        "result_at": item["publish_result_at"],
        "error": item["publish_error"],
    }
    if claim_token:
        task["claim_token"] = claim_token
    return task


def row_to_run(row) -> dict[str, object]:
    return {
        "kind": row["kind"],
        "batch": row["batch"],
        "fetched": row["fetched"],
        "inserted": row["inserted"],
        "duplicates": row["duplicates"],
        "filtered": row["filtered"],
        "generated": row["generated"],
        "skipped": bool(row["skipped"]),
        "errors": json.loads(row["errors"]),
        "created_at": row["created_at"],
    }


def result_to_json(result) -> dict[str, object]:
    return {
        "batch": result.batch,
        "fetched": result.fetched,
        "inserted": result.inserted,
        "duplicates": result.duplicates,
        "filtered": result.filtered,
        "generated": result.generated,
        "skipped": result.skipped,
        "errors": result.errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    Handler.config.validate_for_web()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Copy Factory running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
