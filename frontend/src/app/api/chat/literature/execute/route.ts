import { NextRequest } from "next/server";

/**
 * @deprecated Use POST /api/tasks + GET /api/tasks/{id}/stream instead.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(_req: NextRequest) {
  return new Response(
    JSON.stringify({
      detail:
        "Direct SSE execute is removed. Create a background task via POST /api/tasks, then subscribe to GET /api/tasks/{task_id}/stream.",
    }),
    {
      status: 410,
      headers: { "Content-Type": "application/json" },
    },
  );
}
