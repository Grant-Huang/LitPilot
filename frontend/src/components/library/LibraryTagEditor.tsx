"use client";

import { useMemo, useState } from "react";
import { Input, message } from "antd";
import { normalizeTag, normalizeTags } from "@/lib/libraryTags";
import { libraryApi } from "@/lib/api";
import type { LibraryItem } from "@/lib/libraryTypes";

type TagOption = { name: string; count: number };

type Props = {
  item: LibraryItem;
  suggestions?: TagOption[];
  onChange?: (item: LibraryItem) => void;
  compact?: boolean;
};

export function LibraryTagEditor({
  item,
  suggestions = [],
  onChange,
  compact = false,
}: Props) {
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const tags = useMemo(() => item.tags || [], [item.tags]);

  const suggestSet = useMemo(() => {
    const current = new Set(tags.map((t) => t.toLowerCase()));
    return suggestions.filter((s) => !current.has(s.name.toLowerCase()));
  }, [suggestions, tags]);

  const persist = async (next: string[]) => {
    setSaving(true);
    try {
      const res = await libraryApi.updateTags(item.id, next);
      onChange?.(res.item);
    } catch {
      message.error("保存标签失败");
    } finally {
      setSaving(false);
    }
  };

  const addTag = (raw: string) => {
    const tag = normalizeTag(raw);
    if (!tag) return;
    const next = normalizeTags([...tags, tag]);
    if (next.length === tags.length) return;
    void persist(next);
    setDraft("");
  };

  const removeTag = (tag: string) => {
    void persist(tags.filter((t) => t !== tag));
  };

  return (
    <div
      className={`library-tag-editor${compact ? " library-tag-editor--compact" : ""}`}
    >
      <div className="library-tag-editor__chips">
        {tags.length === 0 && (
          <span className="library-detail__muted">暂无标签，输入后回车添加</span>
        )}
        {tags.map((tag) => (
          <span key={tag} className="library-item-tag">
            {tag}
            <button
              type="button"
              className="library-item-tag__remove"
              aria-label={`移除标签 ${tag}`}
              disabled={saving}
              onClick={() => removeTag(tag)}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <Input
        size="small"
        disabled={saving}
        placeholder="添加标签，回车确认"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onPressEnter={() => addTag(draft)}
        aria-label="新标签"
      />
      {suggestSet.length > 0 && (
        <div className="library-tag-editor__suggest" role="listbox" aria-label="已有标签">
          {suggestSet.slice(0, 12).map((s) => (
            <button
              key={s.name}
              type="button"
              className="library-tag-suggest"
              disabled={saving}
              onClick={() => addTag(s.name)}
            >
              {s.name}
              <span className="library-tag-suggest__count">{s.count}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
