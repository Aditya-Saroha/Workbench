import { NextRequest, NextResponse } from "next/server";

const ROUTER_URL = process.env.ROUTER_URL ?? "http://127.0.0.1:11435";

export async function POST(req: NextRequest) {
  const body = await req.json();

  try {
    const res = await fetch(`${ROUTER_URL}/v1/chat/completions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: `Router returned ${res.status}`, detail: text },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      {
        error: "Could not reach the router",
        detail:
          "Is `ollama-agent-router serve --config ollama-agent-router.yaml` running on port 11435?",
      },
      { status: 502 }
    );
  }
}
