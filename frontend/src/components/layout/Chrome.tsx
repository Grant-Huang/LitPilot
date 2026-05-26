"use client";

import { ChatLayoutBridgeProvider } from "@/contexts/ChatLayoutBridgeContext";
import { ChatSessionProvider } from "@/contexts/ChatSessionContext";
import { LitPilotAppShell } from "./LitPilotAppShell";

export function Chrome({ children }: { children: React.ReactNode }) {
  return (
    <ChatSessionProvider>
      <ChatLayoutBridgeProvider>
        <LitPilotAppShell>{children}</LitPilotAppShell>
      </ChatLayoutBridgeProvider>
    </ChatSessionProvider>
  );
}
