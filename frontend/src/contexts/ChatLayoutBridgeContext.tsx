"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type ArtifactPanelControl = {
  visible: boolean;
  open: () => void;
};

type ChatLayoutBridge = {
  hasArtifact: boolean;
  artifactPanel: ReactNode | null;
  literatureDetailOpen: boolean;
  artifactPanelVisible: boolean;
  /** True when a literature generation stream is in progress (busy/settling). */
  streamBusy: boolean;
  openArtifactPanel: () => void;
  setChatLayout: (layout: {
    hasArtifact?: boolean;
    artifactPanel?: ReactNode | null;
    literatureDetailOpen?: boolean;
    streamBusy?: boolean;
  }) => void;
  registerArtifactPanelControl: (control: ArtifactPanelControl | null) => void;
  resetChatLayout: () => void;
};

const ChatLayoutBridgeContext = createContext<ChatLayoutBridge | null>(null);

export function ChatLayoutBridgeProvider({ children }: { children: ReactNode }) {
  const [hasArtifact, setHasArtifact] = useState(false);
  const [artifactPanel, setArtifactPanel] = useState<ReactNode | null>(null);
  const [literatureDetailOpen, setLiteratureDetailOpen] = useState(false);
  const [streamBusy, setStreamBusy] = useState(false);
  const [artifactControl, setArtifactControl] =
    useState<ArtifactPanelControl | null>(null);

  const setChatLayout = useCallback(
    (layout: {
      hasArtifact?: boolean;
      artifactPanel?: ReactNode | null;
      literatureDetailOpen?: boolean;
      streamBusy?: boolean;
    }) => {
      if (layout.hasArtifact !== undefined) setHasArtifact(layout.hasArtifact);
      if (layout.artifactPanel !== undefined) setArtifactPanel(layout.artifactPanel);
      if (layout.literatureDetailOpen !== undefined) {
        setLiteratureDetailOpen(layout.literatureDetailOpen);
      }
      if (layout.streamBusy !== undefined) setStreamBusy(layout.streamBusy);
    },
    [],
  );

  const registerArtifactPanelControl = useCallback(
    (control: ArtifactPanelControl | null) => {
      setArtifactControl(control);
    },
    [],
  );

  const openArtifactPanel = useCallback(() => {
    artifactControl?.open();
  }, [artifactControl]);

  const resetChatLayout = useCallback(() => {
    setHasArtifact(false);
    setArtifactPanel(null);
    setLiteratureDetailOpen(false);
    setStreamBusy(false);
  }, []);

  const value = useMemo(
    () => ({
      hasArtifact,
      artifactPanel,
      literatureDetailOpen,
      streamBusy,
      artifactPanelVisible: artifactControl?.visible ?? false,
      openArtifactPanel,
      setChatLayout,
      registerArtifactPanelControl,
      resetChatLayout,
    }),
    [
      hasArtifact,
      artifactPanel,
      literatureDetailOpen,
      streamBusy,
      artifactControl,
      openArtifactPanel,
      setChatLayout,
      registerArtifactPanelControl,
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
