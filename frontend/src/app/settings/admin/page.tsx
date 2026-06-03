"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import {
  formatCapabilityParams,
  resolveCapabilityRefLabel,
} from "@/lib/capabilityFormat";
import { settingsApiV2 } from "@/lib/settingsApiV2";
import { SettingsErrorMsg, SettingsLoading, errorMessage } from "../_shared";

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
      .catch((e: unknown) => setMsg(errorMessage(e)))
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

    const row = (id: string, label: string) => {
      const cap = capById.get(id);
      const ref = resolveCapabilityRefLabel(cap, credById, instById);
      const params = formatCapabilityParams(id, cap?.params);
      const value = params ? `${ref} · ${params}` : ref;
      return { id, label, value };
    };

    return [
      row("review_main", "综述主模型"),
      row("orchestrator", "编排模型"),
      row("web_search", "Tavily"),
      row("web_fetch", "Jina"),
    ];
  }, [caps, credentials, instances]);

  if (loading) {
    return <SettingsLoading />;
  }

  return (
    <div className="card settings-section settings-section--compact">
      <SettingsErrorMsg msg={msg} />

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
