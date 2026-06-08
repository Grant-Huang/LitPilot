import { describe, expect, it } from "vitest";
import { LLM_PROVIDERS, applyProviderDefaults, getLlmProvider } from "./llmProviders";

describe("llmProviders", () => {
  it("includes deepseek with OpenAI-compatible defaults", () => {
    const p = getLlmProvider("deepseek");
    expect(p).toBeDefined();
    expect(p?.default_base_url).toBe("https://api.deepseek.com");
    expect(p?.default_model).toBe("deepseek-chat");
    expect(p?.requires_api_key).toBe(true);
  });

  it("includes qwen pointing to DashScope compatible mode", () => {
    const p = getLlmProvider("qwen");
    expect(p).toBeDefined();
    expect(p?.default_base_url).toBe(
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
    expect(p?.default_model).toBe("qwen-plus");
  });

  it("applyProviderDefaults returns model and base_url for new providers", () => {
    expect(applyProviderDefaults("deepseek")).toEqual({
      model: "deepseek-chat",
      base_url: "https://api.deepseek.com",
    });
  });

  it("keeps legacy alibaba slug for backward compatibility", () => {
    expect(getLlmProvider("alibaba")).toBeDefined();
  });

  it("exposes unique provider slugs", () => {
    const slugs = LLM_PROVIDERS.map((p) => p.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });
});
