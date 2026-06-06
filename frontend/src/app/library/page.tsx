"use client";

import { useCallback, useEffect, useState } from "react";
import { message } from "antd";
import { FunctionalPageSkeleton } from "@/components/layout/FunctionalPageSkeleton";
import { LibraryDetailPane, type LibraryDetailTab } from "@/components/library/LibraryDetailPane";
import { LiteratureListPanel } from "@/components/library/LiteratureListPanel";
import { libraryApi } from "@/lib/api";
import { loadLibraryItems } from "@/lib/loadLibraryItems";
import type { LibraryItem } from "@/lib/libraryTypes";

export default function LibraryPage() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [listIndexById, setListIndexById] = useState<Record<string, number>>({});
  const [detailTab, setDetailTab] = useState<LibraryDetailTab | undefined>();
  const [refreshingMeta, setRefreshingMeta] = useState(false);

  const load = useCallback(async (opts?: { force?: boolean }) => {
    setLoading(true);
    try {
      const next = await loadLibraryItems({ force: opts?.force });
      setItems(next);
      setSelectedId((prev) => {
        if (prev && next.some((i) => i.id === prev)) return prev;
        return next[0]?.id || null;
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      message.error(msg || "加载文献库失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleItemChange = useCallback((updated: LibraryItem) => {
    setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
  }, []);

  const handleRefreshMetadata = useCallback(async () => {
    setRefreshingMeta(true);
    try {
      const stats = await libraryApi.refreshMetadata({ parallel: 4 });
      await load({ force: true });
      message.success(
        `已刷新 ${stats.updated} 条元数据（跳过 ${stats.skipped} 条）`,
      );
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      message.error(msg || "刷新元数据失败");
    } finally {
      setRefreshingMeta(false);
    }
  }, [load]);

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await libraryApi.delete(id);
        setItems((prev) => {
          const next = prev.filter((i) => i.id !== id);
          setSelectedId((cur) => (cur === id ? next[0]?.id || null : cur));
          return next;
        });
        message.success("已删除文献");
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        message.error(msg || "删除失败");
      }
    },
    [],
  );

  if (loading) {
    return (
      <FunctionalPageSkeleton
        title="文献库"
        subtitle="正在加载文献…"
        rows={8}
        className="library-page"
      />
    );
  }

  return (
    <div className="functional-shell library-page">
      <header className="functional-page__header">
        <div className="functional-page__header-row">
          <div>
            <h1>文献库</h1>
            <p className="functional-page__subtitle">共 {items.length} 条文献</p>
          </div>
          <button
            type="button"
            className="btn-sm"
            disabled={refreshingMeta || items.length === 0}
            onClick={() => void handleRefreshMetadata()}
          >
            {refreshingMeta ? "刷新中…" : "刷新元数据"}
          </button>
        </div>
      </header>

      <div className="functional-page__body">
        <div className="functional-page__inner library-page__layout">
          <section className="functional-card library-page__list-panel">
            <LiteratureListPanel
              items={items}
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                setDetailTab(undefined);
              }}
              showDensityToggle
              onListIndexMap={setListIndexById}
              onStarChange={handleItemChange}
              onDelete={handleDelete}
              onShowReviews={(id) => {
                setSelectedId(id);
                setDetailTab("reviews");
              }}
              emptyHint="暂无收录文献。在综述会话中生成引用后会自动追加到此库。"
            />
          </section>

          <aside className="library-page__detail-panel functional-card">
            <LibraryDetailPane
              itemId={selectedId}
              listIndex={selectedId ? listIndexById[selectedId] : undefined}
              activeTab={detailTab}
              onTabChange={setDetailTab}
              onItemChange={handleItemChange}
            />
          </aside>
        </div>
      </div>
    </div>
  );
}
