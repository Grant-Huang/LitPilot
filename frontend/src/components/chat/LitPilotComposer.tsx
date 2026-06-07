"use client";

import { useCallback, useRef } from "react";
import { Input, Tag, Tooltip, message } from "antd";
import {
  ArrowUpOutlined,
  CloseOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { parseUrlListFile } from "@/lib/parseUrlList";
import type { LiteratureStreamPhase } from "@/lib/literatureStreamPhase";

const { TextArea } = Input;

type LitPilotComposerProps = {
  input: string;
  onInputChange: (value: string) => void;
  fetchUrls: string[];
  onFetchUrlsChange: (urls: string[]) => void;
  /** 与设置页 max_fetch_urls 一致，默认 50 上限 */
  maxFetchUrls?: number;
  streamPhase: LiteratureStreamPhase;
  isStreamBusy: boolean;
  streamActivityHint?: string | null;
  streamActivityLevel?: "active" | "waiting" | "slow" | null;
  streamParallelismChips?: string[];
  onSend: () => void;
  onAbort: () => void;
  /** 首轮 new_topic 禁用「+」上传；多轮 append_urls 可用 */
  uploadDisabled?: boolean;
};

export function LitPilotComposer({
  input,
  onInputChange,
  fetchUrls,
  onFetchUrlsChange,
  maxFetchUrls = 50,
  streamPhase,
  isStreamBusy,
  streamActivityHint = null,
  streamActivityLevel = null,
  streamParallelismChips = [],
  onSend,
  onAbort,
  uploadDisabled = false,
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

  const canSend =
    (Boolean(input.trim()) || (fetchUrls.length > 0 && !uploadDisabled)) &&
    !isStreamBusy;

  return (
    <div className="litpilot-composer">
      <div className="litpilot-composer__dock">
        <div className="litpilot-composer__box">
          <div className="litpilot-composer__meta">
            {isStreamBusy && streamParallelismChips.length > 0 ? (
              <div
                className="litpilot-composer__readonly-chips"
                aria-label="当前并行度"
              >
                {streamParallelismChips.map((chip) => (
                  <span
                    key={chip}
                    className="litpilot-composer__chip litpilot-composer__chip--readonly"
                    title="当前任务并行度（只读）"
                  >
                    {chip}
                  </span>
                ))}
              </div>
            ) : null}
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
            disabled={isStreamBusy}
          />
          <div className="litpilot-composer__bar">
            <Tooltip
              title={
                uploadDisabled
                  ? "首轮请用文字描述主题；完成首轮后可追加文献链接"
                  : `上传链接列表（.txt / .csv / .json），最多 ${maxFetchUrls} 条（与设置一致）`
              }
            >
              <button
                type="button"
                className="litpilot-composer__attach"
                disabled={isStreamBusy || uploadDisabled}
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
{isStreamBusy ? (
              <button
                type="button"
                className="litpilot-composer__stop"
                aria-label="停止"
                onClick={onAbort}
              >
                <span className="litpilot-composer__stop-icon" aria-hidden />
              </button>
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
