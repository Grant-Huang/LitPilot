"use client";

import { useCallback, useRef } from "react";
import { Button, Input, Tag, Tooltip, message } from "antd";
import {
  ArrowUpOutlined,
  CloseOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { parseUrlListFile } from "@/lib/parseUrlList";

const { TextArea } = Input;

type LiteratureSourceMode = "merge" | "user_only";

type LitPilotComposerProps = {
  input: string;
  onInputChange: (value: string) => void;
  fetchUrls: string[];
  onFetchUrlsChange: (urls: string[]) => void;
  /** 与设置页 max_fetch_urls 一致，默认 50 上限 */
  maxFetchUrls?: number;
  literatureSourceMode?: LiteratureSourceMode;
  streaming: boolean;
  streamActivityHint?: string | null;
  streamActivityLevel?: "active" | "waiting" | "slow" | null;
  onSend: () => void;
  onAbort: () => void;
};

export function LitPilotComposer({
  input,
  onInputChange,
  fetchUrls,
  onFetchUrlsChange,
  maxFetchUrls = 50,
  literatureSourceMode = "merge",
  streaming,
  streamActivityHint = null,
  streamActivityLevel = null,
  onSend,
  onAbort,
}: LitPilotComposerProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      try {
        const { urls, totalFound, limit, truncated } = await parseUrlListFile(
          file,
          maxFetchUrls,
        );
        if (!urls.length) {
          message.warning("未在文件中找到有效 http(s) 链接");
          return;
        }
        onFetchUrlsChange(urls);
        if (truncated) {
          message.warning(
            `文件中共 ${totalFound} 条链接，已按当前设置保留前 ${limit} 条`,
          );
        }
        message.success(`已添加 ${urls.length} 个抓取链接`);
      } catch {
        message.error("无法解析链接列表文件");
      }
    },
    [maxFetchUrls, onFetchUrlsChange],
  );

  const onFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  const canSend = Boolean(input.trim()) && !streaming;

  return (
    <div className="litpilot-composer">
      <div className="litpilot-composer__dock">
        <div className="litpilot-composer__box">
          <div className="litpilot-composer__meta">
            <div className="litpilot-composer__chips" role="group" aria-label="文献来源模式">
              <span
                className={`litpilot-composer__chip${
                  literatureSourceMode === "merge"
                    ? " litpilot-composer__chip--active"
                    : ""
                }`}
              >
                合并检索
              </span>
              <span
                className={`litpilot-composer__chip${
                  literatureSourceMode === "user_only"
                    ? " litpilot-composer__chip--active"
                    : ""
                }`}
              >
                仅用户链接
              </span>
            </div>
            {fetchUrls.length > 0 ? (
              <Tag
                closable
                onClose={() => onFetchUrlsChange([])}
                closeIcon={<CloseOutlined />}
                className="litpilot-composer__url-tag"
              >
                {fetchUrls.length} 个链接
              </Tag>
            ) : null}
          </div>
          <TextArea
            className="litpilot-composer__input"
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder="描述你的研究主题或综述问题…"
            autoSize={{ minRows: 2, maxRows: 6 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                if (canSend) onSend();
              }
            }}
            disabled={streaming}
          />
          <div className="litpilot-composer__bar">
            <Tooltip
              title={`上传链接列表（.txt / .csv / .json），最多 ${maxFetchUrls} 条（与设置一致）`}
            >
              <button
                type="button"
                className="litpilot-composer__attach"
                disabled={streaming}
                aria-label="上传链接列表"
                onClick={() => fileRef.current?.click()}
              >
                <PlusOutlined />
              </button>
            </Tooltip>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.csv,.json,.md,text/plain,text/csv,application/json"
              className="litpilot-composer__file-input"
              onChange={onFileChange}
            />
            <span
              className={`litpilot-composer__hint${
                streamActivityLevel === "waiting" || streamActivityLevel === "slow"
                  ? " litpilot-composer__hint--pulse"
                  : ""
              }`}
            >
              {streaming
                ? streamActivityHint ||
                  (streamActivityLevel === "slow"
                    ? `仍在执行（已等待较久，可停止后重试）`
                    : "执行中…")
                : "Enter 发送 · Shift+Enter 换行"}
            </span>
            {streaming ? (
              <Button size="small" onClick={onAbort} danger>
                停止
              </Button>
            ) : (
              <button
                type="button"
                className="litpilot-composer__send"
                disabled={!canSend}
                aria-label="生成综述"
                onClick={onSend}
              >
                <ArrowUpOutlined />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
