import { NextRequest } from "next/server";
import { getBackendBase } from "@/lib/backendUrl";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

type RouteContext = { params: Promise<{ taskId: string }> };

export async function GET(req: NextRequest, context: RouteContext) {
  const { taskId } = await context.params;
  const backendBase = getBackendBase();
  const search = req.nextUrl.search;
  const target = `${backendBase}/api/tasks/${encodeURIComponent(taskId)}/stream${search}`;

  let upstream: Response;
  try {
    // 透传客户端断开信号：浏览器关闭标签页时，上游 FastAPI 会立刻收到 cancel，
    // 避免任务流协程 + DB 轮询泄漏。
    upstream = await fetch(target, {
      method: "GET",
      cache: "no-store",
      signal: req.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      return new Response(null, { status: 499 });
    }
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
