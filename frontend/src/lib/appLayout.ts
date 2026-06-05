/** 路由 → 壳层布局标志（纯函数，供测试与 LitPilotAppShell 使用） */

export type AppLayoutFlags = {
  isChat: boolean;
  isFunctional: boolean;
  /** 非 chat 路由必须为 false，避免空 Artifact 列占位 */
  artifactVisible: boolean;
  showArtifactToggle: boolean;
  showSessionColumn: boolean;
};

export function isChatRoute(pathname: string): boolean {
  return pathname === "/chat" || pathname.startsWith("/chat/");
}

export function isFunctionalRoute(pathname: string): boolean {
  return (
    pathname === "/settings" ||
    pathname.startsWith("/settings/") ||
    pathname === "/library" ||
    pathname === "/help" ||
    pathname.startsWith("/help/")
  );
}

/**
 * @param pathname 当前 pathname
 * @param chatArtifactVisible 仅 chat 路由下用户/存储的 Artifact 开关
 */
export function getAppLayoutFlags(
  pathname: string,
  chatArtifactVisible: boolean,
): AppLayoutFlags {
  const isChat = isChatRoute(pathname);
  const isFunctional = isFunctionalRoute(pathname);
  return {
    isChat,
    isFunctional,
    artifactVisible: isChat ? chatArtifactVisible : false,
    showArtifactToggle: isChat,
    showSessionColumn: !isFunctional,
  };
}
