import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8001";

export async function GET(req: NextRequest) {
  try {
    // Bulletproof extraction from the URL: /api/agent/123/trace
    const pathSegments = req.nextUrl.pathname.split('/');
    const taskId = pathSegments[3]; // Gets the ID directly from the URL string

    const res = await fetch(`${ORCHESTRATOR_URL}/api/agent/${taskId}/trace`);

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