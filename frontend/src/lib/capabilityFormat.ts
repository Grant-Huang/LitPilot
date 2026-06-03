import type {
  SystemCapability,
  SystemCredential,
  SystemInstance,
} from "@/lib/settingsApiV2";

type PrimaryRef = { kind?: string; id?: string } | null | undefined;

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
    return `检索 ${Number(p.tavily_max_results ?? 8)} · 重试 ${Number(p.tavily_retry_count ?? 0)}`;
  }
  if (capId === "web_fetch") {
    return `抓取 ${Number(p.max_fetch_urls ?? 5)} · 并行 ${Number(p.fetch_parallel ?? 3)}`;
  }
  if (capId === "orchestrator") {
    return `${String(p.orchestrator_mode ?? "lite")} · ${Number(p.orchestrator_max_tokens_per_phase ?? 280)} tok`;
  }
  return "";
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
  if (cap.capability_id === "web_search" || cap.capability_id === "web_fetch") {
    const typePrefix = cap.capability_id === "web_search" ? "tavily" : "jina";
    return {
      kind: "credential",
      items: credentials
        .filter((c) => String(c.type || "").startsWith(typePrefix))
        .map((c) => ({
          id: c.id,
          label: `${c.name} · ${c.has_secret ? c.masked_secret : "未配置"}`,
        })),
    };
  }
  return { kind: "", items: [] };
}

export function capabilityRefLabel(capId: string): string {
  if (capId === "web_search") return "Tavily";
  if (capId === "web_fetch") return "Jina";
  return "实例";
}
