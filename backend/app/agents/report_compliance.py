FOOTER_MD = """

---

*数据来源：Tavily 检索摘要与 Jina Reader 网页摘录。本工具仅供研究辅助，请自行核实引用并遵守各出版商使用条款。*
"""


def append_compliance_footer(text: str) -> str:
    if FOOTER_MD.strip() in text:
        return text
    return text.rstrip() + FOOTER_MD
