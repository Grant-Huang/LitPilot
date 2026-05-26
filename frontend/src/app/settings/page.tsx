"use client";

import { useEffect, useState, type ReactNode } from "react";
import clsx from "clsx";
import { Spin } from "antd";
import { BookOpen, Brain, Save, Search, TestTube } from "lucide-react";
import { settingsApi, type AgentSettings } from "@/lib/api";
import {
  applyProviderDefaults,
  getLlmProvider,
  LLM_PROVIDERS,
} from "@/lib/llmProviders";

type SettingsTab = "agent" | "llm";

const TABS: { id: SettingsTab; label: string; icon: typeof Search }[] = [
  { id: "agent", label: "文献综述 Agent", icon: Search },
  { id: "llm", label: "大模型", icon: Brain },
];

const COST_NOTICE =
  "文献综述会调用 Tavily 检索、Jina 抓取与 LLM 生成，可能产生第三方 API 费用；请自行关注各平台用量。";

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={clsx(
        "settings-status-badge",
        ok && "settings-status-badge--ok",
      )}
    >
      {ok ? "已配置" : "未配置"} · {label}
    </span>
  );
}

const MSG_AUTO_DISMISS_MS = 4500;

function useAutoDismissSuccess(
  msg: string,
  setMsg: (value: string) => void,
) {
  useEffect(() => {
    if (!msg.startsWith("✅")) return;
    const timer = window.setTimeout(() => setMsg(""), MSG_AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [msg, setMsg]);
}

function MsgBox({ msg }: { msg: string }) {
  if (!msg) return null;
  const ok = msg.startsWith("✅");
  return (
    <div
      className={clsx(
        "settings-msg",
        ok ? "settings-msg--ok" : "settings-msg--err",
      )}
      role="status"
      aria-live="polite"
    >
      {msg}
    </div>
  );
}

function SettingsGroup({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="settings-group">
      <div className="settings-group__head">
        <h3 className="settings-group__title">{title}</h3>
        {description ? (
          <p className="settings-group__desc">{description}</p>
        ) : null}
      </div>
      <div className="settings-group__body">{children}</div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="settings-field">
      <label className="label">{label}</label>
      {children}
      {hint ? (
        <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("agent");
  const [loading, setLoading] = useState(true);

  const [hasTavily, setHasTavily] = useState(false);
  const [hasJina, setHasJina] = useState(false);
  const [hasLlm, setHasLlm] = useState(false);

  const [tavilyKey, setTavilyKey] = useState("");
  const [jinaKey, setJinaKey] = useState("");
  const [planConfirm, setPlanConfirm] = useState(false);
  const [fetchParallel, setFetchParallel] = useState(3);
  const [fetchTimeoutSec, setFetchTimeoutSec] = useState(45);
  const [tavilyMaxResults, setTavilyMaxResults] = useState(8);
  const [maxFetchUrls, setMaxFetchUrls] = useState(5);
  const [literatureSourceMode, setLiteratureSourceMode] = useState<
    "merge" | "user_only"
  >("merge");
  const [tavilyRetryCount, setTavilyRetryCount] = useState(0);
  const [fetchRetryCount, setFetchRetryCount] = useState(0);
  const [fetchRetryDelayMs, setFetchRetryDelayMs] = useState(500);
  const [citationFormat, setCitationFormat] = useState<"apa" | "acm">("apa");

  const [llmProvider, setLlmProvider] = useState("openai");
  const [llmKey, setLlmKey] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("https://api.openai.com/v1");
  const [llmGroupId, setLlmGroupId] = useState("");
  const [useLlmPlanner, setUseLlmPlanner] = useState(true);
  const [thinkMode, setThinkMode] = useState<"off" | "lite" | "full">("lite");
  const [thinkUseReasoning, setThinkUseReasoning] = useState(false);
  const [thinkModel, setThinkModel] = useState("");
  const [thinkMaxTokens, setThinkMaxTokens] = useState(280);

  const [agentMsg, setAgentMsg] = useState("");
  const [llmMsg, setLlmMsg] = useState("");
  const [savingAgent, setSavingAgent] = useState(false);
  const [savingLlm, setSavingLlm] = useState(false);
  const [testingTavily, setTestingTavily] = useState(false);

  const applyConfig = (cfg: AgentSettings) => {
    setHasTavily(Boolean(cfg.has_tavily));
    setHasJina(Boolean(cfg.has_jina));
    setHasLlm(Boolean(cfg.has_llm));
    if (cfg.llm_provider) setLlmProvider(cfg.llm_provider);
    if (cfg.llm_model) setLlmModel(cfg.llm_model);
    if (cfg.llm_base_url) setLlmBaseUrl(cfg.llm_base_url);
    else if (cfg.llm_provider) {
      const d = applyProviderDefaults(cfg.llm_provider);
      if (d.base_url) setLlmBaseUrl(d.base_url);
    }
    setLlmGroupId(cfg.llm_group_id || "");
    if (cfg.fetch_parallel != null) setFetchParallel(cfg.fetch_parallel);
    if (cfg.fetch_timeout_sec != null) setFetchTimeoutSec(cfg.fetch_timeout_sec);
    if (cfg.tavily_max_results != null) setTavilyMaxResults(cfg.tavily_max_results);
    if (cfg.max_fetch_urls != null) setMaxFetchUrls(cfg.max_fetch_urls);
    if (
      cfg.literature_source_mode === "merge" ||
      cfg.literature_source_mode === "user_only"
    ) {
      setLiteratureSourceMode(cfg.literature_source_mode);
    }
    if (cfg.tavily_retry_count != null) setTavilyRetryCount(cfg.tavily_retry_count);
    if (cfg.fetch_retry_count != null) setFetchRetryCount(cfg.fetch_retry_count);
    if (cfg.fetch_retry_delay_ms != null) {
      setFetchRetryDelayMs(cfg.fetch_retry_delay_ms);
    }
    if (cfg.plan_confirm != null) setPlanConfirm(cfg.plan_confirm);
    if (cfg.citation_format === "acm" || cfg.citation_format === "apa") {
      setCitationFormat(cfg.citation_format);
    }
    if (cfg.use_llm_planner != null) setUseLlmPlanner(cfg.use_llm_planner);
    if (
      cfg.think_mode === "off" ||
      cfg.think_mode === "lite" ||
      cfg.think_mode === "full"
    ) {
      setThinkMode(cfg.think_mode);
    }
    if (cfg.think_use_reasoning != null) {
      setThinkUseReasoning(cfg.think_use_reasoning);
    }
    if (cfg.think_model != null) setThinkModel(cfg.think_model);
    if (cfg.think_max_tokens_per_phase != null) {
      setThinkMaxTokens(cfg.think_max_tokens_per_phase);
    }
    if (!cfg.has_tavily) setActiveTab("agent");
  };

  useEffect(() => {
    void settingsApi
      .getAgent()
      .then(applyConfig)
      .finally(() => setLoading(false));
  }, []);

  useAutoDismissSuccess(agentMsg, setAgentMsg);
  useAutoDismissSuccess(llmMsg, setLlmMsg);

  const selectedProvider = getLlmProvider(llmProvider);
  const requiresApiKey = selectedProvider?.requires_api_key ?? true;

  const onProviderChange = (slug: string) => {
    setLlmProvider(slug);
    const defaults = applyProviderDefaults(slug);
    setLlmModel(defaults.model);
    setLlmBaseUrl(defaults.base_url);
    if (slug !== "minimax_cn") {
      setLlmGroupId("");
    }
  };

  const handleSaveAgent = async () => {
    if (!hasTavily && !tavilyKey.trim()) {
      setAgentMsg("❌ 请先填写 Tavily API Key");
      setActiveTab("agent");
      return;
    }
    setSavingAgent(true);
    setAgentMsg("");
    try {
      const partial: Partial<AgentSettings> = {
        plan_confirm: planConfirm,
        fetch_parallel: fetchParallel,
        fetch_timeout_sec: fetchTimeoutSec,
        tavily_max_results: tavilyMaxResults,
        max_fetch_urls: maxFetchUrls,
        literature_source_mode: literatureSourceMode,
        tavily_retry_count: tavilyRetryCount,
        fetch_retry_count: fetchRetryCount,
        fetch_retry_delay_ms: fetchRetryDelayMs,
        citation_format: citationFormat,
      };
      if (tavilyKey.trim()) partial.tavily_api_key = tavilyKey.trim();
      if (jinaKey.trim()) partial.jina_api_key = jinaKey.trim();
      const saved = await settingsApi.saveAgent(partial);
      applyConfig(saved);
      setAgentMsg("✅ 文献综述 Agent 配置已保存");
      setTavilyKey("");
      setJinaKey("");
    } catch (e: unknown) {
      setAgentMsg(`❌ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSavingAgent(false);
    }
  };

  const handleSaveLlm = async () => {
    const needsKey = requiresApiKey;
    if (needsKey && !hasLlm && !llmKey.trim()) {
      setLlmMsg("❌ 请填写 LLM API Key");
      setActiveTab("llm");
      return;
    }
    setSavingLlm(true);
    setLlmMsg("");
    try {
      const partial: Partial<AgentSettings> = {
        llm_provider: llmProvider,
        llm_model: llmModel || undefined,
        llm_base_url: llmBaseUrl || undefined,
        use_llm_planner: useLlmPlanner,
        think_mode: thinkMode,
        think_use_reasoning: thinkUseReasoning,
        think_model: thinkModel.trim() || undefined,
        think_max_tokens_per_phase: thinkMaxTokens,
      };
      if (llmKey.trim()) partial.llm_api_key = llmKey.trim();
      if (llmProvider === "minimax_cn") {
        partial.llm_group_id = llmGroupId.trim();
      }
      const saved = await settingsApi.saveAgent(partial);
      applyConfig(saved);
      setLlmMsg("✅ 大模型配置已保存");
      setLlmKey("");
    } catch (e: unknown) {
      setLlmMsg(`❌ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSavingLlm(false);
    }
  };

  const handleTestTavily = async () => {
    setTestingTavily(true);
    setAgentMsg("");
    try {
      const res = await settingsApi.testTavily(
        tavilyKey.trim() && !tavilyKey.startsWith("***")
          ? tavilyKey.trim()
          : undefined,
      );
      setAgentMsg(`✅ Tavily 可用，命中 ${res.hits} 条`);
    } catch (e: unknown) {
      setAgentMsg(`❌ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setTestingTavily(false);
    }
  };

  if (loading) {
    return (
      <div
        className="functional-shell"
        style={{
          alignItems: "center",
          justifyContent: "center",
          flex: 1,
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  const agentPanel = (
    <div className="card settings-section">
      <div>
        <h2
          style={{
            margin: 0,
            fontSize: 15,
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <BookOpen size={16} />
          文献综述 Agent
        </h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
          Tavily 检索 → Jina 抓取 → LLM 生成 APA / ACM 综述
        </p>
      </div>

      {!hasTavily && (
        <div className="settings-alert" role="alert">
          尚未配置 <strong>Tavily API Key</strong>，无法在会话中检索文献。请填写并保存后点击「测试
          Tavily」。
        </div>
      )}

      <div className="settings-highlight">
        <Field label="Tavily API Key（必填）">
          <input
            className="input font-mono"
            type="password"
            placeholder={hasTavily ? "已保存 · 输入新 Key 可覆盖" : "tvly-xxxxxxxx"}
            value={tavilyKey}
            onChange={(e) => setTavilyKey(e.target.value)}
            autoComplete="off"
          />
        </Field>
        <p
          className={clsx(
            "settings-key-status",
            hasTavily && "settings-key-status--ok",
          )}
        >
          {hasTavily
            ? "✓ 服务端已保存 Tavily Key（留空保存则保持不变）"
            : "未检测到已保存的 Key"}
        </p>
        <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>
          注册：
          <a
            href="https://tavily.com/"
            target="_blank"
            rel="noreferrer"
            style={{ color: "var(--color-accent)" }}
          >
            tavily.com
          </a>
        </p>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => void handleTestTavily()}
          disabled={testingTavily || (!hasTavily && !tavilyKey.trim())}
        >
          {testingTavily ? (
            <Spin size="small" />
          ) : (
            <TestTube size={16} />
          )}
          测试 Tavily
        </button>
      </div>

      <SettingsGroup
        title="文献来源"
        description="控制用户上传的链接列表与 Tavily 检索结果如何合并"
      >
        <Field
          label="来源策略"
          hint="上传链接后：合并 = 您的链接优先 + Tavily 补充；仅用户列表 = 跳过 Tavily"
        >
          <select
            className="input settings-select"
            value={literatureSourceMode}
            onChange={(e) =>
              setLiteratureSourceMode(e.target.value as "merge" | "user_only")
            }
          >
            <option value="merge">合并（用户链接优先 + Tavily 补充）</option>
            <option value="user_only">
              仅用户列表（有上传时跳过 Tavily）
            </option>
          </select>
        </Field>
      </SettingsGroup>

      <SettingsGroup
        title="web_search · Tavily 检索"
        description="按研究问题在互联网发现候选文献（返回链接与摘要，非全文）"
      >
        <div className="settings-field-row">
          <Field
            label="检索条数（1–20）"
            hint="单次 web_search 最大命中数 max_results"
          >
            <input
              className="input"
              type="number"
              min={1}
              max={20}
              value={tavilyMaxResults}
              onChange={(e) => setTavilyMaxResults(Number(e.target.value))}
            />
          </Field>
          <Field
            label="失败重试（0–3）"
            hint="Tavily 请求异常时的重试次数"
          >
            <input
              className="input"
              type="number"
              min={0}
              max={3}
              value={tavilyRetryCount}
              onChange={(e) => setTavilyRetryCount(Number(e.target.value))}
            />
          </Field>
        </div>
      </SettingsGroup>

      <SettingsGroup
        title="web_fetch · Jina 抓取"
        description="对选定 URL 拉取正文，供引用抽取与综述生成"
      >
        <Field
          label="Jina Reader API Key（可选）"
          hint="用于 r.jina.ai；无 Key 时仍可用公开 Reader，配额较低"
        >
          <input
            className="input font-mono"
            type="password"
            placeholder={hasJina ? "已保存 · 留空不修改" : "jina_…"}
            value={jinaKey}
            onChange={(e) => setJinaKey(e.target.value)}
          />
        </Field>
        <p
          className={clsx(
            "settings-key-status",
            hasJina && "settings-key-status--ok",
          )}
        >
          {hasJina ? "✓ Jina Key 已配置" : "未配置 Jina Key"}
        </p>
        <div className="settings-field-row">
          <Field label="抓取篇数（1–20）" hint="进入抓取队列的 URL 上限">
            <input
              className="input"
              type="number"
              min={1}
              max={20}
              value={maxFetchUrls}
              onChange={(e) => setMaxFetchUrls(Number(e.target.value))}
            />
          </Field>
          <Field label="并行并发（1–8）" hint="同时抓取的 URL 数量">
            <input
              className="input"
              type="number"
              min={1}
              max={8}
              value={fetchParallel}
              onChange={(e) => setFetchParallel(Number(e.target.value))}
            />
          </Field>
        </div>
        <div className="settings-field-row">
          <Field label="单 URL 超时（秒，10–120）">
            <input
              className="input"
              type="number"
              min={10}
              max={120}
              value={fetchTimeoutSec}
              onChange={(e) => setFetchTimeoutSec(Number(e.target.value))}
            />
          </Field>
          <Field label="失败重试（0–3）" hint="单篇抓取失败时的重试次数">
            <input
              className="input"
              type="number"
              min={0}
              max={3}
              value={fetchRetryCount}
              onChange={(e) => setFetchRetryCount(Number(e.target.value))}
            />
          </Field>
        </div>
      </SettingsGroup>

      <SettingsGroup title="重试间隔" description="上述重试之间的等待时间">
        <Field label="间隔（毫秒，0–5000）">
          <input
            className="input"
            type="number"
            min={0}
            max={5000}
            step={100}
            value={fetchRetryDelayMs}
            onChange={(e) => setFetchRetryDelayMs(Number(e.target.value))}
          />
        </Field>
      </SettingsGroup>

      <SettingsGroup title="输出与流程">
        <Field
          label="参考文献格式"
          hint="影响引用抽取与综述参考文献章节"
        >
          <select
            className="input settings-select"
            value={citationFormat}
            onChange={(e) => setCitationFormat(e.target.value as "apa" | "acm")}
          >
            <option value="apa">APA</option>
            <option value="acm">ACM</option>
          </select>
        </Field>
        <label className="settings-checkbox-row">
          <input
            type="checkbox"
            checked={planConfirm}
            onChange={(e) => setPlanConfirm(e.target.checked)}
          />
          执行前展示工作流拓扑并确认（plan_confirm）
        </label>
      </SettingsGroup>

      <p className="settings-cost-notice">{COST_NOTICE}</p>
    </div>
  );

  const llmPanel = (
    <div className="card settings-section">
      <div>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>大模型</h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
          支持 OpenAI 兼容接口、MiniMax 国内/国际版与本地 Ollama
        </p>
      </div>

      <Field label="提供商" hint={selectedProvider?.notes}>
        <select
          className="input settings-select"
          value={llmProvider}
          onChange={(e) => onProviderChange(e.target.value)}
        >
          {LLM_PROVIDERS.map((p) => (
            <option key={p.slug} value={p.slug}>
              {p.label}
            </option>
          ))}
        </select>
      </Field>

      {requiresApiKey ? (
        <Field label="API Key">
          <input
            className="input font-mono"
            type="password"
            placeholder={hasLlm ? "已保存 · 输入新 Key 可覆盖" : "填写 API Key"}
            value={llmKey}
            onChange={(e) => setLlmKey(e.target.value)}
          />
          {hasLlm && (
            <p className="settings-key-status settings-key-status--ok">
              ✓ LLM Key 已保存在服务端
            </p>
          )}
        </Field>
      ) : (
        <p className="settings-key-status settings-key-status--ok">
          ✓ 本地 Ollama 无需 API Key，请确保 Ollama 已启动且 Base URL 可访问
        </p>
      )}

      {llmProvider === "minimax_cn" &&
        selectedProvider?.extra_fields?.map((field) => (
          <Field
            key={field.key}
            label={`${field.label}${field.required ? "" : "（可选）"}`}
            hint="不填写则使用 MiniMax 账号默认 Group；仅在需要指定团队时填写"
          >
            <input
              className="input font-mono"
              placeholder="留空即可"
              value={llmGroupId}
              onChange={(e) => setLlmGroupId(e.target.value)}
              autoComplete="off"
            />
          </Field>
        ))}

      <Field label="模型（可选）">
        <input
          className="input font-mono"
          placeholder={selectedProvider?.default_model || "gpt-4o-mini"}
          value={llmModel}
          onChange={(e) => setLlmModel(e.target.value)}
        />
      </Field>

      <Field
        label={llmProvider === "ollama" ? "Ollama 地址" : "Base URL"}
        hint={
          llmProvider === "ollama"
            ? "例如 http://127.0.0.1:11434 或 http://host.docker.internal:11434"
            : "OpenAI 兼容端点根路径，一般以 /v1 结尾"
        }
      >
        <input
          className="input font-mono"
          placeholder={selectedProvider?.default_base_url}
          value={llmBaseUrl}
          onChange={(e) => setLlmBaseUrl(e.target.value)}
        />
      </Field>

      <SettingsGroup
        title="过程解说（Planner）"
        description="控制会话中「推理过程」是否由大模型流式生成；关闭后仅显示极短系统注记"
      >
        <label className="settings-checkbox-row">
          <input
            type="checkbox"
            checked={useLlmPlanner}
            onChange={(e) => setUseLlmPlanner(e.target.checked)}
          />
          使用 LLM 规划与过程解说（关闭则仅规则生成检索 query）
        </label>
        <Field
          label="解说密度"
          hint="lite：理解 / 检索后 / 抓取后；full：更多检查点（费用更高）"
        >
          <select
            className="input settings-select"
            value={thinkMode}
            disabled={!useLlmPlanner}
            onChange={(e) =>
              setThinkMode(e.target.value as "off" | "lite" | "full")
            }
          >
            <option value="off">关闭模型解说</option>
            <option value="lite">lite（推荐）</option>
            <option value="full">full</option>
          </select>
        </Field>
        {llmProvider === "minimax_cn" && (
          <label className="settings-checkbox-row">
            <input
              type="checkbox"
              checked={thinkUseReasoning}
              disabled={!useLlmPlanner || thinkMode === "off"}
              onChange={(e) => setThinkUseReasoning(e.target.checked)}
            />
            使用 MiniMax 原生推理流（redacted_thinking → 思考区）
          </label>
        )}
        <Field
          label="Planner 模型（可选）"
          hint="留空则与上方主模型相同"
        >
          <input
            className="input font-mono"
            placeholder={llmModel || selectedProvider?.default_model}
            value={thinkModel}
            disabled={!useLlmPlanner || thinkMode === "off"}
            onChange={(e) => setThinkModel(e.target.value)}
          />
        </Field>
        <Field label="单阶段解说 token 上限（80–500）">
          <input
            className="input"
            type="number"
            min={80}
            max={500}
            value={thinkMaxTokens}
            disabled={!useLlmPlanner || thinkMode === "off"}
            onChange={(e) => setThinkMaxTokens(Number(e.target.value))}
          />
        </Field>
      </SettingsGroup>

      <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>
        也可在项目根目录 <code>.env</code> 中配置{" "}
        <code>OPENAI_API_KEY</code>、<code>TAVILY_API_KEY</code> 等；设置页保存会写入{" "}
        <code>data/config/agent.json</code>。
      </p>

    </div>
  );

  const panelByTab: Record<SettingsTab, React.ReactNode> = {
    agent: agentPanel,
    llm: llmPanel,
  };

  const saveHandler =
    activeTab === "agent"
      ? () => void handleSaveAgent()
      : () => void handleSaveLlm();
  const saving = activeTab === "agent" ? savingAgent : savingLlm;
  const saveLabel =
    activeTab === "agent" ? "保存 Agent 配置" : "保存大模型配置";
  const flashMsg = activeTab === "agent" ? agentMsg : llmMsg;

  return (
    <div className="functional-shell settings-page">
      <header className="functional-page__header">
        <h1>系统设置</h1>
        <p className="functional-page__subtitle">
          文献综述需 Tavily；综述生成需大模型 Key。
        </p>
      </header>

      <div className="settings-tabs" role="tablist" aria-label="设置分类">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={activeTab === id}
            className={clsx(
              "settings-tabs__btn",
              activeTab === id && "settings-tabs__btn--active",
            )}
            onClick={() => setActiveTab(id)}
          >
            <Icon size={16} />
            {label}
            {id === "agent" && !hasTavily && (
              <span className="settings-tabs__warn">必填</span>
            )}
          </button>
        ))}
      </div>

      <div className="functional-page__body settings-page__body">
        <div className="functional-page__inner settings-page__inner">
          <div className="settings-status-bar">
            <StatusBadge ok={hasTavily} label="Tavily" />
            <StatusBadge ok={hasLlm} label="主 LLM" />
            <StatusBadge ok={hasJina} label="Jina（可选）" />
          </div>
          {panelByTab[activeTab]}
        </div>
      </div>

      <div className="settings-page__sticky-bar">
        <MsgBox msg={flashMsg} />
        <button
          type="button"
          className="btn-primary"
          onClick={saveHandler}
          disabled={saving}
        >
          {saving ? <Spin size="small" /> : <Save size={16} />}
          {saving ? "保存中…" : saveLabel}
        </button>
      </div>
    </div>
  );
}
