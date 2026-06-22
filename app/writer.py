from __future__ import annotations

import os
import json
from pathlib import Path
from urllib.request import Request, urlopen

from app.config import Config


def has_deepseek_key() -> bool:
    key_file = os.getenv("DEEPSEEK_API_KEY_FILE", "")
    return bool(os.getenv("DEEPSEEK_API_KEY") or (key_file and Path(key_file).exists()))


def deepseek_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    key_file = os.getenv("DEEPSEEK_API_KEY_FILE", "").strip()
    if key:
        return key
    return Path(key_file).read_text(encoding="utf-8").strip() if key_file else ""


def validate_deepseek_key() -> None:
    key = deepseek_key()
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
    prompt = f"""把下面素材改写成一篇可以直接发布的中文投资社媒正文。

要求：
- 如果来源是英文，在内部先翻译和理解，再输出自然中文，不要保留英文原句。
- 如果来源已经是中文，也要重新组织成完整观点，不要摘抄原文或只做摘要。
- 不要逐句翻译，不要套模板，提炼资产、风险、资金流、情绪或交易含义。
- 口吻直接，短段落，适合 Copy Factory 审核后发布。
- 只输出最终正文，不要写“标题：”“来源：”“核心提醒：”这类字段名，不要解释写作过程。
- 不要编造原文没有的信息。

标题：{item.get('title', '')}
来源：{item.get('source', '')}
作者：{item.get('author', '')}
链接：{item.get('url', '')}

原文：
{item.get('text', '')}
"""
    payload = json.dumps(
        {
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": "你是中文投资社媒写手，负责把市场素材改写成自然、克制、有判断力的中文稿。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        },
        ensure_ascii=False,
    ).encode()
    req = Request(
        os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/chat/completions"),
        data=payload,
        headers={"Authorization": f"Bearer {deepseek_key()}", "Content-Type": "application/json"},
    )
    timeout = int(os.getenv("DEEPSEEK_WRITER_TIMEOUT_SECONDS", "90"))
    with urlopen(req, timeout=timeout) as response:
        data = json.load(response)
    return str(data["choices"][0]["message"]["content"]).strip()


def generate_copy(item: dict[str, object], config: Config) -> tuple[str, str]:
    if has_deepseek_key():
        return deepseek_writer(item), "deepseek"
    if config.is_production:
        raise RuntimeError("production generation requires DEEPSEEK_API_KEY or DEEPSEEK_API_KEY_FILE")
    return fake_writer(item), "local"
