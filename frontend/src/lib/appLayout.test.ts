import { describe, expect, it } from "vitest";
import {
  getAppLayoutFlags,
  isChatRoute,
  isFunctionalRoute,
} from "./appLayout";

describe("appLayout", () => {
  it("识别 chat 与功能页路由", () => {
    expect(isChatRoute("/chat")).toBe(true);
    expect(isChatRoute("/chat/foo")).toBe(true);
    expect(isFunctionalRoute("/settings")).toBe(true);
    expect(isFunctionalRoute("/library")).toBe(true);
    expect(isFunctionalRoute("/help")).toBe(true);
    expect(isFunctionalRoute("/settings/admin")).toBe(true);
    expect(isFunctionalRoute("/chat")).toBe(false);
  });

  it("功能页强制关闭 Artifact 并隐藏切换与会话列", () => {
    const flags = getAppLayoutFlags("/settings", true);
    expect(flags.isFunctional).toBe(true);
    expect(flags.artifactVisible).toBe(false);
    expect(flags.showArtifactToggle).toBe(false);
    expect(flags.showSessionColumn).toBe(false);
  });

  it("chat 路由沿用 Artifact 开关", () => {
    expect(getAppLayoutFlags("/chat", true).artifactVisible).toBe(true);
    expect(getAppLayoutFlags("/chat", false).artifactVisible).toBe(false);
    expect(getAppLayoutFlags("/chat", true).showArtifactToggle).toBe(true);
    expect(getAppLayoutFlags("/chat", true).showSessionColumn).toBe(true);
  });
});
