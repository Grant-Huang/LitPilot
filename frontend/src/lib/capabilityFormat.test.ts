import { describe, expect, it } from "vitest";
import {
  CAPABILITY_LLM_ROLE,
  capabilityLlmModulesTitle,
  capabilityRefOptions,
  formatCapabilityParams,
  resolveCapabilityRefLabel,
} from "./capabilityFormat";
import type {
  SystemCapability,
  SystemCredential,
  SystemInstance,
} from "@/lib/settingsApiV2";

describe("capabilityFormat", () => {
  it("formats ref and params for overview rows", () => {
    const creds = new Map<string, SystemCredential>([
      ["c1", { id: "c1", name: "Tavily Key", type: "tavily:api", has_secret: true, masked_secret: "tv-***" }],
    ]);
    const insts = new Map<string, SystemInstance>([
      [
        "i1",
        {
          id: "i1",
          name: "Main",
          provider: "openai",
          model_name: "gpt-4",
          credential_id: "c1",
          default_params: {},
        },
      ],
    ]);
    const cap = {
      capability_id: "web_search",
      label: "Web Search",
      enabled: true,
      primary_ref: { kind: "credential", id: "c1" },
      override_params: {},
      params: { search_max_results: 10, search_retry_count: 1 },
    } as SystemCapability;
    expect(resolveCapabilityRefLabel(cap, creds, insts)).toBe("Tavily Key");
    expect(formatCapabilityParams("web_search", cap.params)).toBe(
      "multi_academic · 检索 10 · 重试 1",
    );
  });

  it("builds ref options by capability id", () => {
    const opts = capabilityRefOptions(
      {
        capability_id: "review_main",
        label: "Review",
        enabled: true,
        primary_ref: null,
        override_params: {},
        params: {},
      } as SystemCapability,
      [],
      [
        {
          id: "i1",
          name: "Main",
          provider: "openai",
          model_name: "gpt-4",
          credential_id: "c1",
          default_params: {},
        },
      ],
    );
    expect(opts.kind).toBe("instance");
    expect(opts.items[0].label).toContain("Main");
  });

  it("lists planner modules for orchestrator capability", () => {
    expect(CAPABILITY_LLM_ROLE.orchestrator?.modules.length).toBeGreaterThan(5);
    expect(capabilityLlmModulesTitle("orchestrator")).toContain("literature_planner");
    expect(capabilityLlmModulesTitle("review_main")).toContain("literature_turn_generate");
  });
});
