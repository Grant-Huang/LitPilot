"use client";

import type { StreamState } from "@meso.ai/ui";
import { LitPilotArtifactPane } from "@/components/artifact/LitPilotArtifactPane";
import type { LibraryItem } from "@/lib/libraryTypes";

type Props = {
  streamState: StreamState;
  reviewFilename?: string;
  matrixFilename?: string;
  libraryItems?: LibraryItem[];
  selectedLibraryId?: string | null;
  onSelectLibraryId?: (id: string | null) => void;
  activeSessionId?: string | null;
  onLiteratureDetailOpen?: (open: boolean) => void;
};

export function LitPilotArtifactSlot({
  streamState,
  reviewFilename,
  matrixFilename,
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
      matrixFilename={matrixFilename}
      libraryItems={libraryItems}
      selectedLibraryId={selectedLibraryId}
      onSelectLibraryId={onSelectLibraryId}
      activeSessionId={activeSessionId}
      onLiteratureDetailOpen={onLiteratureDetailOpen}
    />
  );
}
