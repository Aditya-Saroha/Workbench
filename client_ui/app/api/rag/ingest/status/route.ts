import { NextResponse } from "next/server";

const RAG_URL = process.env.RAG_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  try {
    const res = await fetch(`${RAG_URL}/ingest/status`, { cache: "no-store" });
    const body = await res.json().catch(() => ({}));
    return NextResponse.json(body, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Could not reach the RAG service" }, { status: 502 });
  }
}