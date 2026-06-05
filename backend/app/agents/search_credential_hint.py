"""Format hints for web_search / web_fetch credential secrets."""
from __future__ import annotations


def looks_like_tavily_secret(key: str) -> bool:
    k = (key or "").strip()
    return k.startswith("tvly-")


def _tavily_secret_hint(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return "未配置 web_search API Key。"
    if k.startswith("sk-"):
        return (
            "当前 Key 以 sk- 开头，像是其他平台（如 OpenAI）的密钥，不是 Tavily 检索凭据。"
            "请到 https://tavily.com 注册并在控制台复制以 tvly- 开头的 Key。"
        )
    if not looks_like_tavily_secret(k):
        return (
            "web_search（Tavily）凭据通常以 tvly- 开头。"
            "请确认粘贴的是 Tavily 控制台中的 API Key，而非其他平台密钥。"
        )
    return ""


def search_credential_secret_hint(credential_type: str, secret: str) -> str:
    """Return a user-facing hint when secret format looks wrong; empty if OK."""
    ctype = (credential_type or "").strip().lower()
    if ctype == "tavily":
        return _tavily_secret_hint(secret)
    return ""
