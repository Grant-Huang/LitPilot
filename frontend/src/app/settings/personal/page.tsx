"use client";

import { useEffect, useState } from "react";
import { UserOutlined } from "@ant-design/icons";
import { settingsApiV2 } from "@/lib/settingsApiV2";
import { FunctionalDocShell } from "@/components/layout/FunctionalDocShell";
import { InlineField } from "../admin/_ui";
import {
  errorMessage,
  SettingsErrorMsg,
  SettingsLoading,
  SettingsSuccessMsg,
} from "../_shared";
import { buildPersonalNavGroups, PERSONAL_SECTION } from "./_shellConfig";

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
      <FunctionalDocShell
        brandIcon={<UserOutlined aria-hidden />}
        brandTitle="个人设置"
        navGroups={buildPersonalNavGroups()}
        pageTitle={PERSONAL_SECTION.title}
        pageSummary={PERSONAL_SECTION.summary}
        contentClassName="settings-doc-content"
        className="functional-doc-shell--loading"
      >
        <SettingsLoading />
      </FunctionalDocShell>
    );
  }

  return (
    <FunctionalDocShell
      brandIcon={<UserOutlined aria-hidden />}
      brandTitle="个人设置"
      navGroups={buildPersonalNavGroups()}
      pageTitle={PERSONAL_SECTION.title}
      pageSummary={PERSONAL_SECTION.summary}
      contentClassName="settings-doc-content"
    >
      <div className="card settings-section settings-personal-panel">
        {msgOk ? <SettingsSuccessMsg msg={msg} /> : <SettingsErrorMsg msg={msg} />}

        <InlineField
          label="参考文献格式"
          htmlFor="citation-format"
          tip="影响引用抽取与综述参考文献章节格式。"
        >
          <select
            id="citation-format"
            className="input settings-select"
            value={citationFormat}
            onChange={(e) => setCitationFormat(e.target.value as CitationFormat)}
          >
            <option value="apa">APA</option>
            <option value="acm">ACM</option>
          </select>
        </InlineField>

        <label className="settings-cap-inline-check settings-personal-panel__check">
          <input type="checkbox" checked={planConfirm} onChange={(e) => setPlanConfirm(e.target.checked)} />
          执行前展示工作流拓扑并确认（plan_confirm）
        </label>

        <div className="settings-personal-panel__actions">
          <button type="button" className="btn-primary btn-sm" onClick={() => void onSave()} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </FunctionalDocShell>
  );
}
