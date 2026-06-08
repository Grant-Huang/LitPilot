"""综述正文引用 [n] 校验：识别越界、未引用、未验证的引用。

Task 4 of 5：用 OpenAlex 已有元数据对 review 正文里的 ``[n]`` 引用做对照，
防止 LLM 编造或错位引用。

校验范围（不引入新的网络调用，使用 ``cite_records`` 中已 OpenAlex/Crossref
解析过的元数据）：
- 引用编号越界：n 不在 ``1..len(cite_records)``
- 元数据未验证：``cite_records[n-1].success`` 为 False（DOI/Crossref/OpenAlex
  都未能确认），意味着该引用条目本身就是不可靠的，引用它要醒目提示
- 未被引用：cite_records 中存在但正文中从未出现 ``[n]``，记入报告
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# 形如 [1]、[2-4]、[1, 3]、[1,3,5] 的引用占位
_CITE_NUM = re.compile(r"\[(\d+(?:\s*[-–,，、]\s*\d+)*)\]")
_NUMBER = re.compile(r"\d+")


def _expand_cite_token(token: str) -> list[int]:
    """[1-3] → [1,2,3]；[1, 3] → [1,3]；[10] → [10]。"""
    nums: list[int] = []
    # 先按分隔符切，再处理范围
    raw = re.split(r"[,，、]\s*", token)
    for part in raw:
        rng = re.split(r"\s*[-–]\s*", part)
        if len(rng) == 2 and rng[0].isdigit() and rng[1].isdigit():
            a, b = int(rng[0]), int(rng[1])
            if 0 < a <= b <= 9999:
                nums.extend(range(a, b + 1))
                continue
        m = _NUMBER.match(part.strip())
        if m:
            nums.append(int(m.group(0)))
    return nums


def extract_cited_indices(review_text: str) -> list[int]:
    """提取正文中所有 ``[n]`` 引用编号（按出现顺序，可重复）。"""
    out: list[int] = []
    for m in _CITE_NUM.finditer(review_text or ""):
        out.extend(_expand_cite_token(m.group(1)))
    return out


@dataclass
class CitationAuditReport:
    total_records: int = 0
    total_refs: int = 0
    unique_cited: list[int] = field(default_factory=list)
    out_of_range: list[int] = field(default_factory=list)
    unverified: list[dict[str, str]] = field(default_factory=list)
    uncited: list[int] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.out_of_range or self.unverified)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "total_refs": self.total_refs,
            "unique_cited": sorted(set(self.unique_cited)),
            "out_of_range": sorted(set(self.out_of_range)),
            "unverified": list(self.unverified),
            "uncited": sorted(set(self.uncited)),
            "has_issues": self.has_issues,
        }

    def footer_lines(self) -> list[str]:
        if not (self.has_issues or self.uncited):
            return []
        lines: list[str] = ["", "> **引用校验**"]
        if self.out_of_range:
            arr = "、".join(f"[{n}]" for n in sorted(set(self.out_of_range)))
            lines.append(f"> - 越界引用（已收录文献仅 {self.total_records} 条）：{arr}")
        if self.unverified:
            arr = "、".join(
                f"[{u['index']}] {u.get('title', '')[:48]}".rstrip()
                for u in self.unverified[:8]
            )
            more = "" if len(self.unverified) <= 8 else f"（另有 {len(self.unverified) - 8} 条）"
            lines.append(f"> - 元数据未通过 DOI/OpenAlex 验证：{arr}{more}")
        if self.uncited:
            arr = "、".join(f"[{n}]" for n in sorted(set(self.uncited))[:12])
            more = "" if len(self.uncited) <= 12 else f"（另有 {len(self.uncited) - 12} 条）"
            lines.append(f"> - 正文未引用的已收录文献：{arr}{more}")
        return lines


def audit_review_citations(
    review_text: str,
    cite_records: Iterable[Any],
) -> CitationAuditReport:
    """对 ``review_text`` 中的 ``[n]`` 引用做静态校验。

    依赖 ``CitationRecord`` 已具有的 ``success`` / ``title`` 字段；不发起新的
    网络调用（OpenAlex 已在 citation_extractor 阶段查询过）。
    """
    records = list(cite_records)
    n_records = len(records)
    cited = extract_cited_indices(review_text or "")

    out_of_range: list[int] = []
    unverified_set: dict[int, dict[str, str]] = {}
    cited_set: set[int] = set()
    for n in cited:
        if not (1 <= n <= n_records):
            out_of_range.append(n)
            continue
        cited_set.add(n)
        rec = records[n - 1]
        success = bool(getattr(rec, "success", False))
        if not success and n not in unverified_set:
            unverified_set[n] = {
                "index": str(n),
                "title": str(getattr(rec, "title", "") or "")[:120],
                "url": str(getattr(rec, "url", "") or ""),
                "error": str(getattr(rec, "error", "") or "")[:80],
            }

    uncited = [i for i in range(1, n_records + 1) if i not in cited_set]
    return CitationAuditReport(
        total_records=n_records,
        total_refs=len(cited),
        unique_cited=sorted(cited_set),
        out_of_range=out_of_range,
        unverified=list(unverified_set.values()),
        uncited=uncited,
    )
