import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8001";

export async function POST(req: NextRequest) {
  // We MUST use .json() here, not .formData()
  const body = await req.json();

  try {
    const res = await fetch(`${ORCHESTRATOR_URL}/api/agent/task`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: `Orchestrator returned ${res.status}`, detail: text },
        { status: res.status }
      );
    }

    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json(
      {
        error: "Could not reach the Agent Orchestrator",
        detail: "Is `uvicorn orchestrator.main:app --port 8001` running?",
      },
      { status: 502 }
    );
  }
}