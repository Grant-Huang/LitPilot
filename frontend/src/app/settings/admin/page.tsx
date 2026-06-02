"use client";

import { useEffect, useMemo, useState } from "react";
import { Spin } from "antd";
import clsx from "clsx";
import { settingsApiV2 } from "@/lib/settingsApiV2";

type Overview = Awaited<ReturnType<typeof settingsApiV2.getSystemOverview>>;
type Capability = Awaited<ReturnType<typeof settingsApiV2.getSystemCapabilities>>["items"][number];
type Credential = Awaited<ReturnType<typeof settingsApiV2.listCredentials>>["items"][number];
type Instance = Awaited<ReturnType<typeof settingsApiV2.listInstances>>["items"][number];

export default function AdminSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [caps, setCaps] = useState<Capability[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [instances, setInstances] = useState<Instance[]>([]);

  useEffect(() => {
    void Promise.all([
      settingsApiV2.getSystemOverview(),
      settingsApiV2.getSystemCapabilities().then((r) => r.items || []),
      settingsApiV2.listCredentials().then((r) => r.items || []),
      settingsApiV2.listInstances().then((r) => r.items || []),
    ])
      .then(([ov, c, cred, inst]) => {
        setOverview(ov as Overview);
        setCaps(c as Capability[]);
        setCredentials(cred as Credential[]);
        setInstances(inst as Instance[]);
      })
      .catch((e: unknown) => setMsg(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const readiness = useMemo(() => {
    const caps = overview?.capabilities || [];
    const byId: Record<string, boolean> = {};
    for (const c of caps) byId[String(c.capability_id)] = Boolean(c.ok) && Boolean(c.enabled);
    return byId;
  }, [overview]);

  const summary = useMemo(() => {
    const credById = new Map(credentials.map((c) => [c.id, c]));
    const instById = new Map(instances.map((i) => [i.id, i]));
    const capById = new Map(caps.map((c) => [c.capability_id, c]));

    const fmtRef = (capId: string): string => {
      const cap = capById.get(capId);
      const ref = cap?.primary_ref as { kind?: string; id?: string } | null;
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
    };

    const fmtParams = (capId: string): string => {
      const cap = capById.get(capId);
      const p = cap?.params || {};
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
    };

    return [
      { id: "review_main", label: "综述主模型", value: fmtRef("review_main") },
      { id: "orchestrator", label: "编排模型", value: `${fmtRef("orchestrator")} · ${fmtParams("orchestrator")}` },
      { id: "web_search", label: "Tavily", value: `${fmtRef("web_search")} · ${fmtParams("web_search")}` },
      { id: "web_fetch", label: "Jina", value: `${fmtRef("web_fetch")} · ${fmtParams("web_fetch")}` },
    ];
  }, [caps, credentials, instances]);

  if (loading) {
    return (
      <div className="settings-admin-loading">
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="card settings-section settings-section--compact">
      {msg ? <div className={clsx("settings-msg", "settings-msg--err")}>{msg}</div> : null}

      <div className="settings-overview-list">
        {summary.map((row) => (
          <div key={row.id} className="settings-overview-row">
            <div className="settings-overview-row__label">
              <span className="settings-overview-row__name">{row.label}</span>
              <span
                className={clsx(
                  "settings-cred-status",
                  readiness[row.id] ? "settings-cred-status--ok" : "settings-cred-status--pending",
                )}
              >
                {readiness[row.id] ? "已就绪" : "待配置"}
              </span>
            </div>
            <div className="settings-overview-row__value">{row.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
