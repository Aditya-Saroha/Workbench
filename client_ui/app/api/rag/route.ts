import { NextRequest, NextResponse } from "next/server";

const RAG_URL = process.env.RAG_URL ?? "http://127.0.0.1:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();

  try {
    const res = await fetch(`${RAG_URL}/query`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-session-id": req.headers.get("x-session-id") ?? "default" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: `RAG service returned ${res.status}`, detail: text },
        { status: res.status }
      );
    }

    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json(
      {
        error: "Could not reach the RAG service",
        detail:
          "Is `uvicorn rag_server:app --port 8081` running from your rag/ folder?",
      },
      { status: 502 }
    );
  }
}
