#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import adapters, writer


RAW_ENGLISH_FRAGMENTS = (
    "Investors debate",
    "A thread on large-cap tech",
)


def cjk_count(value: str) -> int:
    return sum("\u4e00" <= ch <= "\u9fff" for ch in value)


def require_deepseek_key() -> None:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    key_file = os.getenv("DEEPSEEK_API_KEY_FILE", "").strip()
    if key:
        return
    if key_file and Path(key_file).expanduser().is_file():
        return
    print(
        "DEEPSEEK_API_KEY or DEEPSEEK_API_KEY_FILE is required to run the real DeepSeek writing smoke.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def main() -> None:
    require_deepseek_key()
    item = adapters.mock_reddit()[0]
    generated = writer.deepseek_writer(item).strip()
    if not generated:
        raise RuntimeError("DeepSeek returned empty copy")

    chinese_chars = cjk_count(generated)
    if chinese_chars < 20:
        raise RuntimeError("DeepSeek output did not look like Chinese review copy")

    leaked = [fragment for fragment in RAW_ENGLISH_FRAGMENTS if fragment in generated]
    if leaked:
        raise RuntimeError(f"DeepSeek output kept raw English source fragments: {leaked}")

    evidence = {
        "source": item["source"],
        "source_id": item["source_id"],
        "input_title": item["title"],
        "output_chars": len(generated),
        "cjk_chars": chinese_chars,
        "raw_english_absent": True,
        "preview": generated[:240],
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
