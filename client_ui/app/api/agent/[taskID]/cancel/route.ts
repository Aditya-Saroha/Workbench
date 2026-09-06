import { NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8001";

export async function POST(req: Request) {
  const url = new URL(req.url);
  const pathSegments = url.pathname.split("/");
  const taskId = pathSegments[3];

  try {
    const res = await fetch(`${ORCHESTRATOR_URL}/api/agent/${taskId}/cancel`, {
      method: "POST",
    });
    const body = await res.json().catch(() => ({}));
    return NextResponse.json(body, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: "Orchestrator unreachable" },
      { status: 502 }
    );
  }
}