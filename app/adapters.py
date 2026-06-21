from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import Config


class AdapterConfigError(RuntimeError):
    pass


def mock_observed_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mock_xueqiu() -> list[dict[str, object]]:
    return [
        {
            "source": "mock-xueqiu",
            "source_id": "xq-2026-06-20-001",
            "url": "https://xueqiu.example/status/001",
            "title": "央行继续净投放，短端资金利率回落",
            "text": "央行公开市场延续净投放，隔夜资金价格回落。交易员称，跨季预期仍在，但短端压力比上周缓和。",
            "author": "雪球宏观观察",
            "published_at": "2026-06-20T09:00:00+08:00",
            "observed_at": mock_observed_at(),
            "media_urls": ["/static/mock-liquidity.svg"],
        },
        {
            "source": "mock-xueqiu",
            "source_id": "xq-2026-06-20-002",
            "url": "https://xueqiu.example/status/002",
            "title": "消费电子链午后走强",
            "text": "多只消费电子链公司午后拉升。市场讨论集中在补库存、端侧 AI 和三季度新品备货。",
            "author": "雪球市场热帖",
            "published_at": "2026-06-20T13:30:00+08:00",
            "observed_at": mock_observed_at(),
            "media_urls": [],
        },
    ]


def mock_reddit() -> list[dict[str, object]]:
    return [
        {
            "source": "mock-reddit",
            "source_id": "rd-2026-06-20-001",
            "url": "https://reddit.example/r/investing/comments/001",
            "title": "Investors debate whether AI capex is becoming a margin risk",
            "text": "A thread on large-cap tech asks whether AI infrastructure spending can keep rising without pressuring free cash flow.",
            "author": "r/investing",
            "published_at": "2026-06-20T02:00:00Z",
            "observed_at": mock_observed_at(),
            "media_urls": ["/static/mock-capex.svg"],
        }
    ]


def fetch_health(config: Config) -> dict[str, object]:
    with urlopen(f"{config.export_base_url.rstrip('/')}/api/health", timeout=20) as response:
        return json.load(response)


def fetch_export(config: Config, sources: list[str], limit: int = 500) -> list[dict[str, object]]:
    token = config.news_harness_token()
    if not token:
        raise AdapterConfigError("NEWS_HARNESS_EXPORT_TOKEN or NEWS_HARNESS_EXPORT_TOKEN_FILE is required")
    query = urlencode({"source": ",".join(sources), "limit": str(limit)})
    req = Request(
        f"{config.export_base_url.rstrip('/')}/api/export/v1/items?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urlopen(req, timeout=30) as response:
        payload = json.load(response)
    return [normalize_export_item(item) for item in payload.get("items", [])]


def normalize_export_item(item: dict[str, object]) -> dict[str, object]:
    text = str(item.get("copy_text", ""))
    return {
        "source": str(item.get("source", "")),
        "source_id": str(item.get("id", "")),
        "url": str(item.get("source_url", "")),
        "title": text.splitlines()[0][:80] if text else str(item.get("id", "")),
        "text": text,
        "author": "",
        "published_at": str(item.get("published_at", "")),
        "observed_at": str(item.get("observed_at") or item.get("fetched_at") or item.get("published_at", "")),
        "media_urls": item.get("image_refs", []) or [],
    }


def fetch_source(name: str) -> list[dict[str, object]]:
    if name == "mock-xueqiu":
        return mock_xueqiu()
    if name == "mock-reddit":
        return mock_reddit()
    if name in {"xueqiu", "reddit"}:
        raise AdapterConfigError("real xueqiu/reddit are fetched together through health-gated export")
    raise AdapterConfigError(f"unknown source adapter: {name}")
