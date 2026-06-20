from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app import adapters, db, writer
from app.config import Config


@dataclass
class SyncResult:
    batch: str
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    generated: int = 0
    errors: list[str] = field(default_factory=list)


def run_sync(config: Config) -> SyncResult:
    config.validate_for_web()
    batch = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = SyncResult(batch=batch)
    conn = db.connect(config.db_path)
    db.init_db(conn)
    try:
        for source in config.sources:
            try:
                items = adapters.fetch_source(source)
                result.fetched += len(items)
            except Exception as exc:  # adapter errors should not hide other sources
                result.errors.append(f"{source}: {exc}")
                continue

            for item in items:
                item_id, inserted = db.insert_source_item(conn, item, batch)
                if not inserted:
                    result.duplicates += 1
                    continue
                result.inserted += 1
                try:
                    copy = writer.generate_copy(item, config)
                    db.save_generation(conn, item_id, copy)
                    result.generated += 1
                except Exception as exc:
                    db.save_generation(conn, item_id, "", str(exc))
                    result.errors.append(f"{source}/{item.get('source_id', item_id)}: {exc}")
    finally:
        conn.close()
    return result
