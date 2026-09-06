import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8001";

// Without this, Next.js's App Router caches GET fetches made inside Route
// Handlers by default. Every poll hits the identical URL for a given
// taskId, so without an explicit opt-out every request after the first
// was a cache hit that replayed the first (early) response forever —
// the frontend never saw status flip to "completed".
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    // Bulletproof extraction from the URL: /api/agent/123/trace
    const pathSegments = req.nextUrl.pathname.split('/');
    const taskId = pathSegments[3]; // Gets the ID directly from the URL string

    const res = await fetch(`${ORCHESTRATOR_URL}/api/agent/${taskId}/trace`, {
      cache: "no-store",
      headers: { "x-session-id": req.headers.get("x-session-id") ?? "default" },
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: `Task ${taskId} not found in orchestrator` },
        { status: res.status }
      );
    }

    return NextResponse.json(await res.json());
  } catch (err) {
    return NextResponse.json({ error: "Orchestrator unreachable" }, { status: 502 });
  }
}