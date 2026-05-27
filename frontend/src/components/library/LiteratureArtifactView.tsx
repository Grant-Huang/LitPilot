"use client";

import type { LibraryItem } from "@/lib/libraryTypes";
import { LibraryDetailPane } from "./LibraryDetailPane";
import { LiteratureListPanel } from "./LiteratureListPanel";

type Props = {
  items: LibraryItem[];
  selectedId: string | null;
  onSelectId: (id: string | null) => void;
  activeSessionId?: string | null;
  onLiteratureDetailOpen?: (open: boolean) => void;
};

export function LiteratureArtifactView({
  items,
  selectedId,
  onSelectId,
  activeSessionId,
  onLiteratureDetailOpen,
}: Props) {
  const detailOpen = Boolean(selectedId);

  const handleBack = () => {
    onSelectId(null);
    onLiteratureDetailOpen?.(false);
  };

  const handleSelect = (id: string) => {
    onSelectId(id);
    onLiteratureDetailOpen?.(true);
  };

  if (detailOpen) {
    return (
      <div className="literature-artifact-view literature-artifact-view--detail">
        <LibraryDetailPane
          variant="artifact"
          itemId={selectedId}
          onBack={handleBack}
        />
      </div>
    );
  }

  return (
    <div className="literature-artifact-view literature-artifact-view--list">
      <LiteratureListPanel
        items={items}
        selectedId={selectedId}
        onSelect={handleSelect}
        onOpenFullText={handleSelect}
        activeSessionId={activeSessionId}
        showSessionFilter
        emptyHint="本会话尚未收录文献，请完成综述或点击文献库补全。"
      />
    </div>
  );
}
