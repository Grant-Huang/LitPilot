"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Spin, message } from "antd";
import { useChatSession } from "@/contexts/ChatSessionContext";
import { LibraryDetailPane } from "@/components/library/LibraryDetailPane";
import { LiteratureListPanel } from "@/components/library/LiteratureListPanel";
import { libraryApi } from "@/lib/api";
import { normalizeLibraryItem, type LibraryItem } from "@/lib/libraryTypes";

export default function LibraryPage() {
  const router = useRouter();
  const { sessions, activeSessionId } = useChatSession();
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await libraryApi.items();
      setItems(data.items || []);
    } catch {
      try {
        const legacy = await libraryApi.refs();
        const raw =
          (legacy.items as Record<string, unknown>[]) ||
          (legacy.index?.refs as Record<string, unknown>[]) ||
          [];
        setItems(raw.map((r) => normalizeLibraryItem(r)));
      } catch {
        message.error("加载文献库失败");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleReconcile = async (mode: "session" | "all" | "failed_only") => {
    if (mode === "session" && !activeSessionId) {
      message.warning("请先选择或创建一个综述会话");
      return;
    }
    setBusy(true);
    try {
      const res = await libraryApi.reconcile({
        session_id: activeSessionId ?? undefined,
        mode,
      });
      message.success(
        `补全完成：新增 ${res.added ?? 0}，合并 ${res.merged ?? 0}，重试 ${res.retried ?? 0}`,
      );
      await load();
    } catch {
      message.error("补全失败");
    } finally {
      setBusy(false);
    }
  };

  const handleDedupe = async () => {
    setBusy(true);
    try {
      const res = await libraryApi.dedupe();
      message.success(`去重完成：移除 ${res.removed ?? 0} 条重复`);
      await load();
    } catch {
      message.error("去重失败");
    } finally {
      setBusy(false);
    }
  };

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
          <div className="functional-page__header-actions library-page__actions">
            <button
              type="button"
              className="btn-ghost"
              disabled={busy}
              onClick={() => void handleReconcile("session")}
            >
              从当前会话补全
            </button>
            <button
              type="button"
              className="btn-ghost"
              disabled={busy}
              onClick={() => void handleReconcile("failed_only")}
            >
              重试失败项
            </button>
            <button
              type="button"
              className="btn-ghost"
              disabled={busy}
              onClick={() => void handleDedupe()}
            >
              全库去重
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => router.push("/chat")}
            >
              {activeSessionId ? "继续当前会话" : "前往综述会话"}
            </button>
          </div>
        </div>
        {sessions.length > 0 && (
          <p className="functional-page__meta">已有 {sessions.length} 个综述会话</p>
        )}
      </header>

      <div className="functional-page__body">
        <div className="functional-page__inner library-page__layout">
          <section className="functional-card library-page__list-panel">
            <LiteratureListPanel
              items={items}
              selectedId={selectedId}
              onSelect={setSelectedId}
              activeSessionId={activeSessionId}
              showSessionFilter
              showDensityToggle
              emptyHint="暂无收录文献。在会话中生成综述后会自动追加；也可点击「从当前会话补全」。"
            />
          </section>

          <aside className="library-page__detail-panel functional-card">
            <LibraryDetailPane
              itemId={selectedId}
              onStarChange={(updated) => {
                setItems((prev) =>
                  prev.map((i) => (i.id === updated.id ? updated : i)),
                );
              }}
            />
          </aside>
        </div>
      </div>
    </div>
  );
}
