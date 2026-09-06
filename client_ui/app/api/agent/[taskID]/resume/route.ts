import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8001";

export async function POST(req: NextRequest) {
  try {
    const pathSegments = req.nextUrl.pathname.split('/');
    const taskId = pathSegments[3]; 

    const res = await fetch(`${ORCHESTRATOR_URL}/api/agent/${taskId}/resume`, {
      method: "POST",
      headers: { "x-session-id": req.headers.get("x-session-id") ?? "default" },
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json({ error: "Failed to resume", detail: text }, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (err) {
    return NextResponse.json({ error: "Orchestrator unreachable" }, { status: 502 });
  }
}