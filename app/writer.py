from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from app.config import Config


HUAJIAO_SCRIPT = "/Users/oxjames/.codex/skills/huajiao-finance-writer/scripts/deepseek_generate.py"


def has_deepseek_key() -> bool:
    key_file = os.getenv("DEEPSEEK_API_KEY_FILE", "")
    return bool(os.getenv("DEEPSEEK_API_KEY") or (key_file and Path(key_file).exists()))


def validate_deepseek_key() -> None:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key and not key.startswith("sk-"):
        raise RuntimeError("DEEPSEEK_API_KEY looks invalid; expected it to start with sk-")


def fake_writer(item: dict[str, object]) -> str:
    title = str(item.get("title", ""))
    text = str(item.get("text", ""))
    source = str(item.get("source", ""))
    # ponytail: deterministic local writer, replace with DeepSeek only when credentials exist.
    return f"【待审仿写】{title}\n\n这条来自 {source}，核心不是热闹，是信号本身。\n\n{text}\n\n先别急着下结论，等真实数据和价格反应互相验证。"


def deepseek_writer(item: dict[str, object]) -> str:
    validate_deepseek_key()
    source_text = f"# {item.get('title', '')}\n\n来源：{item.get('source', '')}\n作者：{item.get('author', '')}\n链接：{item.get('url', '')}\n\n{item.get('text', '')}\n"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "source.md"
        out = Path(tmp) / "out.md"
        src.write_text(source_text, encoding="utf-8")
        env = os.environ.copy()
        env["VOICE_OUTPUT_MODE"] = "long-social"
        result = subprocess.run(["python3", HUAJIAO_SCRIPT, str(src), str(out)], env=env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or "DeepSeek writer failed")[-800:])
        return out.read_text(encoding="utf-8")


def generate_copy(item: dict[str, object], config: Config) -> str:
    if has_deepseek_key():
        return deepseek_writer(item)
    if config.is_production:
        raise RuntimeError("production generation requires DEEPSEEK_API_KEY or DEEPSEEK_API_KEY_FILE")
    return fake_writer(item)
