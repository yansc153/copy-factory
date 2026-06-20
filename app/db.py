from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
            media_urls TEXT NOT NULL DEFAULT '[]',
            content_hash TEXT NOT NULL,
            sync_batch TEXT NOT NULL,
            generation_status TEXT NOT NULL DEFAULT 'pending',
            generation_error TEXT NOT NULL DEFAULT '',
            generated_copy TEXT NOT NULL DEFAULT '',
            review_status TEXT NOT NULL DEFAULT 'draft',
            edited_copy TEXT NOT NULL DEFAULT '',
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
        """
    )
    conn.commit()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def insert_source_item(conn: sqlite3.Connection, item: dict[str, Any], sync_batch: str) -> tuple[int, bool]:
    media_urls = json.dumps(item.get("media_urls", []), ensure_ascii=False)
    content_hash = hash_text(f"{item.get('title', '')}\n{item.get('text', '')}")
    ts = now()
    existing = conn.execute(
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
    if existing:
        return int(existing["id"]), False

    cur = conn.execute(
        """
        INSERT INTO source_items (
            source, source_id, url, title, text, author, published_at, media_urls,
            content_hash, sync_batch, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["source"],
            item.get("source_id", ""),
            item.get("url", ""),
            item.get("title", ""),
            item["text"],
            item.get("author", ""),
            item.get("published_at", ""),
            media_urls,
            content_hash,
            sync_batch,
            ts,
            ts,
        ),
    )
    conn.commit()
    return int(cur.lastrowid), True


def save_generation(conn: sqlite3.Connection, item_id: int, copy: str, error: str = "") -> None:
    status = "error" if error else "generated"
    conn.execute(
        """
        UPDATE source_items
        SET generation_status = ?, generation_error = ?, generated_copy = ?, edited_copy = ?,
            review_status = 'draft', updated_at = ?
        WHERE id = ?
        """,
        (status, error, copy, copy, now(), item_id),
    )
    conn.commit()


def save_review(conn: sqlite3.Connection, item_id: int, edited_copy: str, status: str) -> None:
    if status not in {"draft", "approved", "rejected"}:
        raise ValueError("status must be draft, approved, or rejected")
    conn.execute(
        "UPDATE source_items SET edited_copy = ?, review_status = ?, updated_at = ? WHERE id = ?",
        (edited_copy, status, now(), item_id),
    )
    conn.commit()


def today_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM source_items ORDER BY updated_at DESC, id DESC"))


def get_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_items WHERE id = ?", (item_id,)).fetchone()


def get_state(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else ""


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
