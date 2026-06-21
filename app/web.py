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
:root{{color-scheme:light;--line:#e6ecf0;--muted:#536471;--ink:#0f1419;--blue:#1d9bf0;--soft:#f7f9f9;--card:#fff;--green:#00a36c;--red:#dc2626}}
*{{box-sizing:border-box}} body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#fff;color:var(--ink)}}
a{{color:inherit;text-decoration:none}} a:hover{{text-decoration:underline}} main{{max-width:1320px;margin:0 auto}}
.shell{{display:grid;grid-template-columns:230px minmax(0,760px) 330px;min-height:100vh}}
.rail{{border-right:1px solid var(--line);padding:22px 18px;position:sticky;top:0;height:100vh}}
.brand{{font-size:29px;font-weight:900;margin:0 0 28px;letter-spacing:0}} .nav{{display:grid;gap:8px}} .nav a,.sync-btn,.logout{{border-radius:999px;padding:12px 16px;font-weight:750}}
.nav a:hover,.logout:hover{{background:var(--soft);text-decoration:none}} .sync-btn{{border:0;background:var(--ink);color:#fff;width:100%;cursor:pointer}}
.feed{{border-right:1px solid var(--line);min-height:100vh}} .topbar{{position:sticky;top:0;z-index:2;background:rgba(255,255,255,.9);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:14px 18px}}
h1{{font-size:22px;margin:0}} h2{{font-size:17px;line-height:1.35;margin:0 0 4px}} .hint,.meta{{color:var(--muted);font-size:13px}} .subline{{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}}
.metric-pill{{background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:5px 10px;font-size:12px;color:var(--muted)}} .metric-pill strong{{color:var(--ink)}}
.notice{{border-bottom:1px solid var(--line);padding:10px 18px;color:var(--muted);font-size:13px}}
.tweet{{display:grid;grid-template-columns:48px minmax(0,1fr);gap:12px;padding:16px 18px;border-bottom:1px solid var(--line)}}
.tweet:hover{{background:#fafafa}} .avatar{{width:44px;height:44px;border-radius:50%;background:var(--ink);color:#fff;display:grid;place-items:center;font-weight:800}}
.head{{display:flex;gap:6px;align-items:center;flex-wrap:wrap}} .source{{font-weight:800}} .dot{{color:var(--muted)}} .pill{{border:1px solid var(--line);border-radius:999px;padding:2px 8px;font-size:12px;color:var(--muted);background:#fff}}
.pill.approved{{color:#15803d;background:#f0fdf4;border-color:#bbf7d0}} .pill.rejected{{color:#b91c1c;background:#fef2f2;border-color:#fecaca}}
.copy{{white-space:pre-wrap;line-height:1.56;margin:10px 0 0;font-size:15px}} .media{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px;max-width:520px}} .media-tile{{position:relative;display:block;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:linear-gradient(135deg,#f7f9f9,#eef3f5);min-height:132px}} .media-tile img{{width:100%;height:132px;object-fit:cover;display:block}} .media-label{{position:absolute;left:8px;bottom:8px;background:rgba(15,20,25,.82);color:#fff;border-radius:999px;padding:4px 8px;font-size:12px}} .media span{{border:1px solid var(--line);border-radius:8px;padding:12px;color:var(--muted);font-size:12px;background:var(--soft)}}
.actions{{display:flex;gap:12px;margin-top:12px;color:var(--muted);font-size:13px;align-items:center;flex-wrap:wrap}} .actions a{{color:var(--blue);font-weight:800}} .action-primary{{border:1px solid #b6ddff;border-radius:999px;padding:6px 12px;background:#eef7ff}}
.side{{padding:18px;position:sticky;top:0;height:100vh}} .card{{background:var(--soft);border-radius:8px;padding:16px;margin-bottom:14px}} .stat{{display:flex;justify-content:space-between;margin:8px 0}} .stat strong{{font-size:18px}}
.queue-card{{border:1px solid var(--line);background:#fff;border-radius:8px;padding:14px;margin-bottom:14px}} .queue-card h2{{margin-bottom:10px}}
.login{{max-width:420px;margin:80px auto;padding:0 18px}} .panel{{border:1px solid var(--line);border-radius:8px;padding:18px;background:#fff}}
input,textarea,select,button{{font:inherit}} input,textarea,select{{width:100%;border:1px solid var(--line);border-radius:8px;padding:12px;background:#fff}} textarea{{min-height:320px;line-height:1.55}}
button{{cursor:pointer}} .primary{{border:0;background:var(--blue);color:#fff;border-radius:999px;padding:10px 18px;font-weight:800}} pre{{white-space:pre-wrap;background:var(--soft);padding:14px;border-radius:8px;line-height:1.5}}
.detail{{display:grid;grid-template-columns:minmax(0,760px) 330px;gap:0;max-width:1090px;margin:0 auto;border-left:1px solid var(--line);border-right:1px solid var(--line)}}
.detail-main{{min-height:100vh;border-right:1px solid var(--line)}} .detail-section{{padding:16px 18px;border-bottom:1px solid var(--line)}} .back{{color:var(--blue);font-weight:700}}
.media-list{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}} .media-list .media-tile{{min-height:180px}} .media-list img{{height:180px}}
@media(max-width:960px){{.shell{{grid-template-columns:72px minmax(0,1fr)}}.side{{display:none}}.rail{{padding:16px 10px}}.brand{{font-size:20px;text-align:center}}.nav a span{{display:none}}.sync-btn{{padding:10px}}.detail{{display:block;border:0}}}}
@media(max-width:640px){{.shell{{display:block}}.rail{{height:auto;position:static;border-right:0;border-bottom:1px solid var(--line)}}.nav{{display:flex;align-items:center}}.feed{{border-right:0}}}}
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
                msg = f"同步完成：fetched={result.fetched}, inserted={result.inserted}, duplicates={result.duplicates}, generated={result.generated}, skipped={result.skipped}, errors={len(result.errors)}"
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
<div class="login">
<h1>Copy Factory</h1>
<form method="post" action="/login" class="panel">
<p class="meta">{html.escape(message)}</p>
<p><input name="user" autocomplete="username" placeholder="账号" required></p>
<p><input name="password" type="password" autocomplete="current-password" placeholder="密码" required></p>
<button class="primary" type="submit">登录</button>
</form>
</div>
"""
        self.send_html("Login", body)

    def review_page(self, message: str) -> None:
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        items = db.today_items(conn)
        conn.close()
        counts = {"draft": 0, "approved": 0, "rejected": 0}
        for row in items:
            counts[row["review_status"]] = counts.get(row["review_status"], 0) + 1
        rows = "\n".join(
            self.tweet(row)
            for row in items
        )
        body = f"""
<div class="shell">
<aside class="rail">
<p class="brand">CF</p>
<nav class="nav">
<a href="/review"><span>审核池</span></a>
<a href="/logout" class="logout"><span>退出</span></a>
</nav>
<form method="post" action="/sync" style="margin-top:22px"><button class="sync-btn" type="submit">同步</button></form>
</aside>
<section class="feed">
<div class="topbar">
<h1>今日待审核池</h1>
<p class="hint">最新快照进来后，只处理新增。每条都保留原文、图片和人工审核状态。</p>
<div class="subline">
<span class="metric-pill">全部 <strong>{len(items)}</strong></span>
<span class="metric-pill">待审 <strong>{counts.get('draft', 0)}</strong></span>
<span class="metric-pill">通过 <strong>{counts.get('approved', 0)}</strong></span>
<span class="metric-pill">拒绝 <strong>{counts.get('rejected', 0)}</strong></span>
</div>
</div>
{f'<p class="notice">{html.escape(message)}</p>' if message else ''}
{rows or '<p class="notice">暂无文案。点击同步生成数据。</p>'}
</section>
<aside class="side">
<div class="queue-card">
<h2>同步概览</h2>
<div class="stat"><span>全部</span><strong>{len(items)}</strong></div>
<div class="stat"><span>待审</span><strong>{counts.get('draft', 0)}</strong></div>
<div class="stat"><span>通过</span><strong>{counts.get('approved', 0)}</strong></div>
<div class="stat"><span>拒绝</span><strong>{counts.get('rejected', 0)}</strong></div>
</div>
<div class="card">
<h2>处理规则</h2>
<p class="hint">先看 health 的 snapshot 时间；变了才拉 export。入库按 source_id / url / hash 去重。</p>
</div>
</aside>
</div>
"""
        self.send_html("Review", body)

    def tweet(self, row) -> str:
        media = json.loads(row["media_urls"])
        media_html = self.media_preview(media)
        status = html.escape(row["review_status"])
        copy = html.escape((row["edited_copy"] or row["generated_copy"])[:260])
        return f"""<article class="tweet">
<a class="avatar" href="/items/{row['id']}">{html.escape(row['source'][:1].upper())}</a>
<div>
<div class="head">
<a class="source" href="/items/{row['id']}">{html.escape(row['title'])}</a>
<span class="dot">·</span><span class="meta">{html.escape(row['source'])}</span>
<span class="dot">·</span><span class="meta">{html.escape(row['updated_at'])}</span>
<span class="pill {status}">{status}</span><span class="pill">{html.escape(row['generation_status'])}</span>
</div>
<p class="copy">{copy}</p>
<div class="media">{media_html}</div>
<div class="actions"><a class="action-primary" href="/items/{row['id']}">编辑文案</a><span>原文已保留</span><span>图片引用 {len(media)}</span></div>
</div>
</article>"""

    def media_preview(self, media: list[object]) -> str:
        if not media:
            return "<span>无图片</span>"
        cells = []
        for i, ref in enumerate(media[:4], 1):
            url = self.media_url(ref)
            if url:
                cells.append(f'<a class="media-tile" href="{html.escape(url)}"><img src="{html.escape(url)}" alt="图片 {i}" loading="lazy"><span class="media-label">图片 {i}</span></a>')
            else:
                cells.append(f"<span>图片 {i}</span>")
        return "".join(cells)

    @staticmethod
    def media_url(ref: object) -> str:
        if isinstance(ref, str):
            return ref
        if isinstance(ref, dict):
            return str(ref.get("thumbnail_ref") or ref.get("original_image_ref") or "")
        return ""

    def item_page(self, item_id: int) -> None:
        conn = db.connect(self.config.db_path)
        db.init_db(conn)
        item = db.get_item(conn, item_id)
        conn.close()
        if not item:
            self.send_error(404)
            return
        media_refs = json.loads(item["media_urls"])
        media = self.media_detail(media_refs)
        body = f"""
<div class="detail">
<section class="detail-main">
<div class="topbar"><a class="back" href="/review">← 返回审核池</a></div>
<div class="detail-section">
<h1>{html.escape(item['title'])}</h1>
<p class="meta">{html.escape(item['source'])} · {html.escape(item['author'])} · <a href="{html.escape(item['url'])}">原文链接</a></p>
</div>
<div class="detail-section">
<h2>原文</h2>
<pre>{html.escape(item['text'])}</pre>
</div>
<div class="detail-section">
<h2>图片 / 媒体引用</h2>
{media}
</div>
<form method="post" action="/items/{item_id}/save" class="panel">
<h2>生成文案</h2>
<textarea name="edited_copy">{html.escape(item['edited_copy'] or item['generated_copy'])}</textarea>
<p><select name="status">
{self.option('draft', item['review_status'])}
{self.option('approved', item['review_status'])}
{self.option('rejected', item['review_status'])}
</select></p>
<p><button class="primary" type="submit">保存</button></p>
<p class="meta">生成状态：{html.escape(item['generation_status'])} {html.escape(item['generation_error'])}</p>
</form>
</section>
<aside class="side">
<div class="card"><h2>审核动作</h2><p class="hint">改文字，选状态，保存。图片引用保留在原文旁边。</p></div>
</aside>
</div>
"""
        self.send_html(item["title"], body)

    def media_detail(self, media: list[object]) -> str:
        if not media:
            return "<p class=\"hint\">无图片</p>"
        cells = []
        for i, ref in enumerate(media, 1):
            url = self.media_url(ref)
            label = html.escape(str(ref))
            if url:
                cells.append(f'<a class="media-tile" href="{html.escape(url)}"><img src="{html.escape(url)}" alt="图片 {i}" loading="lazy"><span class="media-label">图片 {i} · 打开原图</span></a>')
            else:
                cells.append(f"<p>{label}</p>")
        return f'<div class="media-list">{"".join(cells)}</div>'

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
