"use client";

import { useMemo, useState } from "react";
import { Input, Select } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import type { LibraryItem } from "@/lib/libraryTypes";
import {
  prepareLibraryList,
  type LibraryListDensity,
  type LibraryListFilter,
} from "@/lib/libraryListUtils";
import { LibraryRefCard } from "./LibraryRefCard";

type Props = {
  items: LibraryItem[];
  selectedId?: string | null;
  onSelect: (id: string) => void;
  onOpenFullText?: (id: string) => void;
  activeSessionId?: string | null;
  showSessionFilter?: boolean;
  showDensityToggle?: boolean;
  emptyHint?: string;
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
}: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<LibraryListFilter>("all");
  const [density, setDensity] = useState<LibraryListDensity>("comfortable");

  const filtered = useMemo(
    () =>
      prepareLibraryList(items, {
        query,
        filter,
        sessionId:
          filter === "session" ? activeSessionId || undefined : undefined,
        groupFailedFirst: true,
      }),
    [items, query, filter, activeSessionId],
  );

  const filterOptions = [
    { value: "all", label: "全部" },
    ...(showSessionFilter && activeSessionId
      ? [{ value: "session", label: "本会话" }]
      : []),
    { value: "fulltext", label: "有全文" },
    { value: "failed", label: "失败" },
    { value: "starred", label: "收藏" },
  ];

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
        <Select
          size="small"
          value={filter}
          onChange={(v) => setFilter(v as LibraryListFilter)}
          options={filterOptions}
          aria-label="筛选"
        />
        {showDensityToggle && (
          <Select
            size="small"
            value={density}
            onChange={(v) => setDensity(v as LibraryListDensity)}
            options={[
              { value: "comfortable", label: "舒适" },
              { value: "compact", label: "紧凑" },
            ]}
            aria-label="密度"
          />
        )}
      </div>
      <p className="literature-list-panel__count">
        {filtered.length} / {items.length} 条
      </p>
      {filtered.length === 0 ? (
        <p className="functional-card__empty">{emptyHint}</p>
      ) : (
        <ul className="library-ref-list">
          {filtered.map((item) => (
            <LibraryRefCard
              key={item.id}
              item={item}
              density={density}
              selected={selectedId === item.id}
              onSelect={() => onSelect(item.id)}
              onOpenFullText={() => {
                onSelect(item.id);
                onOpenFullText?.(item.id);
              }}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
