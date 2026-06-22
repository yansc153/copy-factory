from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_id TEXT,
            url TEXT,
            title TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT '',
            published_at TEXT NOT NULL DEFAULT '',
            observed_at TEXT NOT NULL DEFAULT '',
            media_urls TEXT NOT NULL DEFAULT '[]',
            selected_media_url TEXT NOT NULL DEFAULT '',
            work_date TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            sync_batch TEXT NOT NULL,
            generation_status TEXT NOT NULL DEFAULT 'pending',
            generation_error TEXT NOT NULL DEFAULT '',
            generated_copy TEXT NOT NULL DEFAULT '',
            review_status TEXT NOT NULL DEFAULT 'draft',
            edited_copy TEXT NOT NULL DEFAULT '',
            schedule_status TEXT NOT NULL DEFAULT 'unscheduled',
            scheduled_at TEXT NOT NULL DEFAULT '',
            publish_status TEXT NOT NULL DEFAULT 'none',
            publish_confirmed_at TEXT NOT NULL DEFAULT '',
            publish_claimed_at TEXT NOT NULL DEFAULT '',
            publish_claim_token TEXT NOT NULL DEFAULT '',
            publish_result_at TEXT NOT NULL DEFAULT '',
            publish_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_source_id
            ON source_items(source, source_id)
            WHERE source_id IS NOT NULL AND source_id != '';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_source_url
            ON source_items(source, url)
            WHERE url IS NOT NULL AND url != '';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_source_hash
            ON source_items(source, content_hash);
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            batch TEXT NOT NULL,
            fetched INTEGER NOT NULL,
            inserted INTEGER NOT NULL,
            duplicates INTEGER NOT NULL,
            filtered INTEGER NOT NULL,
            generated INTEGER NOT NULL,
            skipped INTEGER NOT NULL,
            errors TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    ensure_columns(conn)
    conn.commit()


def ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(source_items)")}
    if "schedule_status" not in columns:
        conn.execute("ALTER TABLE source_items ADD COLUMN schedule_status TEXT NOT NULL DEFAULT 'unscheduled'")
    if "scheduled_at" not in columns:
        conn.execute("ALTER TABLE source_items ADD COLUMN scheduled_at TEXT NOT NULL DEFAULT ''")
    if "selected_media_url" not in columns:
        conn.execute("ALTER TABLE source_items ADD COLUMN selected_media_url TEXT NOT NULL DEFAULT ''")
    if "work_date" not in columns:
        conn.execute("ALTER TABLE source_items ADD COLUMN work_date TEXT NOT NULL DEFAULT ''")
    if "observed_at" not in columns:
        conn.execute("ALTER TABLE source_items ADD COLUMN observed_at TEXT NOT NULL DEFAULT ''")
    conn.execute("UPDATE source_items SET work_date = substr(created_at, 1, 10) WHERE work_date = ''")
    for name in (
        "publish_status",
        "publish_confirmed_at",
        "publish_claimed_at",
        "publish_claim_token",
        "publish_result_at",
        "publish_error",
    ):
        if name not in columns:
            default = "none" if name == "publish_status" else ""
            conn.execute(f"ALTER TABLE source_items ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def work_today() -> str:
    return datetime.now(SHANGHAI).date().isoformat()


def parse_item_time(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def observed_value(item: dict[str, Any]) -> str:
    return str(item.get("observed_at") or item.get("fetched_at") or item.get("published_at") or "")


def capture_value(item: dict[str, Any]) -> str:
    return str(item.get("observed_at") or item.get("fetched_at") or "")


def work_date_for_item(item: dict[str, Any]) -> str:
    observed = parse_item_time(observed_value(item))
    return observed.astimezone(SHANGHAI).date().isoformat() if observed else work_today()


def due_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def insert_source_item(conn: sqlite3.Connection, item: dict[str, Any], sync_batch: str) -> tuple[int, bool]:
    media = item.get("media_urls", [])
    media_urls = json.dumps(media, ensure_ascii=False)
    selected_media_url = str(media[0]) if media and isinstance(media[0], str) else ""
    content_hash = hash_text(f"{item.get('title', '')}\n{item.get('text', '')}")
    ts = now()
    existing = conn.execute(
        """
        SELECT id, observed_at FROM source_items
        WHERE source = ?
          AND (
            (? != '' AND source_id = ?)
            OR (? != '' AND url = ?)
            OR content_hash = ?
          )
        LIMIT 1
        """,
        (item["source"], item.get("source_id", ""), item.get("source_id", ""), item.get("url", ""), item.get("url", ""), content_hash),
    ).fetchone()
    if existing:
        incoming_observed = capture_value(item)
        incoming_time = parse_item_time(incoming_observed)
        existing_time = parse_item_time(str(existing["observed_at"] or ""))
        if incoming_time and (not existing_time or incoming_time > existing_time):
            conn.execute(
                """
                UPDATE source_items
                SET observed_at = ?, work_date = ?, updated_at = ?
                WHERE id = ?
                """,
                (incoming_observed, incoming_time.astimezone(SHANGHAI).date().isoformat(), ts, existing["id"]),
            )
            conn.commit()
        return int(existing["id"]), False

    cur = conn.execute(
        """
        INSERT INTO source_items (
            source, source_id, url, title, text, author, published_at, observed_at, media_urls, selected_media_url,
            work_date, content_hash, sync_batch, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["source"],
            item.get("source_id", ""),
            item.get("url", ""),
            item.get("title", ""),
            item["text"],
            item.get("author", ""),
            item.get("published_at", ""),
            observed_value(item),
            media_urls,
            selected_media_url,
            work_date_for_item(item),
            content_hash,
            sync_batch,
            ts,
            ts,
        ),
    )
    conn.commit()
    return int(cur.lastrowid), True


def save_generation(conn: sqlite3.Connection, item_id: int, copy: str, error: str = "", status: str = "generated") -> None:
    status = "error" if error else status
    conn.execute(
        """
        UPDATE source_items
        SET generation_status = ?, generation_error = ?, generated_copy = ?, edited_copy = ?,
            review_status = 'draft', schedule_status = 'unscheduled', scheduled_at = '',
            publish_status = 'none', publish_confirmed_at = '', publish_claimed_at = '',
            publish_claim_token = '', publish_result_at = '', publish_error = '', updated_at = ?
        WHERE id = ?
        """,
        (status, error, copy, copy, now(), item_id),
    )
    conn.commit()


def save_review(conn: sqlite3.Connection, item_id: int, edited_copy: str, status: str, selected_media_url: str | None = None) -> bool:
    if status not in {"draft", "approved", "rejected"}:
        raise ValueError("status must be draft, approved, or rejected")
    cur = conn.execute(
        """
        UPDATE source_items
        SET edited_copy = ?, review_status = ?,
            selected_media_url = COALESCE(?, selected_media_url),
            publish_status = CASE
                WHEN ? != 'approved' THEN 'none'
                WHEN publish_status IN ('confirmed', 'failed') THEN 'none'
                ELSE publish_status
            END,
            publish_confirmed_at = CASE WHEN publish_status IN ('confirmed', 'failed') OR ? != 'approved' THEN '' ELSE publish_confirmed_at END,
            publish_claimed_at = CASE WHEN publish_status IN ('confirmed', 'failed') OR ? != 'approved' THEN '' ELSE publish_claimed_at END,
            publish_claim_token = CASE WHEN publish_status IN ('confirmed', 'failed') OR ? != 'approved' THEN '' ELSE publish_claim_token END,
            publish_result_at = CASE WHEN publish_status IN ('confirmed', 'failed') OR ? != 'approved' THEN '' ELSE publish_result_at END,
            publish_error = CASE WHEN publish_status IN ('confirmed', 'failed') OR ? != 'approved' THEN '' ELSE publish_error END,
            updated_at = ?
        WHERE id = ? AND publish_status NOT IN ('claimed', 'published')
        """,
        (edited_copy, status, selected_media_url, status, status, status, status, status, status, now(), item_id),
    )
    conn.commit()
    return int(cur.rowcount) == 1


def save_schedule(conn: sqlite3.Connection, item_id: int, scheduled_at: str) -> bool:
    cur = conn.execute(
        """
        UPDATE source_items
        SET schedule_status = 'scheduled', scheduled_at = ?, publish_status = 'none',
            publish_confirmed_at = '', publish_claimed_at = '', publish_claim_token = '',
            publish_result_at = '', publish_error = '', updated_at = ?
        WHERE id = ? AND publish_status IN ('none', 'failed')
        """,
        (scheduled_at, now(), item_id),
    )
    conn.commit()
    return int(cur.rowcount) == 1


def clear_schedule(conn: sqlite3.Connection, item_id: int) -> bool:
    cur = conn.execute(
        """
        UPDATE source_items
        SET schedule_status = 'unscheduled', scheduled_at = '', publish_status = 'none',
            publish_confirmed_at = '', publish_claimed_at = '', publish_claim_token = '',
            publish_result_at = '', publish_error = '', updated_at = ?
        WHERE id = ? AND publish_status IN ('none', 'failed')
        """,
        (now(), item_id),
    )
    conn.commit()
    return int(cur.rowcount) == 1


def confirm_publish_plan(conn: sqlite3.Connection) -> int:
    ts = now()
    cur = conn.execute(
        """
        UPDATE source_items
        SET publish_status = 'confirmed', publish_confirmed_at = ?, publish_error = '', updated_at = ?
        WHERE review_status = 'approved'
          AND schedule_status = 'scheduled'
          AND scheduled_at != ''
          AND publish_status IN ('none', 'failed')
        """,
        (ts, ts),
    )
    conn.commit()
    return int(cur.rowcount)


def publish_queue(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT * FROM source_items
            WHERE publish_status IN ('confirmed', 'claimed', 'published', 'failed')
            ORDER BY scheduled_at ASC, id ASC
            """
        )
    )


def claim_due(conn: sqlite3.Connection, due_at: str = "", limit: int = 1) -> list[tuple[sqlite3.Row, str]]:
    limit = max(1, min(limit, 20))
    ts = now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = list(
            conn.execute(
                """
                SELECT * FROM source_items
                WHERE publish_status = 'confirmed'
                  AND schedule_status = 'scheduled'
                ORDER BY scheduled_at ASC, id ASC
                LIMIT ?
                """,
                (limit,),
            )
        )
        claimed = []
        for row in rows:
            token = secrets.token_urlsafe(24)
            conn.execute(
                """
                UPDATE source_items
                SET publish_status = 'claimed', publish_claimed_at = ?, publish_claim_token = ?, updated_at = ?
                WHERE id = ? AND publish_status = 'confirmed'
                """,
                (ts, token, ts, row["id"]),
            )
            fresh = get_item(conn, int(row["id"]))
            if fresh:
                claimed.append((fresh, token))
        conn.commit()
        return claimed
    except Exception:
        conn.rollback()
        raise


def save_publish_result(conn: sqlite3.Connection, item_id: int, claim_token: str, status: str, error: str = "") -> bool:
    if status not in {"published", "failed"}:
        raise ValueError("status must be published or failed")
    ts = now()
    cur = conn.execute(
        """
        UPDATE source_items
        SET publish_status = ?, publish_result_at = ?, publish_error = ?, updated_at = ?
        WHERE id = ? AND publish_status = 'claimed' AND publish_claim_token = ?
        """,
        (status, ts, error, ts, item_id, claim_token),
    )
    conn.commit()
    return int(cur.rowcount) == 1


def items_for_work_date(conn: sqlite3.Connection, work_date: str = "") -> list[sqlite3.Row]:
    feed_order = "COALESCE(NULLIF(observed_at, ''), NULLIF(published_at, ''), created_at)"
    if not work_date:
        return list(conn.execute(f"SELECT * FROM source_items ORDER BY work_date DESC, {feed_order} DESC, id DESC"))
    return list(conn.execute(f"SELECT * FROM source_items WHERE work_date = ? ORDER BY {feed_order} DESC, id DESC", (work_date,)))


def today_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return items_for_work_date(conn, work_today())


def get_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_items WHERE id = ?", (item_id,)).fetchone()


def existing_item_id(conn: sqlite3.Connection, item: dict[str, Any]) -> int | None:
    content_hash = hash_text(f"{item.get('title', '')}\n{item.get('text', '')}")
    row = conn.execute(
        """
        SELECT id FROM source_items
        WHERE source = ?
          AND (
            (? != '' AND source_id = ?)
            OR (? != '' AND url = ?)
            OR content_hash = ?
          )
        LIMIT 1
        """,
        (item["source"], item.get("source_id", ""), item.get("source_id", ""), item.get("url", ""), item.get("url", ""), content_hash),
    ).fetchone()
    return int(row["id"]) if row else None


def get_state(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else ""


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def record_sync_run(conn: sqlite3.Connection, kind: str, result: Any) -> None:
    conn.execute(
        """
        INSERT INTO sync_runs(kind, batch, fetched, inserted, duplicates, filtered, generated, skipped, errors, created_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kind,
            result.batch,
            result.fetched,
            result.inserted,
            result.duplicates,
            result.filtered,
            result.generated,
            1 if result.skipped else 0,
            json.dumps(result.errors, ensure_ascii=False),
            now(),
        ),
    )
    conn.commit()


def recent_sync_runs(conn: sqlite3.Connection, limit: int = 8) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)))
