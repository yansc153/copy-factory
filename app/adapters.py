from __future__ import annotations


class AdapterConfigError(RuntimeError):
    pass


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
            "media_urls": ["https://xueqiu.example/chart/liquidity.png"],
        },
        {
            "source": "mock-xueqiu",
            "source_id": "xq-2026-06-20-002",
            "url": "https://xueqiu.example/status/002",
            "title": "消费电子链午后走强",
            "text": "多只消费电子链公司午后拉升。市场讨论集中在补库存、端侧 AI 和三季度新品备货。",
            "author": "雪球市场热帖",
            "published_at": "2026-06-20T13:30:00+08:00",
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
            "media_urls": ["https://reddit.example/media/capex-table.jpg"],
        }
    ]


def real_adapter(name: str) -> list[dict[str, object]]:
    raise AdapterConfigError(
        f"{name} adapter needs endpoint/credential wiring. Set COPY_FACTORY_SOURCES to mock-xueqiu,mock-reddit until ready."
    )


def fetch_source(name: str) -> list[dict[str, object]]:
    if name == "mock-xueqiu":
        return mock_xueqiu()
    if name == "mock-reddit":
        return mock_reddit()
    if name in {"xueqiu", "reddit"}:
        return real_adapter(name)
    raise AdapterConfigError(f"unknown source adapter: {name}")
