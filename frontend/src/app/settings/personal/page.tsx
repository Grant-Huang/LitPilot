"use client";

import { useEffect, useState } from "react";
import { settingsApiV2 } from "@/lib/settingsApiV2";
import { InlineField } from "../admin/_ui";
import {
  errorMessage,
  SettingsErrorMsg,
  SettingsLoading,
  SettingsSuccessMsg,
} from "../_shared";

type CitationFormat = "apa" | "acm";

export default function PersonalSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [msgOk, setMsgOk] = useState(false);

  const [citationFormat, setCitationFormat] = useState<CitationFormat>("apa");
  const [planConfirm, setPlanConfirm] = useState(false);

  useEffect(() => {
    void settingsApiV2
      .getPersonalPreferences()
      .then((p) => {
        if (p.citation_format === "apa" || p.citation_format === "acm") {
          setCitationFormat(p.citation_format);
        }
        setPlanConfirm(Boolean(p.plan_confirm));
      })
      .catch((e: unknown) => {
        setMsgOk(false);
        setMsg(errorMessage(e));
      })
      .finally(() => setLoading(false));
  }, []);

  const onSave = async () => {
    setSaving(true);
    setMsg("");
    try {
      await settingsApiV2.savePersonalPreferences({
        citation_format: citationFormat,
        plan_confirm: planConfirm,
      });
      setMsgOk(true);
      setMsg("个人偏好已保存");
    } catch (e: unknown) {
      setMsgOk(false);
      setMsg(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div
        className="functional-shell"
        style={{ alignItems: "center", justifyContent: "center", flex: 1 }}
      >
        <SettingsLoading />
      </div>
    );
  }

  return (
    <div className="functional-shell">
      <div className="card settings-section" style={{ maxWidth: 920 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>个人设置</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
            仅影响本机个人偏好，不包含系统级密钥与能力配置。
          </p>
        </div>

        {msgOk ? <SettingsSuccessMsg msg={msg} /> : <SettingsErrorMsg msg={msg} />}

        <InlineField label="参考文献格式" htmlFor="citation-format">
          <select
            id="citation-format"
            className="input settings-select"
            value={citationFormat}
            onChange={(e) => setCitationFormat(e.target.value as CitationFormat)}
          >
            <option value="apa">APA</option>
            <option value="acm">ACM</option>
          </select>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
            影响引用抽取与综述参考文献章节格式。
          </p>
        </InlineField>

        <label className="settings-checkbox-row">
          <input type="checkbox" checked={planConfirm} onChange={(e) => setPlanConfirm(e.target.checked)} />
          执行前展示工作流拓扑并确认（plan_confirm）
        </label>

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
          <button type="button" className="btn-primary" onClick={() => void onSave()} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
