"""Tavily API key format checks."""
from __future__ import annotations


def looks_like_tavily_api_key(key: str) -> bool:
    k = (key or "").strip()
    return k.startswith("tvly-")


def tavily_key_hint(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return "未配置 Tavily API Key。"
    if k.startswith("sk-"):
        return (
            "当前 Key 以 sk- 开头，像是其他平台（如 OpenAI）的密钥，不是 Tavily。"
            "请到 https://tavily.com 注册并在控制台复制以 tvly- 开头的 Key。"
        )
    if not looks_like_tavily_api_key(k):
        return (
            "Tavily Key 通常以 tvly- 开头。"
            "请确认粘贴的是 Tavily 控制台中的 API Key，而非 Jina / OpenAI 等密钥。"
        )
    return ""
