"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

type ChatLayoutBridge = {
  hasArtifact: boolean;
  artifactPanel: ReactNode | null;
  literatureDetailOpen: boolean;
  setChatLayout: (layout: {
    hasArtifact?: boolean;
    artifactPanel?: ReactNode | null;
    literatureDetailOpen?: boolean;
  }) => void;
  resetChatLayout: () => void;
};

const ChatLayoutBridgeContext = createContext<ChatLayoutBridge | null>(null);

export function ChatLayoutBridgeProvider({ children }: { children: ReactNode }) {
  const [hasArtifact, setHasArtifact] = useState(false);
  const [artifactPanel, setArtifactPanel] = useState<ReactNode | null>(null);
  const [literatureDetailOpen, setLiteratureDetailOpen] = useState(false);

  const setChatLayout = useCallback(
    (layout: {
      hasArtifact?: boolean;
      artifactPanel?: ReactNode | null;
      literatureDetailOpen?: boolean;
    }) => {
      if (layout.hasArtifact !== undefined) setHasArtifact(layout.hasArtifact);
      if (layout.artifactPanel !== undefined) setArtifactPanel(layout.artifactPanel);
      if (layout.literatureDetailOpen !== undefined) {
        setLiteratureDetailOpen(layout.literatureDetailOpen);
      }
    },
    [],
  );

  const resetChatLayout = useCallback(() => {
    setHasArtifact(false);
    setArtifactPanel(null);
    setLiteratureDetailOpen(false);
  }, []);

  const value = useMemo(
    () => ({
      hasArtifact,
      artifactPanel,
      literatureDetailOpen,
      setChatLayout,
      resetChatLayout,
    }),
    [
      hasArtifact,
      artifactPanel,
      literatureDetailOpen,
      setChatLayout,
      resetChatLayout,
    ],
  );

  return (
    <ChatLayoutBridgeContext.Provider value={value}>
      {children}
    </ChatLayoutBridgeContext.Provider>
  );
}

export function useChatLayoutBridge() {
  const ctx = useContext(ChatLayoutBridgeContext);
  if (!ctx) throw new Error("ChatLayoutBridgeProvider required");
  return ctx;
}

export function useChatLayoutBridgeOptional() {
  return useContext(ChatLayoutBridgeContext);
}
