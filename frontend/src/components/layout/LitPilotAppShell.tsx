"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOutlined, MessageOutlined } from "@ant-design/icons";
import { ThreeColumnLayout } from "@meso.ai/ui";
import { useChatLayoutBridgeOptional } from "@/contexts/ChatLayoutBridgeContext";
import { useChatSession } from "@/contexts/ChatSessionContext";
import {
  pendingNavLabel,
  useAppNavigation,
} from "@/contexts/AppNavigationContext";
import { debounce } from "@/lib/debounce";
import { LitPilotSessionColumn } from "@/integrations/meso/LitPilotSessionColumn";
import { LitPilotMark, LitPilotWordmark } from "@/components/brand/LitPilotMark";
import { LitPilotBrandLockup } from "@/components/brand/LitPilotBrandLockup";
import { LitPilotSidebarUser } from "@/components/layout/LitPilotSidebarUser";
import { SidebarTaskBadge } from "@/components/layout/SidebarTaskBadge";
import { getAppLayoutFlags } from "@/lib/appLayout";

const ARTIFACT_KEY = "litpilot:artifact-visible";

function readArtifactVisible(defaultOn: boolean): boolean {
  if (typeof window === "undefined") return defaultOn;
  try {
    const v = localStorage.getItem(ARTIFACT_KEY);
    if (v === "false") return false;
    if (v === "true") return true;
  } catch {
    /* ignore */
  }
  return defaultOn;
}

type Props = { children: React.ReactNode };

export function LitPilotAppShell({ children }: Props) {
  const pathname = usePathname();
  const { pendingHref, navigate, isNavigating } = useAppNavigation();
  const isChat = pathname === "/chat" || pathname.startsWith("/chat/");
  const chatBridge = useChatLayoutBridgeOptional();
  const {
    sessions,
    activeSessionId,
    loadSessions,
    handleNewSession,
    handleSelectSession,
    handleDeleteSession,
    handleRenameSession,
    handleTogglePinSession,
  } = useChatSession();

  const hasArtifact = Boolean(isChat && chatBridge?.hasArtifact);
  // 首屏与 SSR 一致为 false，避免 localStorage 导致 hydration 不匹配
  const [artifactVisible, setArtifactVisible] = useState(false);

  useEffect(() => {
    if (!isChat) return;
    const run = debounce(() => {
      void loadSessions();
    }, 300);
    run();
    return () => run.cancel();
  }, [loadSessions, isChat]);

  useEffect(() => {
    if (!isChat) {
      setArtifactVisible(false);
      return;
    }
    setArtifactVisible(readArtifactVisible(true));
  }, [isChat]);

  const prevHasArtifact = useRef(false);
  const [artifactNudge, setArtifactNudge] = useState(false);
  useEffect(() => {
    if (hasArtifact && !prevHasArtifact.current) {
      setArtifactVisible(true);
    }
    prevHasArtifact.current = hasArtifact;
  }, [hasArtifact]);

  useEffect(() => {
    if (!isChat || !hasArtifact || artifactVisible) {
      setArtifactNudge(false);
      return;
    }
    setArtifactNudge(true);
    const t = window.setTimeout(() => setArtifactNudge(false), 4000);
    return () => window.clearTimeout(t);
  }, [isChat, hasArtifact, artifactVisible]);

  useEffect(() => {
    if (!isChat) return;
    try {
      localStorage.setItem(ARTIFACT_KEY, String(artifactVisible));
    } catch {
      /* ignore */
    }
  }, [isChat, artifactVisible]);

  useEffect(() => {
    if (!isChat || !chatBridge) return;
    chatBridge.registerArtifactPanelControl({
      visible: artifactVisible,
      open: () => setArtifactVisible(true),
    });
    return () => chatBridge.registerArtifactPanelControl(null);
  }, [isChat, chatBridge, artifactVisible]);

  useEffect(() => {
    if (isChat) return;
    chatBridge?.resetChatLayout();
  }, [isChat, chatBridge]);

  const navItems = useMemo(
    () => [
      {
        id: "chat",
        label: pendingNavLabel("/chat", "综述会话", pendingHref),
        icon: <MessageOutlined />,
        active: isChat,
        onClick: () => navigate("/chat"),
      },
      {
        id: "library",
        label: pendingNavLabel("/library", "文献库", pendingHref),
        icon: <BookOutlined />,
        active: pathname === "/library",
        onClick: () => navigate("/library"),
      },
    ],
    [isChat, navigate, pathname, pendingHref],
  );

  const sessionColumn = (
    <LitPilotSessionColumn
      sessions={sessions}
      activeId={activeSessionId}
      onSelect={(id) => {
        if (!isChat) navigate("/chat");
        void handleSelectSession(id);
      }}
      onNewSession={() => {
        if (!isChat) navigate("/chat");
        void handleNewSession();
      }}
      onDelete={handleDeleteSession}
      onRename={handleRenameSession}
      onTogglePin={handleTogglePinSession}
    />
  );

  const titles: Record<string, string> = {
    "/library": "文献库",
    "/settings": "设置",
    "/help": "帮助中心",
  };
  const mainTitle = isChat ? "文献综述" : titles[pathname] || "LitPilot";
  const layoutFlags = getAppLayoutFlags(pathname, artifactVisible);

  const layoutExtraClass = [
    "litpilot-branded",
    isNavigating ? "litpilot-layout--nav-pending" : "",
    isChat && artifactVisible ? "litpilot-layout--artifact-open" : "",
    isChat && artifactNudge ? "litpilot-layout--artifact-nudge" : "",
    isChat && chatBridge?.literatureDetailOpen
      ? "litpilot-layout--literature-detail"
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={layoutExtraClass}
      data-nav-pending={pendingHref ?? undefined}
    >
      <ThreeColumnLayout
        appName="LitPilot"
        sidebarLogo={
          <Link
            href="/chat"
            className="litpilot-sidebar-home"
            aria-label="回到主页"
          >
            <LitPilotMark size={26} aria-hidden className="litpilot-sidebar-mark" />
          </Link>
        }
        sidebarTitle={
          <Link href="/chat" className="litpilot-sidebar-home__title" aria-label="回到主页">
            <LitPilotWordmark size={15} />
          </Link>
        }
        navItems={navItems}
        sidebarFooter={
          <>
            <SidebarTaskBadge />
            <LitPilotSidebarUser />
          </>
        }
        sessionColumn={layoutFlags.showSessionColumn ? sessionColumn : <div />}
        mainHeader={
          <LitPilotBrandLockup
            markSize={22}
            wordmarkSize={14}
            pageTitle={isChat ? mainTitle : undefined}
            className="litpilot-main-header"
          />
        }
        artifactPanel={layoutFlags.isChat ? chatBridge?.artifactPanel : null}
        artifactVisible={layoutFlags.artifactVisible}
        showArtifactToggle={layoutFlags.showArtifactToggle}
        showSessionColumn={layoutFlags.showSessionColumn}
        onArtifactToggle={setArtifactVisible}
      >
        <div key={pathname} className="litpilot-route-outlet">
          {children}
        </div>
      </ThreeColumnLayout>
    </div>
  );
}
