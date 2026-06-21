from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app import adapters, db, writer
from app.config import Config


@dataclass
class SyncResult:
    batch: str
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    filtered: int = 0
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
                skipped = 0
                for source in real_sources:
                    state_key = f"news_harness_generated_at:{source}"
                    if generated_at and generated_at == db.get_state(conn, state_key):
                        skipped += 1
                        continue
                    items = adapters.fetch_export(config, [source], limit=config.export_limit)
                    fetched = len(items)
                    result.fetched += fetched
                    items = filter_by_window(items, config)
                    result.filtered += fetched - len(items)
                    process_items(conn, config, batch, result, items)
                    if generated_at:
                        db.set_state(conn, state_key, generated_at)
                result.skipped = skipped == len(real_sources)
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
        db.record_sync_run(conn, "run", result)
    finally:
        conn.close()
    return result


def preview_sync(config: Config) -> SyncResult:
    config.validate_for_web()
    batch = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = SyncResult(batch=batch)
    conn = db.connect(config.db_path)
    db.init_db(conn)
    try:
        real_sources = [s for s in config.sources if s in {"xueqiu", "reddit"}]
        if not real_sources:
            return result
        health = adapters.fetch_health(config)
        generated_at = str(health.get("generated_at", ""))
        skipped = 0
        for source in real_sources:
            state_key = f"news_harness_generated_at:{source}"
            if generated_at and generated_at == db.get_state(conn, state_key):
                skipped += 1
                continue
            items = adapters.fetch_export(config, [source], limit=config.export_limit)
            fetched = len(items)
            result.fetched += fetched
            items = filter_by_window(items, config)
            result.filtered += fetched - len(items)
            for item in items:
                if db.existing_item_id(conn, item):
                    result.duplicates += 1
                else:
                    result.inserted += 1
        result.skipped = skipped == len(real_sources)
        db.record_sync_run(conn, "preview", result)
        return result
    except Exception as exc:
        result.errors.append(f"preview: {exc}")
        db.record_sync_run(conn, "preview", result)
        return result
    finally:
        conn.close()


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if len(value) == 10:
        value += "T00:00:00+00:00"
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def filter_by_window(items: list[dict[str, Any]], config: Config) -> list[dict[str, Any]]:
    since = parse_time(config.import_since)
    until = parse_time(config.import_until)
    if not since and not until:
        return items
    kept = []
    for item in items:
        published = parse_time(str(item.get("published_at", "")))
        if not published:
            continue
        if since and published < since:
            continue
        if until and published >= until:
            continue
        kept.append(item)
    return kept


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
