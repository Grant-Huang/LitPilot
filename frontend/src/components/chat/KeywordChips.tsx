"use client";

import { parseSearchKeywords } from "@/lib/searchProgressTree";

/**
 * 把检索查询串渲染成关键词 chip，取代原先直接糊在界面上的引号查询串
 * （如 `"AI-native" "manufacturing operations management"`）。
 */
export function KeywordChips({ query }: { query: string }) {
  const chips = parseSearchKeywords(query);
  if (!chips.length) return null;
  return (
    <ul className="lp-kw-chips">
      {chips.map((kw, i) => (
        <li key={`${kw}-${i}`} className="lp-kw-chip">
          {kw}
        </li>
      ))}
    </ul>
  );
}
