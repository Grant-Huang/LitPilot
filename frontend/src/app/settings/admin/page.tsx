"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import Link from "next/link";
import {
  formatCapabilityParams,
  resolveCapabilityRefLabel,
} from "@/lib/capabilityFormat";
import { settingsApiV2, type StorageSettings } from "@/lib/settingsApiV2";
import { SettingsListPanel } from "./_ui";
import { storageBackendLabel } from "./_storage";
import { SettingsErrorMsg, SettingsLoading, errorMessage } from "../_shared";

type Overview = Awaited<ReturnType<typeof settingsApiV2.getSystemOverview>>;
type Capability = Awaited<ReturnType<typeof settingsApiV2.getSystemCapabilities>>["items"][number];
type Credential = Awaited<ReturnType<typeof settingsApiV2.listCredentials>>["items"][number];
type Instance = Awaited<ReturnType<typeof settingsApiV2.listInstances>>["items"][number];

const CAPABILITY_HREF: Record<string, string> = {
  review_main: "/settings/admin/capabilities",
  orchestrator: "/settings/admin/capabilities",
  web_search: "/settings/admin/capabilities",
  web_fetch: "/settings/admin/capabilities",
};

function storageStatus(storage: StorageSettings) {
  if (storage.turso_ready) {
    return { label: "已通过", tone: "ok" as const, hint: "Turso 连接正常" };
  }
  return { label: "待配置", tone: "pending" as const, hint: "请配置 Turso URL 与 Token" };
}

export default function AdminSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [caps, setCaps] = useState<Capability[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [storage, setStorage] = useState<StorageSettings | null>(null);

  useEffect(() => {
    void Promise.all([
      settingsApiV2.getSystemOverview(),
      settingsApiV2.getSystemCapabilities().then((r) => r.items || []),
      settingsApiV2.listCredentials().then((r) => r.items || []),
      settingsApiV2.listInstances().then((r) => r.items || []),
    ])
      .then(([ov, c, cred, inst]) => {
        const overviewData = ov as Overview;
        setOverview(overviewData);
        setStorage(overviewData.storage);
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
      return { id, label, value, href: CAPABILITY_HREF[id] || "/settings/admin/capabilities" };
    };

    return [
      row("review_main", "综述主模型"),
      row("orchestrator", "编排模型"),
      row("web_search", "网络检索"),
      row("web_fetch", "网页抓取"),
    ];
  }, [caps, credentials, instances]);

  if (loading) {
    return <SettingsLoading />;
  }

  const storageRow = storage ? storageStatus(storage) : null;

  return (
    <SettingsListPanel>
      <SettingsErrorMsg msg={msg} />

      <div className="settings-overview-list">
        {storage && storageRow ? (
          <Link href="/settings/admin/storage" className="settings-overview-row settings-overview-row--link">
            <div className="settings-overview-row__label">
              <span className="settings-overview-row__name">持久化存储</span>
              <span
                className={clsx(
                  "settings-cred-status",
                  storageRow.tone === "ok" ? "settings-cred-status--ok" : "settings-cred-status--pending",
                )}
                title={storageRow.hint}
              >
                {storageRow.label}
              </span>
            </div>
            <div className="settings-overview-row__value">
              {storageBackendLabel(storage.backend)}
              <span className="settings-overview-row__goto">去配置 →</span>
            </div>
          </Link>
        ) : null}

        {summary.map((row) => {
          const ready = readiness[row.id];
          return (
            <Link
              key={row.id}
              href={row.href}
              className="settings-overview-row settings-overview-row--link"
            >
              <div className="settings-overview-row__label">
                <span className="settings-overview-row__name">{row.label}</span>
                <span
                  className={clsx(
                    "settings-cred-status",
                    ready ? "settings-cred-status--ok" : "settings-cred-status--pending",
                  )}
                  title={ready ? "能力已启用且依赖项就绪" : "未就绪：请检查凭据、实例与能力绑定"}
                >
                  {ready ? "已通过" : "待配置"}
                </span>
              </div>
              <div className="settings-overview-row__value">
                {row.value}
                <span className="settings-overview-row__goto">去配置 →</span>
              </div>
            </Link>
          );
        })}
      </div>
    </SettingsListPanel>
  );
}
