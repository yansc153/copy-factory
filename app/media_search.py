from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


MIN_WIDTH = 800
MIN_HEIGHT = 450
MIN_BYTES = 40 * 1024
MIN_RATIO = 1.2
MAX_RATIO = 2.2
MEDIA_DIR = Path("data/media/google")
MEDIA_URL_PREFIX = "/media/google/"
BRAVE_IMAGE_SEARCH_URL = "https://api.search.brave.com/res/v1/images/search"


def search_configured() -> bool:
    return bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip())


def search_query(item: dict[str, object], copy: str = "") -> str:
    text = " ".join(
        str(part or "")
        for part in (
            item.get("title"),
            item.get("text"),
            item.get("source"),
            copy,
        )
    )
    words = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    stop = {
        "https",
        "http",
        "copy",
        "factory",
        "mock",
        "reddit",
        "xueqiu",
        "static",
        "这条",
        "来源",
        "文案",
        "图片",
        "待审仿写",
        "这条来自",
        "核心不是热闹",
        "信号本身",
        "先别急着下结论",
        "真实数据",
        "价格反应",
    }
    picked: list[str] = []
    seen: set[str] = set()
    for word in words:
        if len(word) < 2 or word in stop or word in seen:
            continue
        seen.add(word)
        picked.append(word)
        if len(picked) == 8:
            break
    query_text = " ".join(picked)
    hints: list[str] = []
    if any(term in text for term in ("消费电子", "端侧", "补库存", "新品")):
        hints.append("consumer electronics supply chain stock market news")
    if any(term in text for term in ("AI", "人工智能", "英伟达", "云厂商", "资本开支")):
        hints.append("artificial intelligence technology stocks market news")
    if any(term in text for term in ("央行", "流动性", "利率", "债券", "汇率")):
        hints.append("central bank liquidity financial markets news")
    if hints:
        return " ".join(hints)
    hints.append("finance market news")
    return " ".join([part for part in (query_text, *hints) if part]).strip()


def find_candidates(item: dict[str, object], copy: str = "", limit: int = 3) -> list[str]:
    if not search_configured():
        return []
    query = search_query(item, copy)
    try:
        results = brave_image_results(query)
    except Exception:
        return []
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    urls: list[str] = []
    for result in sorted(results, key=result_score, reverse=True):
        if len(urls) >= limit:
            break
        if not brave_metadata_ok(result):
            continue
        saved = download_candidate(result_image_url(result), query)
        if saved:
            urls.append(saved)
    return urls


def brave_image_results(query: str) -> list[dict[str, object]]:
    params = urlencode(
        {
            "q": query,
            "count": "50",
            "country": "US",
            "search_lang": "en",
            "safesearch": "strict",
        }
    )
    req = Request(f"{BRAVE_IMAGE_SEARCH_URL}?{params}")
    req.add_header("Accept", "application/json")
    req.add_header("Accept-Encoding", "identity")
    req.add_header("User-Agent", "copy-factory/1.0")
    req.add_header("X-Subscription-Token", os.getenv("BRAVE_SEARCH_API_KEY", "").strip())
    with urlopen(req, timeout=20) as response:
        payload = json.load(response)
    return [item for item in payload.get("results", []) if isinstance(item, dict)]


def brave_metadata_ok(result: dict[str, object]) -> bool:
    props = result.get("properties") if isinstance(result.get("properties"), dict) else {}
    width = int(props.get("width") or 0)
    height = int(props.get("height") or 0)
    return dimensions_ok(width, height)


def result_score(result: dict[str, object]) -> tuple[int, int, int]:
    props = result.get("properties") if isinstance(result.get("properties"), dict) else {}
    width = int(props.get("width") or 0)
    height = int(props.get("height") or 0)
    ratio = width / height if height else 0
    return (
        1 if width >= 1200 else 0,
        -int(abs(ratio - (16 / 9)) * 1000),
        width * height,
    )


def result_image_url(result: dict[str, object]) -> str:
    props = result.get("properties") if isinstance(result.get("properties"), dict) else {}
    return str(props.get("url") or result.get("url") or "")


def download_candidate(url: str, query: str) -> str:
    if not url:
        return ""
    try:
        req = Request(url, headers={"User-Agent": "copy-factory/1.0"})
        with urlopen(req, timeout=20) as response:
            data = response.read(8 * 1024 * 1024 + 1)
    except Exception:
        return ""
    if len(data) > 8 * 1024 * 1024 or len(data) < MIN_BYTES:
        return ""
    dims = image_dimensions(data)
    if not dims or not dimensions_ok(*dims):
        return ""
    ext = extension_from_url(url, data)
    name = hashlib.sha256(f"{query}\n{url}".encode("utf-8")).hexdigest()[:24] + ext
    path = MEDIA_DIR / name
    path.write_bytes(data)
    return MEDIA_URL_PREFIX + name


def dimensions_ok(width: int, height: int) -> bool:
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return False
    ratio = width / height
    return MIN_RATIO <= ratio <= MAX_RATIO


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in {0xD8, 0xD9}:
                continue
            if i + 2 > len(data):
                return None
            size = int.from_bytes(data[i : i + 2], "big")
            if marker in range(0xC0, 0xC4) and i + 7 < len(data):
                return int.from_bytes(data[i + 5 : i + 7], "big"), int.from_bytes(data[i + 3 : i + 5], "big")
            i += max(size, 2)
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8X" and len(data) >= 30:
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return width, height
    return None


def extension_from_url(url: str, data: bytes) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if ext == ".jpeg" else ext
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ".img"
