import { NextRequest, NextResponse } from "next/server";
import {
  buildProxyResponseHeaders,
  buildUpstreamHeaders,
} from "@/lib/apiProxy";
import { getBackendBase } from "@/lib/backendUrl";

/**
 * 运行时透传 /api/* 到 FastAPI 后端。
 * 比 next.config rewrites 更可靠：BACKEND_URL 在 Vercel 运行时读取，无需构建时写死。
 * 更具体的路由（如 literature/execute）会优先生效。
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DEFAULT_UPSTREAM_TIMEOUT_MS = 120_000;

type RouteContext = { params: Promise<{ path: string[] }> };

function combineSignals(signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController();
  for (const s of signals) {
    if (s.aborted) {
      controller.abort(s.reason);
      return controller.signal;
    }
    s.addEventListener("abort", () => controller.abort(s.reason), { once: true });
  }
  return controller.signal;
}

async function proxyRequest(req: NextRequest, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  const backendBase = getBackendBase();
  const subpath = path.join("/");
  const target = `${backendBase}/api/${subpath}${req.nextUrl.search}`;

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  // 客户端断开 + 超时同时生效，任一触发都会取消上游请求，避免 worker 泄漏。
  const timeoutSignal = AbortSignal.timeout(DEFAULT_UPSTREAM_TIMEOUT_MS);
  const upstreamSignal = combineSignals([req.signal, timeoutSignal]);

  let upstream: Response;
  try {
    // 注意：body 改为直接转发 req.body 流（duplex: "half"），避免大上传被全量缓冲到 Node 内存。
    const init: RequestInit & { duplex?: "half" } = {
      method: req.method,
      headers: buildUpstreamHeaders(req),
      cache: "no-store",
      signal: upstreamSignal,
    };
    if (hasBody) {
      init.body = req.body as unknown as BodyInit;
      init.duplex = "half";
    }
    upstream = await fetch(target, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      // 客户端主动断开或超时：不再产出响应
      return NextResponse.json(
        { status: "error", message: "上游请求已取消或超时" },
        { status: 504 },
      );
    }
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { status: "error", message: `无法连接后端 ${backendBase}: ${msg}` },
      { status: 502 },
    );
  }

  // 关键修复：直接以流式方式转发 upstream.body，
  // 既支持 SSE / chunked，也避免大响应全量缓冲到内存。
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: buildProxyResponseHeaders(upstream),
  });
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
