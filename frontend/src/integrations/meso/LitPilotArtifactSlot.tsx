"use client";

import type { StreamState } from "@meso/ui";
import { LitPilotArtifactPane } from "@/components/artifact/LitPilotArtifactPane";
import type { LibraryItem } from "@/lib/libraryTypes";

type Props = {
  streamState: StreamState;
  reviewFilename?: string;
  libraryItems?: LibraryItem[];
  selectedLibraryId?: string | null;
  onSelectLibraryId?: (id: string | null) => void;
  activeSessionId?: string | null;
  onLiteratureDetailOpen?: (open: boolean) => void;
};

export function LitPilotArtifactSlot({
  streamState,
  reviewFilename,
  libraryItems,
  selectedLibraryId,
  onSelectLibraryId,
  activeSessionId,
  onLiteratureDetailOpen,
}: Props) {
  return (
    <LitPilotArtifactPane
      streamState={streamState}
      reviewFilename={reviewFilename}
      libraryItems={libraryItems}
      selectedLibraryId={selectedLibraryId}
      onSelectLibraryId={onSelectLibraryId}
      activeSessionId={activeSessionId}
      onLiteratureDetailOpen={onLiteratureDetailOpen}
    />
  );
}
