"use client";

import { useState } from "react";
import { Spin } from "antd";
import { FieldTip, InlineField, SettingToolbar } from "../_ui";
import { settingsApiV2 } from "@/lib/settingsApiV2";
import { toastError, toastSuccess, toastWarning } from "@/lib/toastFeedback";
import { errorMessage } from "../../_shared";

const DEFAULT_FETCH_URL =
  "https://sol.sbc.org.br/index.php/webmedia/article/view/38018";
const DEFAULT_SEARCH_QUERY = "systematic literature review methods";

type Props = {
  fetchProvider: string;
  pdfExtractBackend: string;
  fetchTimeoutSec: number;
  searchProvider: string;
};

export function WebProviderTestPanel({
  fetchProvider,
  pdfExtractBackend,
  fetchTimeoutSec,
  searchProvider,
}: Props) {
  const [fetchUrl, setFetchUrl] = useState(DEFAULT_FETCH_URL);
  const [fetchLoading, setFetchLoading] = useState(false);
  const [fetchResult, setFetchResult] = useState<{
    ok: boolean;
    provider: string;
    raw_bytes: number;
    text_chars: number;
    title?: string;
    preview?: string;
    note?: string;
    is_pdf?: boolean;
    pdf_extract_backend?: string | null;
    resolved_pdf_url?: string | null;
  } | null>(null);

  const [searchQuery, setSearchQuery] = useState(DEFAULT_SEARCH_QUERY);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResult, setSearchResult] = useState<{
    ok: boolean;
    provider: string;
    hits: number;
    note?: string;
    results?: Array<{ title?: string; url?: string }>;
  } | null>(null);

  const runFetchTest = async () => {
    const trimmed = fetchUrl.trim();
    if (!trimmed) {
      toastWarning("请输入 URL");
      return;
    }
    setFetchLoading(true);
    setFetchResult(null);
    try {
      const res = await settingsApiV2.testWebFetchUrl({
        url: trimmed,
        provider: fetchProvider,
        pdf_extract_backend: pdfExtractBackend,
      });
      setFetchResult(res);
      if (res.ok) {
        toastSuccess(
          `web_fetch 测试通过（${res.provider}，${res.text_chars} 字）`,
        );
      } else {
        toastWarning(res.note || "正文过短或未解析到有效内容");
      }
    } catch (e: unknown) {
      toastError(errorMessage(e));
    } finally {
      setFetchLoading(false);
    }
  };

  const runSearchTest = async () => {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      toastWarning("请输入检索词");
      return;
    }
    setSearchLoading(true);
    setSearchResult(null);
    try {
      const res = await settingsApiV2.testWebSearch({
        query: trimmed,
        provider: searchProvider,
      });
      setSearchResult(res);
      if (res.ok) {
        toastSuccess(`web_search 测试通过（${res.provider}，命中 ${res.hits} 条）`);
      } else {
        toastWarning(res.note || "无命中结果");
      }
    } catch (e: unknown) {
      toastError(errorMessage(e));
    } finally {
      setSearchLoading(false);
    }
  };

  return (
    <div className="card settings-cred-row settings-web-provider-test">
      <SettingToolbar
        title={
          <span className="settings-cap-card__title-block">
            <span>
              Web 后端连通测试
              <FieldTip title="使用能力绑定页当前保存的后端配置进行探测；改后端后请先在能力绑定页保存。" />
            </span>
            <span className="settings-cap-card__subtitle">
              fetch · {fetchProvider} · search · {searchProvider}
            </span>
          </span>
        }
        actions={<span />}
      />

      <InlineField label="抓取测试" htmlFor="web-provider-fetch-url">
        <div className="settings-web-provider-test__row">
          <input
            id="web-provider-fetch-url"
            className="input"
            value={fetchUrl}
            onChange={(e) => setFetchUrl(e.target.value)}
            placeholder="https://..."
          />
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={fetchLoading}
            onClick={() => void runFetchTest()}
          >
            {fetchLoading ? <Spin size="small" /> : null}
            测试 web_fetch
          </button>
        </div>
      </InlineField>
      {fetchResult ? (
        <div
          className={`settings-web-fetch-test__result${
            fetchResult.ok ? " settings-web-fetch-test__result--ok" : ""
          }`}
        >
          <p className="settings-web-fetch-test__meta">
            {fetchResult.provider} · 原始 {fetchResult.raw_bytes} 字节 · 正文{" "}
            {fetchResult.text_chars} 字
            {fetchResult.is_pdf ? " · PDF" : ""}
            {fetchResult.title ? ` · ${fetchResult.title}` : ""}
            {fetchTimeoutSec ? ` · 超时上限 ${fetchTimeoutSec}s` : ""}
          </p>
          {fetchResult.preview ? (
            <pre className="settings-web-fetch-test__preview">{fetchResult.preview}</pre>
          ) : null}
        </div>
      ) : null}

      <InlineField label="检索测试" htmlFor="web-provider-search-q">
        <div className="settings-web-provider-test__row">
          <input
            id="web-provider-search-q"
            className="input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="检索词…"
          />
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={searchLoading}
            onClick={() => void runSearchTest()}
          >
            {searchLoading ? <Spin size="small" /> : null}
            测试 web_search
          </button>
        </div>
      </InlineField>
      {searchResult ? (
        <div
          className={`settings-web-fetch-test__result${
            searchResult.ok ? " settings-web-fetch-test__result--ok" : ""
          }`}
        >
          <p className="settings-web-fetch-test__meta">
            {searchResult.provider} · {searchResult.note || `命中 ${searchResult.hits} 条`}
          </p>
          {searchResult.results?.length ? (
            <ul className="settings-web-provider-test__hits">
              {searchResult.results.map((r, i) => (
                <li key={`${r.url || i}`}>
                  {r.title || r.url || "—"}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
