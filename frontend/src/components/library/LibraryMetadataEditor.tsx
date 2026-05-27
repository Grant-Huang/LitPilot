"use client";

import { useCallback, useEffect, useState } from "react";
import { Input, message } from "antd";
import { libraryApi } from "@/lib/api";
import type { LibraryItem } from "@/lib/libraryTypes";

type Props = {
  item: LibraryItem;
  onChange: (item: LibraryItem) => void;
};

export function LibraryMetadataEditor({ item, onChange }: Props) {
  const [doiDraft, setDoiDraft] = useState(item.doi || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDoiDraft(item.doi || "");
  }, [item.id, item.doi]);

  const saveDoi = useCallback(async () => {
    const doi = doiDraft.trim();
    setSaving(true);
    try {
      const res = await libraryApi.updateMetadata(item.id, {
        doi: doi || undefined,
        refresh_crossref: Boolean(doi),
      });
      onChange(res.item);
      message.success(doi ? "DOI 已保存，已从 Crossref 补全书目与被引/他引" : "DOI 已清除");
    } catch {
      message.error("保存 DOI 失败");
    } finally {
      setSaving(false);
    }
  }, [doiDraft, item.id, onChange]);

  const refreshCrossref = useCallback(async () => {
    if (!item.doi && !doiDraft.trim()) {
      message.info("请先填写 DOI");
      return;
    }
    setSaving(true);
    try {
      const res = await libraryApi.enrich(item.id);
      if (res.item) {
        onChange(res.item);
        message.success(
          `已更新：被引 ${res.citation_count ?? "—"}，他引 ${res.references_count ?? "—"}`,
        );
      }
    } catch {
      message.error("Crossref 补全失败");
    } finally {
      setSaving(false);
    }
  }, [item.doi, item.id, doiDraft, onChange]);

  return (
    <div className="library-metadata-editor">
      <label className="library-metadata-editor__label" htmlFor={`doi-${item.id}`}>
        DOI
      </label>
      <div className="library-metadata-editor__row">
        <Input
          id={`doi-${item.id}`}
          size="small"
          value={doiDraft}
          placeholder="10.xxxx/xxxxx"
          onChange={(e) => setDoiDraft(e.target.value)}
          onPressEnter={() => void saveDoi()}
        />
        <button
          type="button"
          className="btn-ghost"
          disabled={saving}
          onClick={() => void saveDoi()}
        >
          保存
        </button>
        <button
          type="button"
          className="btn-ghost"
          disabled={saving || (!item.doi && !doiDraft.trim())}
          onClick={() => void refreshCrossref()}
        >
          从 Crossref 刷新
        </button>
      </div>
      <p className="library-detail__hint">
        无 DOI 时可手工补充；保存后将自动查询被引与他引（参考文献条数）。
      </p>
    </div>
  );
}
