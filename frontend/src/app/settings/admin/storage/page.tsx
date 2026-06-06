"use client";

import { useEffect, useState } from "react";
import { loadAdminBootstrap, invalidateAdminBootstrap } from "@/lib/settingsBootstrap";
import type { StorageSettings } from "@/lib/settingsApiV2";
import { SettingsErrorMsg, SettingsListSkeleton, errorMessage } from "../../_shared";
import { SettingsListPanel } from "../_ui";
import { StorageSettingsPanel } from "../_storage";

export default function AdminStoragePage() {
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [storage, setStorage] = useState<StorageSettings | null>(null);

  useEffect(() => {
    void loadAdminBootstrap()
      .then((boot) => setStorage(boot.overview.storage))
      .catch((e: unknown) => setMsg(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <SettingsListPanel>
        <SettingsListSkeleton rows={3} />
      </SettingsListPanel>
    );
  }

  if (!storage) {
    return <SettingsErrorMsg msg={msg || "无法加载存储配置"} />;
  }

  return (
    <SettingsListPanel>
      <SettingsErrorMsg msg={msg} />
      <StorageSettingsPanel
        storage={storage}
        onSaved={(next) => {
          invalidateAdminBootstrap();
          setStorage(next);
        }}
      />
    </SettingsListPanel>
  );
}
