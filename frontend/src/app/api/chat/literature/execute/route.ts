import { NextRequest } from "next/server";

/**
 * 流式透传 SSE — Next rewrites 会缓冲 event-stream，导致前端长时间无输出。
 * 此 Route Handler 优先于 next.config rewrites（同路径）。
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const backendBase =
  process.env.BACKEND_URL ||
  process.env.API_PROXY_TARGET ||
  "http://127.0.0.1:8001";

export async function POST(req: NextRequest) {
  const body = await req.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${backendBase}/api/chat/literature/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return new Response(JSON.stringify({ detail: `无法连接后端 ${backendBase}: ${msg}` }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (!upstream.ok) {
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") || "application/json",
      },
    });
  }

  if (!upstream.body) {
    return new Response(JSON.stringify({ detail: "后端未返回流式 body" }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") || "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
