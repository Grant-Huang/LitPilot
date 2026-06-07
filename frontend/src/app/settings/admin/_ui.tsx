"use client";

import { useEffect } from "react";
import clsx from "clsx";
import { Tooltip } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";

export function FieldTip({ title }: { title: string }) {
  return (
    <Tooltip title={title} placement="topLeft">
      <button
        type="button"
        className="settings-field-tip"
        aria-label="帮助说明"
        tabIndex={-1}
        onClick={(e) => e.preventDefault()}
      >
        <QuestionCircleOutlined />
      </button>
    </Tooltip>
  );
}

export function InlineField({
  label,
  htmlFor,
  children,
  className,
  tip,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
  tip?: string;
}) {
  return (
    <div className={clsx("settings-inline-field", className)}>
      <label className="label settings-inline-field__label" htmlFor={htmlFor}>
        <span className="settings-inline-field__label-text">{label}</span>
        {tip ? <FieldTip title={tip} /> : null}
      </label>
      <div className="settings-inline-field__control">{children}</div>
    </div>
  );
}

export function InlineCheck({
  label,
  checked,
  onChange,
  tip,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  tip?: string;
}) {
  return (
    <InlineField label={label} tip={tip}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </InlineField>
  );
}

export function SettingStatus({ status, hint }: { status?: string; hint?: string }) {
  const normalized = status === "ok" ? "ok" : status === "fail" ? "fail" : "pending";
  const label = normalized === "ok" ? "已通过" : normalized === "fail" ? "失败" : "未测试";
  const defaultTitle =
    normalized === "ok" ? "连接测试已通过" : normalized === "fail" ? "连接测试失败" : "尚未测试";
  return (
    <span
      className={clsx(
        "settings-cred-status",
        normalized === "ok" && "settings-cred-status--ok",
        normalized === "fail" && "settings-cred-status--fail",
      )}
      title={hint || defaultTitle}
    >
      {label}
    </span>
  );
}

export function SettingToolbar({
  title,
  status,
  feedback,
  feedbackOk,
  actions,
  titleMuted,
  extra,
  statusHint,
}: {
  title: React.ReactNode;
  status?: string;
  feedback?: string;
  feedbackOk?: boolean;
  actions: React.ReactNode;
  titleMuted?: boolean;
  extra?: React.ReactNode;
  statusHint?: string;
}) {
  const normalizedStatus = status === "ok" ? "ok" : status === "fail" ? "fail" : "pending";
  const showFeedback = Boolean(
    feedback && !(feedbackOk && (normalizedStatus === "ok" || normalizedStatus === "fail")),
  );

  return (
    <div className="settings-cred-row__toolbar">
      <div className="settings-cred-row__titleline">
        <span className={clsx("settings-cred-row__title", titleMuted && "settings-cap-card__title--off")}>
          {title}
        </span>
        {extra}
        {status !== undefined ? <SettingStatus status={status} hint={statusHint} /> : null}
        {showFeedback ? (
          <span
            className={clsx(
              "settings-cred-row__feedback",
              feedbackOk ? "settings-cred-row__feedback--ok" : "settings-cred-row__feedback--err",
            )}
          >
            {feedback}
          </span>
        ) : null}
      </div>
      <div className="settings-cred-row__actions">{actions}</div>
    </div>
  );
}

export function feedbackOk(msg: string): boolean {
  return msg.includes("通过") || msg === "已保存" || msg === "已创建" || msg === "测试完成";
}

export function useUnsavedGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);
}

export function SettingsListPanel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={clsx("card settings-panel", className)}>{children}</div>;
}
