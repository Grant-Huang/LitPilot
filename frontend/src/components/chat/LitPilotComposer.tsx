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
  literatureSourceMode?: LiteratureSourceMode;
  streaming: boolean;
  onSend: () => void;
  onAbort: () => void;
};

export function LitPilotComposer({
  input,
  onInputChange,
  fetchUrls,
  onFetchUrlsChange,
  literatureSourceMode = "merge",
  streaming,
  onSend,
  onAbort,
}: LitPilotComposerProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      try {
        const urls = await parseUrlListFile(file);
        if (!urls.length) {
          message.warning("未在文件中找到有效 http(s) 链接");
          return;
        }
        onFetchUrlsChange(urls);
        message.success(`已添加 ${urls.length} 个抓取链接`);
      } catch {
        message.error("无法解析链接列表文件");
      }
    },
    [onFetchUrlsChange],
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

  const sourceHint =
    fetchUrls.length > 0
      ? literatureSourceMode === "user_only"
        ? "当前：仅用户列表，将跳过 Tavily 网络检索"
        : "当前：合并模式，您的链接将优先抓取"
      : literatureSourceMode === "user_only"
        ? "仅用户列表模式：上传链接后跳过检索；未上传时将自动 Tavily 检索"
        : null;

  return (
    <div className="litpilot-composer">
      <div className="litpilot-composer__dock">
        <div className="litpilot-composer__box">
          {(fetchUrls.length > 0 || sourceHint) && (
            <div className="litpilot-composer__urls">
              {fetchUrls.length > 0 && (
                <Tag
                  closable
                  onClose={() => onFetchUrlsChange([])}
                  closeIcon={<CloseOutlined />}
                >
                  已添加 {fetchUrls.length} 个 web_fetch 链接
                </Tag>
              )}
              {sourceHint ? (
                <span className="litpilot-composer__source-hint">{sourceHint}</span>
              ) : null}
            </div>
          )}
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
            <Tooltip title="上传链接列表（.txt / .csv / .json），加入 web_fetch 抓取队列">
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
            <span className="litpilot-composer__hint">
              {streaming ? "执行中…" : "Enter 发送 · Shift+Enter 换行"}
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
