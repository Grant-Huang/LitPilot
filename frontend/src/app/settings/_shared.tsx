"use client";

import { Spin } from "antd";
import { ApiError } from "@/lib/http";
import type { SystemCredential } from "@/lib/settingsApiV2";

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function isLlmCredential(c: SystemCredential): boolean {
  return String(c.type || "").startsWith("llm:");
}

export function mergeById<T extends { id: string }>(items: T[], updated: T): T[] {
  return items.map((x) => (x.id === updated.id ? { ...x, ...updated } : x));
}

export function entityFromTestError<T extends { id: string }>(
  e: unknown,
  key: "credential" | "instance",
): T | null {
  if (e instanceof ApiError && e.data && typeof e.data === "object") {
    const entity = (e.data as Record<string, T | undefined>)[key];
    if (entity?.id) return entity;
  }
  return null;
}

export function formatVerifiedHint(lastVerifiedAt?: string | null): string {
  return lastVerifiedAt
    ? `最近测试：${new Date(lastVerifiedAt).toLocaleString()}`
    : "";
}

export function SettingsLoading() {
  return (
    <div className="settings-admin-loading">
      <Spin size="large" />
    </div>
  );
}

export function SettingsErrorMsg({ msg }: { msg: string }) {
  if (!msg) return null;
  return (
    <div className="settings-msg settings-msg--err" role="alert">
      {msg}
    </div>
  );
}

export function SettingsSuccessMsg({ msg }: { msg: string }) {
  if (!msg) return null;
  return (
    <div className="settings-msg settings-msg--ok" role="status">
      {msg}
    </div>
  );
}
