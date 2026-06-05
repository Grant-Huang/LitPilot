import { NextRequest } from "next/server";

/** 不透传到上游或下游的 hop-by-hop / 编码相关头。 */
export const PROXY_SKIP_REQUEST = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  "accept-encoding",
]);

export const PROXY_SKIP_RESPONSE = new Set([
  ...PROXY_SKIP_REQUEST,
  "content-encoding",
]);

export function buildUpstreamHeaders(req: NextRequest): Headers {
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!PROXY_SKIP_REQUEST.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  return headers;
}

export function buildProxyResponseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!PROXY_SKIP_RESPONSE.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  return headers;
}
