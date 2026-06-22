#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, writer
from app.config import Config


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate existing drafts through Huajiao + DeepSeek.")
    parser.add_argument("--source", default="", help="Only regenerate one source, for example reddit or xueqiu_hot.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--include-approved", action="store_true")
    parser.add_argument("--only-error", action="store_true")
    args = parser.parse_args()

    if not writer.has_deepseek_key():
        print("DEEPSEEK_API_KEY or DEEPSEEK_API_KEY_FILE is required", file=sys.stderr)
        return 2

    config = Config()
    conn = db.connect(config.db_path)
    db.init_db(conn)
    try:
        statuses = ("draft", "approved") if args.include_approved else ("draft",)
        sql = """
            SELECT * FROM source_items
            WHERE generation_status != 'deepseek'
              AND publish_status NOT IN ('claimed', 'published')
              AND review_status IN ({})
        """.format(",".join("?" for _ in statuses))
        params: list[object] = list(statuses)
        if args.source:
            sql += " AND source = ?"
            params.append(args.source)
        if args.only_error:
            sql += " AND generation_status = 'error'"
        sql += " ORDER BY id DESC LIMIT ?" if args.only_error else " ORDER BY id ASC LIMIT ?"
        params.append(max(1, args.limit))

        rows = list(conn.execute(sql, params))
        ok = 0
        for row in rows:
            item = dict(row)
            item["media_urls"] = []
            try:
                copy, status = writer.generate_copy(item, config)
                db.save_generation(conn, int(row["id"]), copy, status=status)
                ok += 1
                print(f"regenerated id={row['id']} source={row['source']} status={status}")
            except Exception as exc:
                db.save_generation(conn, int(row["id"]), "", str(exc))
                print(f"error id={row['id']} source={row['source']}: {exc}", file=sys.stderr)
        print(f"done regenerated={ok} candidates={len(rows)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
