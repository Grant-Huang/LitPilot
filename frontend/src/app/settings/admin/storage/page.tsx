"use client";

import { useEffect, useState } from "react";
import { settingsApiV2, type StorageSettings } from "@/lib/settingsApiV2";
import { SettingsErrorMsg, SettingsLoading, errorMessage } from "../../_shared";
import { SettingsListPanel } from "../_ui";
import { StorageSettingsPanel } from "../_storage";

export default function AdminStoragePage() {
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [storage, setStorage] = useState<StorageSettings | null>(null);

  useEffect(() => {
    void settingsApiV2
      .getSystemOverview()
      .then((ov) => setStorage(ov.storage))
      .catch((e: unknown) => setMsg(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <SettingsLoading />;
  }

  if (!storage) {
    return <SettingsErrorMsg msg={msg || "无法加载存储配置"} />;
  }

  return (
    <SettingsListPanel>
      <SettingsErrorMsg msg={msg} />
      <StorageSettingsPanel storage={storage} onSaved={setStorage} />
    </SettingsListPanel>
  );
}
