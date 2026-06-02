export type LlmProviderSlug =
  | "openai"
  | "zhipu"
  | "alibaba"
  | "minimax_intl"
  | "minimax_cn"
  | "ollama";

export type LlmExtraField = {
  key: string;
  label: string;
  required?: boolean;
};

export type LlmProviderMeta = {
  slug: LlmProviderSlug;
  label: string;
  default_model: string;
  default_base_url: string;
  requires_api_key: boolean;
  notes: string;
  extra_fields?: LlmExtraField[];
};

export const LLM_PROVIDERS: LlmProviderMeta[] = [
  {
    slug: "openai",
    label: "OpenAI (GPT)",
    default_model: "gpt-4o-mini",
    default_base_url: "https://api.openai.com/v1",
    requires_api_key: true,
    notes: "API Key 来自 platform.openai.com",
  },
  {
    slug: "zhipu",
    label: "智谱 GLM (ZhipuAI)",
    default_model: "glm-4-flash",
    default_base_url: "https://open.bigmodel.cn/api/paas/v4",
    requires_api_key: true,
    notes: "API Key 来自 open.bigmodel.cn，兼容 OpenAI 接口",
  },
  {
    slug: "alibaba",
    label: "阿里云百炼 (Qwen)",
    default_model: "qwen-turbo",
    default_base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    requires_api_key: true,
    notes: "API Key 来自 dashscope.aliyuncs.com",
  },
  {
    slug: "minimax_intl",
    label: "MiniMax 国际版",
    default_model: "MiniMax-Text-01",
    default_base_url: "https://api.minimaxi.chat/v1",
    requires_api_key: true,
    notes: "API Key 来自 www.minimaxi.chat，兼容 OpenAI 接口",
  },
  {
    slug: "minimax_cn",
    label: "MiniMax 国内版",
    default_model: "MiniMax-M2.7",
    default_base_url: "https://api.minimaxi.com/v1",
    requires_api_key: true,
    notes:
      "OpenAI 兼容端点 https://api.minimaxi.com/v1（请勿填 /anthropic）；Group ID 可选（团队信息页可查，不填用账号默认）",
    extra_fields: [{ key: "group_id", label: "Group ID", required: false }],
  },
  {
    slug: "ollama",
    label: "Ollama (本地)",
    default_model: "llama3.2",
    default_base_url: "http://127.0.0.1:11434",
    requires_api_key: false,
    notes:
      "本地 Ollama 服务，无需 API Key。macOS 上若后端在 Docker 内运行，可填 http://host.docker.internal:11434",
  },
];

export function getLlmProvider(slug: string): LlmProviderMeta | undefined {
  return LLM_PROVIDERS.find((p) => p.slug === slug);
}

export function applyProviderDefaults(slug: string): {
  model: string;
  base_url: string;
} {
  const p = getLlmProvider(slug);
  if (!p) return { model: "", base_url: "" };
  return { model: p.default_model, base_url: p.default_base_url };
}
