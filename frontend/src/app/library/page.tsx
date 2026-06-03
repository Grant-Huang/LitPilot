"use client";

import { useCallback, useEffect, useState } from "react";
import { Spin, message } from "antd";
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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await loadLibraryItems();
      setItems(next);
      setSelectedId((prev) => {
        if (prev && next.some((i) => i.id === prev)) return prev;
        return next[0]?.id || null;
      });
    } catch {
      message.error("加载文献库失败");
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
      } catch {
        message.error("删除失败");
      }
    },
    [],
  );

  if (loading) {
    return (
      <div
        className="functional-shell"
        style={{ alignItems: "center", justifyContent: "center", flex: 1 }}
      >
        <Spin size="large" />
      </div>
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
