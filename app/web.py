from __future__ import annotations

import argparse
import html
import hmac
import json
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app import db
from app.config import Config
from app.sync import run_sync


def sign(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.encode(), "sha256").hexdigest()


def valid_session(header: str | None, config: Config) -> bool:
    jar = cookies.SimpleCookie(header or "")
    morsel = jar.get("copy_factory")
    if not morsel or ":" not in morsel.value:
        return False
    value, sig = morsel.value.split(":", 1)
    return value == config.user and hmac.compare_digest(sig, sign(value, config.session_secret))


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f7f4;color:#1d1d1b}}
main{{max-width:980px;margin:0 auto;padding:28px 18px}}
a{{color:#075985}} .bar{{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:20px}}
.item,form.panel{{background:white;border:1px solid #ddd;border-radius:8px;padding:16px;margin:12px 0}}
.meta{{color:#666;font-size:14px}} textarea{{width:100%;min-height:260px;font:16px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}}
button,input,select{{font:inherit;padding:8px 10px}} button{{cursor:pointer}} pre{{white-space:pre-wrap;background:#f1f1ed;padding:12px;border-radius:6px}}
</style>
</head>
<body><main>{body}</main></body></html>""".encode()


class Handler(BaseHTTPRequestHandler):
    config = Config()

    def send_html(self, title: str, body: str, status: int = 200, headers: dict[str, str] | None = None) -> None:
        data = page(title, body)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, path: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", path)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode()
        return {k: v[0] for k, v in parse_qs(raw).items()}

    def require_login(self) -> bool:
        if valid_session(self.headers.get("Cookie"), self.config):
            return True
        self.redirect("/login")
        return False

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/login":
            self.login_page()
        elif path == "/logout":
            self.redirect("/login", {"Set-Cookie": "copy_factory=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
        elif path in {"/", "/review"}:
            if self.require_login():
                self.review_page("")
        elif path.startswith("/items/"):
            if self.require_login():
                self.item_page(int(path.rsplit("/", 1)[-1]))
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/login":
            form = self.read_form()
            if form.get("user") == self.config.user and form.get("password") == self.config.password:
                value = self.config.user
                self.redirect("/review", {"Set-Cookie": f"copy_factory={value}:{sign(value, self.config.session_secret)}; Path=/; HttpOnly; SameSite=Lax"})
            else:
                self.login_page("登录失败")
        elif path == "/sync":
            if self.require_login():
                result = run_sync(self.config)
                msg = f"同步完成：fetched={result.fetched}, inserted={result.inserted}, duplicates={result.duplicates}, generated={result.generated}, errors={len(result.errors)}"
                self.review_page(msg)
        elif path.startswith("/items/") and path.endswith("/save"):
            if self.require_login():
                item_id = int(path.split("/")[2])
                form = self.read_form()
                conn = db.connect(self.config.db_path)
                db.init_db(conn)
                db.save_review(conn, item_id, form.get("edited_copy", ""), form.get("status", "draft"))
                conn.close()
                self.redirect(f"/items/{item_id}?saved=1")
        else:
            self.send_error(404)

    def login_page(self, message: str = "") -> None:
        body = f"""
<h1>Copy Factory</h1>
<form method="post" action="/login" class="panel">
<p class="meta">{html.escape(message)}</p>
<p><input name="user" autocomplete="username" placeholder="账号" required></p>
<p><input name="password" type="password" autocomplete="current-password" placeholder="密码" required></p>
<button type="submit">登录</button>
</form>
"""
        self.send_html("Login", body)

    def review_page(self, message: str) -> None:
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        items = db.today_items(conn)
        conn.close()
        rows = "\n".join(
            f"""<article class="item">
<h2><a href="/items/{row['id']}">{html.escape(row['title'])}</a></h2>
<p class="meta">{html.escape(row['source'])} · {html.escape(row['review_status'])} · {html.escape(row['generation_status'])} · {html.escape(row['updated_at'])}</p>
<p>{html.escape((row['edited_copy'] or row['generated_copy'])[:180])}</p>
</article>"""
            for row in items
        )
        body = f"""
<div class="bar"><h1>今日待审核池</h1><p><a href="/logout">退出</a></p></div>
<form method="post" action="/sync"><button type="submit">手动同步</button></form>
<p class="meta">{html.escape(message)}</p>
{rows or '<p>暂无文案。点击手动同步生成 mock 数据。</p>'}
"""
        self.send_html("Review", body)

    def item_page(self, item_id: int) -> None:
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        item = db.get_item(conn, item_id)
        conn.close()
        if not item:
            self.send_error(404)
            return
        media = "\n".join(f"<li>{html.escape(url)}</li>" for url in json.loads(item["media_urls"]))
        body = f"""
<p><a href="/review">← 返回审核池</a></p>
<h1>{html.escape(item['title'])}</h1>
<p class="meta">{html.escape(item['source'])} · {html.escape(item['author'])} · <a href="{html.escape(item['url'])}">原文链接</a></p>
<h2>原文</h2>
<pre>{html.escape(item['text'])}</pre>
<h2>图片 / 媒体引用</h2>
<ul>{media or '<li>无</li>'}</ul>
<form method="post" action="/items/{item_id}/save" class="panel">
<h2>生成文案</h2>
<textarea name="edited_copy">{html.escape(item['edited_copy'] or item['generated_copy'])}</textarea>
<p><select name="status">
{self.option('draft', item['review_status'])}
{self.option('approved', item['review_status'])}
{self.option('rejected', item['review_status'])}
</select> <button type="submit">保存</button></p>
<p class="meta">生成状态：{html.escape(item['generation_status'])} {html.escape(item['generation_error'])}</p>
</form>
"""
        self.send_html(item["title"], body)

    @staticmethod
    def option(value: str, current: str) -> str:
        selected = " selected" if value == current else ""
        return f'<option value="{value}"{selected}>{value}</option>'


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
