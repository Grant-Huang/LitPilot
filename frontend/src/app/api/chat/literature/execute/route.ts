import { NextRequest } from "next/server";
import { getBackendBase } from "@/lib/backendUrl";

/**
 * 流式透传 SSE — Next rewrites 会缓冲 event-stream，导致前端长时间无输出。
 * 此 Route Handler 优先于 next.config rewrites（同路径）。
 *
 * 将 delivery=process 的 text 事件转为 extension(process_text)，避免混入 chat textContent。
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

type SseEnvelope = {
  type: string;
  schema_version?: string;
  payload: Record<string, unknown>;
};

function transformSseLine(line: string): string {
  if (!line.startsWith("data: ")) return line;
  const raw = line.slice(6).trim();
  if (raw === "[DONE]") return line;
  let parsed: SseEnvelope;
  try {
    parsed = JSON.parse(raw) as SseEnvelope;
  } catch {
    return line;
  }
  if (parsed.type !== "text" || !parsed.payload || typeof parsed.payload !== "object") {
    return line;
  }
  const delivery = parsed.payload.delivery;
  if (delivery === "process") {
    const ext: SseEnvelope = {
      type: "extension",
      schema_version: parsed.schema_version ?? "1.0",
      payload: {
        name: "process_text",
        version: "1.0",
        data: { delta: String(parsed.payload.delta ?? "") },
      },
    };
    return `data: ${JSON.stringify(ext)}`;
  }
  const { delivery: _d, ...rest } = parsed.payload;
  return `data: ${JSON.stringify({ ...parsed, payload: rest })}`;
}

function createSseTransformStream(): TransformStream<Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";
  return new TransformStream({
    transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      const out = lines.map(transformSseLine).join("\n");
      if (out.length > 0) {
        controller.enqueue(encoder.encode(`${out}\n`));
      }
    },
    flush(controller) {
      if (buffer.length > 0) {
        controller.enqueue(encoder.encode(transformSseLine(buffer)));
      }
    },
  });
}

export async function POST(req: NextRequest) {
  const backendBase = getBackendBase();
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

  const transformed = upstream.body.pipeThrough(createSseTransformStream());

  return new Response(transformed, {
    status: 200,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") || "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
