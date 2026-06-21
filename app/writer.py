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


def mostly_english(value: str) -> bool:
    ascii_letters = sum(ch.isascii() and ch.isalpha() for ch in value)
    cjk = sum("\u4e00" <= ch <= "\u9fff" for ch in value)
    return ascii_letters > 20 and ascii_letters > cjk * 3


def localized_source(item: dict[str, object]) -> tuple[str, str]:
    title = str(item.get("title", ""))
    text = str(item.get("text", ""))
    if not mostly_english(f"{title}\n{text}"):
        return title, text

    lower = f"{title}\n{text}".lower()
    if "ai capex" in lower and ("margin" in lower or "free cash flow" in lower):
        return (
            "海外投资者讨论 AI 资本开支是否正在变成利润率风险",
            "英文社区的核心争论是：大型科技公司的 AI 基础设施投入还能不能继续上行，还是会开始压低自由现金流和利润率。这个线索更像是在提醒市场，AI 叙事不能只看收入想象，也要看资本开支和现金流承压。",
        )
    return (
        "海外投资者讨论一条英文市场线索",
        "这条英文来源需要先转成中文投资语境：不要照搬原文句子，先提炼它讨论的资产、风险、现金流、利润率或风险偏好变化，再判断它和中文市场读者有什么关系。",
    )


def fake_writer(item: dict[str, object]) -> str:
    title, text = localized_source(item)
    source = str(item.get("source", ""))
    # ponytail: deterministic local writer, replace with DeepSeek only when credentials exist.
    return f"【待审仿写】{title}\n\n这条来自 {source}，核心不是热闹，是信号本身。\n\n{text}\n\n先别急着下结论，等真实数据和价格反应互相验证。"


def deepseek_writer(item: dict[str, object]) -> str:
    validate_deepseek_key()
    source_text = f"# {item.get('title', '')}\n\n来源：{item.get('source', '')}\n作者：{item.get('author', '')}\n链接：{item.get('url', '')}\n\n语言处理：如果来源是英文，先转写成自然中文投资语境，不要在成稿里保留英文原句；如果来源是中文，保留原语境并重写。\n\n{item.get('text', '')}\n"
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
