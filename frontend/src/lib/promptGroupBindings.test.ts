import { describe, expect, it } from "vitest";
import {
  applyGroupInstanceToParams,
  effectivePromptTemplate,
  loadGroupInstances,
  promptTemplateForSave,
  resolveGroupInstanceId,
} from "./promptGroupBindings";
import type { PromptTemplateMeta } from "./settingsApiV2";

const META: PromptTemplateMeta[] = [
  {
    key: "understanding_system_template",
    label: "理解",
    group: "orchestrator",
    group_label: "编排解说",
    max_len: 8000,
    hint: "",
  },
  {
    key: "intent_router_system_template",
    label: "路由",
    group: "router",
    group_label: "路由",
    max_len: 8000,
    hint: "",
  },
];

describe("resolveGroupInstanceId", () => {
  it("reads capability refs for orchestrator and generation", () => {
    const capRefs = {
      orchestrator: "orch-id",
      review_main: "review-id",
    };
    expect(resolveGroupInstanceId("orchestrator", {}, capRefs)).toBe("orch-id");
    expect(resolveGroupInstanceId("generation", {}, capRefs)).toBe("review-id");
  });

  it("reads group param keys for router/search", () => {
    expect(
      resolveGroupInstanceId("router", { router_instance_id: "r1" }, {}),
    ).toBe("r1");
  });
});

describe("loadGroupInstances", () => {
  it("loads one entry per group from meta", () => {
    const loaded = loadGroupInstances(
      META,
      { router_instance_id: "router-inst" },
      { orchestrator: "orch-inst" },
    );
    expect(loaded.orchestrator).toBe("orch-inst");
    expect(loaded.router).toBe("router-inst");
  });
});

describe("prompt templates", () => {
  it("fills empty stored with built-in default for display", () => {
    expect(effectivePromptTemplate("", "built-in")).toBe("built-in");
    expect(effectivePromptTemplate("custom", "built-in")).toBe("custom");
  });

  it("stores empty when display matches built-in", () => {
    expect(promptTemplateForSave("built-in", "built-in")).toBe("");
    expect(promptTemplateForSave("custom", "built-in")).toBe("custom");
  });
});

describe("applyGroupInstanceToParams", () => {
  it("writes router_instance_id not per-prompt keys", () => {
    const next = applyGroupInstanceToParams("router", "id-1", {});
    expect(next.router_instance_id).toBe("id-1");
    expect(next.intent_router_system_template_instance_id).toBeUndefined();
  });
});
