"use client";

import { useEffect, useMemo, useState } from "react";
import { Input } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import type { LibraryItem } from "@/lib/libraryTypes";
import {
  prepareLibraryList,
  type LibraryListDensity,
  type LibraryListFilter,
} from "@/lib/libraryListUtils";
import { libraryApi } from "@/lib/api";
import { LibraryRefCard } from "./LibraryRefCard";

const FILTER_CHIPS: { value: LibraryListFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "fulltext", label: "有全文" },
  { value: "failed", label: "失败" },
  { value: "starred", label: "收藏" },
];

type Props = {
  items: LibraryItem[];
  selectedId?: string | null;
  onSelect: (id: string) => void;
  onOpenFullText?: (id: string) => void;
  activeSessionId?: string | null;
  showSessionFilter?: boolean;
  showDensityToggle?: boolean;
  emptyHint?: string;
  onListIndexMap?: (map: Record<string, number>) => void;
  onStarChange?: (item: LibraryItem) => void;
  onDelete?: (id: string) => void | Promise<void>;
  onShowReviews?: (id: string) => void;
};

export function LiteratureListPanel({
  items,
  selectedId,
  onSelect,
  onOpenFullText,
  activeSessionId,
  showSessionFilter = false,
  showDensityToggle = false,
  emptyHint = "暂无文献",
  onListIndexMap,
  onStarChange,
  onDelete,
  onShowReviews,
}: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<LibraryListFilter>("all");
  const [tagFilters, setTagFilters] = useState<string[]>([]);
  const [density, setDensity] = useState<LibraryListDensity>("comfortable");
  const [tagCatalog, setTagCatalog] = useState<{ name: string; count: number }[]>([]);

  useEffect(() => {
    void libraryApi
      .tags()
      .then((res) => setTagCatalog(res.tags || []))
      .catch(() => setTagCatalog([]));
  }, [items]);

  const filterChips = useMemo(() => {
    if (showSessionFilter && activeSessionId) {
      return [
        ...FILTER_CHIPS.slice(0, 1),
        { value: "session" as LibraryListFilter, label: "本会话" },
        ...FILTER_CHIPS.slice(1),
      ];
    }
    return FILTER_CHIPS;
  }, [showSessionFilter, activeSessionId]);

  const filtered = useMemo(
    () =>
      prepareLibraryList(items, {
        query,
        filter,
        sessionId:
          filter === "session" ? activeSessionId || undefined : undefined,
        tagFilters,
        groupFailedFirst: true,
      }),
    [items, query, filter, activeSessionId, tagFilters],
  );

  const toggleTagFilter = (name: string) => {
    setTagFilters((prev) =>
      prev.includes(name) ? prev.filter((t) => t !== name) : [...prev, name],
    );
  };

  useEffect(() => {
    if (!onListIndexMap) return;
    const map: Record<string, number> = {};
    filtered.forEach((item, i) => {
      map[item.id] = i + 1;
    });
    onListIndexMap(map);
  }, [filtered, onListIndexMap]);

  return (
    <div className="literature-list-panel">
      <div className="literature-list-panel__toolbar">
        <Input
          allowClear
          size="small"
          prefix={<SearchOutlined />}
          placeholder="搜索文献…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="搜索文献"
        />
        <div className="literature-list-panel__filters" role="group" aria-label="筛选">
          {filterChips.map((chip) => (
            <button
              key={chip.value}
              type="button"
              className={`library-filter-chip${
                filter === chip.value ? " library-filter-chip--active" : ""
              }`}
              onClick={() => setFilter(chip.value)}
            >
              {chip.label}
            </button>
          ))}
        </div>
        {showDensityToggle && (
          <div className="literature-list-panel__density" role="group" aria-label="列表密度">
            <button
              type="button"
              className={`library-density-btn${
                density === "comfortable" ? " library-density-btn--active" : ""
              }`}
              onClick={() => setDensity("comfortable")}
            >
              舒适
            </button>
            <button
              type="button"
              className={`library-density-btn${
                density === "compact" ? " library-density-btn--active" : ""
              }`}
              onClick={() => setDensity("compact")}
            >
              紧凑
            </button>
          </div>
        )}
      </div>
      {tagCatalog.length > 0 && (
        <div
          className="literature-list-panel__tag-filters"
          role="group"
          aria-label="按标签筛选"
        >
          {tagCatalog.map((t) => (
            <button
              key={t.name}
              type="button"
              className={`library-filter-chip library-filter-chip--tag${
                tagFilters.includes(t.name) ? " library-filter-chip--active" : ""
              }`}
              onClick={() => toggleTagFilter(t.name)}
            >
              {t.name}
              <span className="library-filter-chip__count">{t.count}</span>
            </button>
          ))}
          {tagFilters.length > 0 && (
            <button
              type="button"
              className="library-filter-chip library-filter-chip--clear"
              onClick={() => setTagFilters([])}
            >
              清除标签
            </button>
          )}
        </div>
      )}
      <p className="literature-list-panel__count">
        {filtered.length} / {items.length} 条
      </p>
      {filtered.length === 0 ? (
        <p className="functional-card__empty">{emptyHint}</p>
      ) : (
        <ul
          className={`library-ref-list library-ref-list--${density}`}
          aria-label="文献列表"
        >
          {filtered.map((item, i) => (
            <LibraryRefCard
              key={item.id}
              item={item}
              listIndex={i + 1}
              density={density}
              selected={selectedId === item.id}
              onSelect={() => onSelect(item.id)}
              onOpenFullText={() => {
                onSelect(item.id);
                onOpenFullText?.(item.id);
              }}
              onShowReviews={() => {
                onSelect(item.id);
                onShowReviews?.(item.id);
              }}
              onStarChange={onStarChange}
              onDelete={onDelete ? () => onDelete(item.id) : undefined}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
