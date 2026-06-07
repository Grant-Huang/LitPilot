import type {
  SystemCapability,
  SystemCredential,
  SystemInstance,
} from "@/lib/settingsApiV2";
import {
  fetchProviderNeedsCredential,
  searchProviderNeedsCredential,
  searchProviderOptionalCredential,
} from "@/lib/webProviderOptions";

type PrimaryRef = { kind?: string; id?: string } | null | undefined;

/** 能力 ID → 后端 LLM 运行时角色（与 llm_service 一致） */
export const CAPABILITY_LLM_ROLE: Partial<
  Record<
    string,
    { role: "review" | "planner"; summary: string; modules: string[] }
  >
> = {
  review_main: {
    role: "review",
    summary: "绑定实例 → get_review_llm()",
    modules: [
      "literature_turn_generate（语料问答、矩阵、分章综述、全文流式）",
      "literature_section_writer（单章撰写）",
    ],
  },
  orchestrator: {
    role: "planner",
    summary: "绑定实例 → get_planner_llm()",
    modules: [
      "literature_planner（理解+路由 A、阶段解说 B–G）",
      "literature_router（独立 router JSON 回退）",
      "literature_intent（多轮意图路由）",
      "search_query_refiner（检索式精炼 / 澄清问题）",
      "search_expansion（检索式扩展）",
      "literature_clarification（首轮 LLM 澄清）",
      "content_pipeline（网页分块摘要）",
      "paper_attributes（文献结构化）",
    ],
  },
};

export function capabilityLlmModulesTitle(capId: string): string | undefined {
  const role = CAPABILITY_LLM_ROLE[capId];
  if (!role?.modules.length) return undefined;
  return role.modules.join("\n");
}

const PROVIDER_CAP_IDS = new Set(["web_search", "web_fetch"]);

const CAPABILITY_TITLES: Partial<Record<string, string>> = {
  web_search: "网络检索",
  web_fetch: "网页抓取",
  literature_source: "文献来源",
};

export function capabilityDisplayTitle(cap: SystemCapability): string {
  const mapped = CAPABILITY_TITLES[cap.capability_id];
  if (mapped) return mapped;
  if (cap.label?.trim()) return cap.label.trim();
  if (PROVIDER_CAP_IDS.has(cap.capability_id)) {
    return cap.capability_id;
  }
  return cap.label || cap.capability_id;
}

export function resolveCapabilityRefLabel(
  cap: SystemCapability | undefined,
  credById: Map<string, SystemCredential>,
  instById: Map<string, SystemInstance>,
): string {
  const ref = cap?.primary_ref as PrimaryRef;
  if (!ref) return "未选择";
  if (ref.kind === "credential") {
    const c = credById.get(String(ref.id));
    if (!c) return "凭据不存在";
    return c.name;
  }
  if (ref.kind === "instance") {
    const i = instById.get(String(ref.id));
    if (!i) return "实例不存在";
    return `${i.name} · ${i.model_name}`;
  }
  return "未选择";
}

export function formatCapabilityParams(
  capId: string,
  params: Record<string, unknown> | undefined,
): string {
  const p = params || {};
  if (capId === "web_search") {
    const prov = String(p.search_provider ?? "multi_academic");
    return `${prov} · 检索 ${Number(p.search_max_results ?? 20)} · 重试 ${Number(p.search_retry_count ?? 3)}`;
  }
  if (capId === "web_fetch") {
    const prov = String(p.fetch_provider ?? "native");
    const pdf = String(p.pdf_extract_backend ?? "pymupdf4llm");
    const pdfPart = prov === "native" ? ` · PDF ${pdf}` : "";
    return `${prov} · 抓取 ${Number(p.max_fetch_urls ?? 5)} · 并行 ${Number(p.fetch_parallel ?? 3)}${pdfPart}`;
  }
  if (capId === "orchestrator") {
    return "";
  }
  return "";
}

export function capabilityNeedsCredentialRef(
  cap: SystemCapability,
  params?: Record<string, unknown>,
): boolean {
  const p = params ?? cap.params ?? {};
  if (cap.capability_id === "web_search") {
    return searchProviderNeedsCredential(String(p.search_provider ?? "multi_academic"));
  }
  if (cap.capability_id === "web_fetch") {
    return fetchProviderNeedsCredential(String(p.fetch_provider ?? "native"));
  }
  return cap.capability_id === "review_main" || cap.capability_id === "orchestrator";
}

export function capabilityRefOptions(
  cap: SystemCapability,
  credentials: SystemCredential[],
  instances: SystemInstance[],
): { kind: string; items: Array<{ id: string; label: string }> } {
  if (cap.capability_id === "review_main" || cap.capability_id === "orchestrator") {
    return {
      kind: "instance",
      items: instances.map((i) => ({
        id: i.id,
        label: `${i.name} · ${i.provider} · ${i.model_name}`,
      })),
    };
  }
  if (cap.capability_id === "web_search") {
    const provider = String(cap.params?.search_provider ?? "multi_academic");
    if (searchProviderNeedsCredential(provider)) {
      const credType = provider === "brave" ? "brave" : "tavily";
      return {
        kind: "credential",
        items: credentials
          .filter((c) => String(c.type || "") === credType)
          .map((c) => ({
            id: c.id,
            label: `${c.name} · ${c.has_secret ? c.masked_secret : "未配置"}`,
          })),
      };
    }
    const optional = searchProviderOptionalCredential(provider);
    if (optional) {
      return {
        kind: "credential",
        items: credentials
          .filter((c) => String(c.type || "") === optional)
          .map((c) => ({
            id: c.id,
            label: `${c.name} · ${c.has_secret ? c.masked_secret : "未配置（可选）"}`,
          })),
      };
    }
    return { kind: "", items: [] };
  }
  if (cap.capability_id === "web_fetch") {
    const provider = String(cap.params?.fetch_provider ?? "native");
    if (!fetchProviderNeedsCredential(provider)) {
      return { kind: "", items: [] };
    }
    return {
      kind: "credential",
      items: credentials
        .filter((c) => String(c.type || "").startsWith("jina"))
        .map((c) => ({
          id: c.id,
          label: `${c.name} · ${c.has_secret ? c.masked_secret : "未配置"}`,
        })),
    };
  }
  return { kind: "", items: [] };
}

export function capabilityRefLabel(
  capId: string,
  params?: Record<string, unknown>,
): string {
  if (capId === "web_search") {
    const p = String(params?.search_provider ?? "multi_academic");
    if (p === "brave" || p === "tavily") return "web_search 凭据";
    if (searchProviderOptionalCredential(p)) return "Semantic Scholar Key（可选）";
    return "凭据";
  }
  if (capId === "web_fetch") {
    const p = String(params?.fetch_provider ?? "native");
    if (p === "jina") return "web_fetch 凭据";
    return "凭据";
  }
  return "实例";
}
