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
    skipped: bool = False
    errors: list[str] = field(default_factory=list)


def run_sync(config: Config) -> SyncResult:
    config.validate_for_web()
    batch = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = SyncResult(batch=batch)
    conn = db.connect(config.db_path)
    db.init_db(conn)
    try:
        sources = list(config.sources)
        real_sources = [s for s in sources if s in {"xueqiu", "reddit"}]
        mock_sources = [s for s in sources if s not in {"xueqiu", "reddit"}]

        if real_sources:
            try:
                health = adapters.fetch_health(config)
                generated_at = str(health.get("generated_at", ""))
                state_key = "news_harness_generated_at:" + ",".join(sorted(real_sources))
                if generated_at and generated_at == db.get_state(conn, state_key):
                    result.skipped = True
                else:
                    items = adapters.fetch_export(config, real_sources)
                    result.fetched += len(items)
                    process_items(conn, config, batch, result, items)
                    if generated_at:
                        db.set_state(conn, state_key, generated_at)
            except Exception as exc:
                result.errors.append(f"news-harness: {exc}")

        for source in mock_sources:
            try:
                items = adapters.fetch_source(source)
                result.fetched += len(items)
            except Exception as exc:  # adapter errors should not hide other sources
                result.errors.append(f"{source}: {exc}")
                continue
            process_items(conn, config, batch, result, items)
    finally:
        conn.close()
    return result


def process_items(conn, config: Config, batch: str, result: SyncResult, items: list[dict[str, object]]) -> None:
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
            result.errors.append(f"{item.get('source')}/{item.get('source_id', item_id)}: {exc}")
