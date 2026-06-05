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

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxyRequest(req: NextRequest, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  const backendBase = getBackendBase();
  const subpath = path.join("/");
  const target = `${backendBase}/api/${subpath}${req.nextUrl.search}`;

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers: buildUpstreamHeaders(req),
      body: hasBody ? await req.arrayBuffer() : undefined,
      cache: "no-store",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { status: "error", message: `无法连接后端 ${backendBase}: ${msg}` },
      { status: 502 },
    );
  }

  const body = await upstream.arrayBuffer();
  return new NextResponse(body, {
    status: upstream.status,
    headers: buildProxyResponseHeaders(upstream),
  });
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
