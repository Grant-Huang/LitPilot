"use client";



import { useEffect, useMemo, useState } from "react";

import { Spin } from "antd";

import { feedbackOk, InlineField, SettingToolbar } from "../_ui";

import { SettingsLoading, errorMessage } from "../../_shared";

import { settingsApiV2, type SystemCapability } from "@/lib/settingsApiV2";



type OutlineMode = "off" | "lite" | "full";

type PostRefineMode = "off" | "lite";



const OUTLINE_MODE_OPTIONS: { value: OutlineMode; label: string }[] = [

  { value: "off", label: "关闭" },

  { value: "lite", label: "智能（推荐）" },

  { value: "full", label: "始终分章" },

];



const POST_REFINE_OPTIONS: { value: PostRefineMode; label: string }[] = [

  { value: "off", label: "关闭" },

  { value: "lite", label: "轻量校验" },

];



const OUTLINE_MODE_TIPS: Record<OutlineMode, string> = {

  off: "一次性生成整篇综述，不拆子主题检索与分章写作；适合短问题或调试。",

  lite: "检测到「其一、其二…」等多 aspect 提问时，自动拆子主题检索、挂载文献、按章节流式写作再合并；单主题仍一次性生成。",

  full: "无论是否多 aspect，均走大纲 + 分章写作（含导言/结论）；耗时与 token 更高，结构最可控。",

};



const POST_REFINE_TIPS: Record<PostRefineMode, string> = {

  off: "交付前不做规则后处理，综述原文直接保存。",

  lite: "拼接后去除套话结语、检测缺失章节、统计「待核实」标记，并推送 refine 报告 SSE。",

};



function parseOutlineMode(raw: unknown): OutlineMode {

  const v = String(raw || "lite").toLowerCase();

  return v === "off" || v === "full" ? v : "lite";

}



function parsePostRefineMode(raw: unknown): PostRefineMode {

  return String(raw || "lite").toLowerCase() === "off" ? "off" : "lite";

}



function SettingTip({ children }: { children: React.ReactNode }) {

  return <p className="settings-field-tip">{children}</p>;

}



export default function AdminPromptsPage() {

  const [loading, setLoading] = useState(true);

  const [msg, setMsg] = useState("");

  const [caps, setCaps] = useState<SystemCapability[]>([]);

  const [saving, setSaving] = useState(false);

  const [tpl, setTpl] = useState("");

  const [savedTpl, setSavedTpl] = useState("");

  const [enablePaperAttributes, setEnablePaperAttributes] = useState(true);

  const [savedEnablePaperAttributes, setSavedEnablePaperAttributes] = useState(true);

  const [outlineMode, setOutlineMode] = useState<OutlineMode>("lite");

  const [savedOutlineMode, setSavedOutlineMode] = useState<OutlineMode>("lite");

  const [postRefineMode, setPostRefineMode] = useState<PostRefineMode>("lite");

  const [savedPostRefineMode, setSavedPostRefineMode] = useState<PostRefineMode>("lite");



  const promptsCap = useMemo(() => caps.find((c) => c.capability_id === "prompts") || null, [caps]);

  const dirty =

    tpl !== savedTpl ||

    enablePaperAttributes !== savedEnablePaperAttributes ||

    outlineMode !== savedOutlineMode ||

    postRefineMode !== savedPostRefineMode;



  useEffect(() => {

    void settingsApiV2

      .getSystemCapabilities()

      .then((res) => {

        const items = res.items || [];

        setCaps(items);

        const p = items.find((c) => c.capability_id === "prompts");

        const text = String(p?.params?.review_system_prompt_template || "");

        setTpl(text);

        setSavedTpl(text);

        const enabled = Boolean(p?.params?.enable_paper_attributes ?? true);

        setEnablePaperAttributes(enabled);

        setSavedEnablePaperAttributes(enabled);

        const om = parseOutlineMode(p?.params?.outline_mode);

        setOutlineMode(om);

        setSavedOutlineMode(om);

        const pr = parsePostRefineMode(p?.params?.post_refine_mode);

        setPostRefineMode(pr);

        setSavedPostRefineMode(pr);

      })

      .catch((e: unknown) => setMsg(errorMessage(e)))

      .finally(() => setLoading(false));

  }, []);



  const onSave = async () => {

    if (!promptsCap) return;

    setSaving(true);

    setMsg("");

    try {

      const saved = await settingsApiV2.updateCapability("prompts", {

        params: {

          ...(promptsCap.params || {}),

          review_system_prompt_template: tpl,

          enable_paper_attributes: enablePaperAttributes,

          outline_mode: outlineMode,

          post_refine_mode: postRefineMode,

        },

      });

      setCaps((prev) => prev.map((c) => (c.capability_id === saved.capability_id ? saved : c)));

      setSavedTpl(tpl);

      setSavedEnablePaperAttributes(enablePaperAttributes);

      setSavedOutlineMode(outlineMode);

      setSavedPostRefineMode(postRefineMode);

      setMsg("已保存");

    } catch (e: unknown) {

      setMsg(e instanceof Error ? e.message : String(e));

    } finally {

      setSaving(false);

    }

  };



  if (loading) {
    return <SettingsLoading />;
  }



  return (

    <div className="card settings-section settings-section--compact settings-prompts">

      <SettingToolbar

        title="综述 System Prompt"

        feedback={msg}

        feedbackOk={feedbackOk(msg)}

        actions={

          <button type="button" className="btn-primary btn-sm" disabled={saving || !dirty || !promptsCap} onClick={() => void onSave()}>

            {saving ? <Spin size="small" /> : null}

            保存

          </button>

        }

      />



      <div className="settings-prompts__toggles">

        <label className="settings-cap-inline-check settings-prompts__toggle">

          <input

            type="checkbox"

            checked={enablePaperAttributes}

            onChange={(e) => setEnablePaperAttributes(e.target.checked)}

          />

          启用文献结构化（AttributeTree lite）

        </label>

        <SettingTip>

          抓取后为每篇文献抽取 problem / method / findings 等字段，写入 paper_index，供大纲挂载与各章写作引用。

        </SettingTip>



        <InlineField label="大纲驱动分章" htmlFor="outline-mode">

          <select

            id="outline-mode"

            className="input settings-prompts__select"

            value={outlineMode}

            onChange={(e) => setOutlineMode(parseOutlineMode(e.target.value))}

          >

            {OUTLINE_MODE_OPTIONS.map((o) => (

              <option key={o.value} value={o.value}>

                {o.label}

              </option>

            ))}

          </select>

        </InlineField>

        <SettingTip>{OUTLINE_MODE_TIPS[outlineMode]}</SettingTip>



        <InlineField label="综述后处理" htmlFor="post-refine-mode">

          <select

            id="post-refine-mode"

            className="input settings-prompts__select"

            value={postRefineMode}

            onChange={(e) => setPostRefineMode(parsePostRefineMode(e.target.value))}

          >

            {POST_REFINE_OPTIONS.map((o) => (

              <option key={o.value} value={o.value}>

                {o.label}

              </option>

            ))}

          </select>

        </InlineField>

        <SettingTip>{POST_REFINE_TIPS[postRefineMode]}</SettingTip>

      </div>



      <textarea

        className="input settings-textarea font-mono settings-prompts__editor"

        value={tpl}

        onChange={(e) => setTpl(e.target.value)}

        spellCheck={false}

      />



      <p className="settings-prompts__hint">

        占位符：<code>{`{fmt_label}`}</code>、<code>{`{citation_format}`}</code>

      </p>

    </div>

  );

}


