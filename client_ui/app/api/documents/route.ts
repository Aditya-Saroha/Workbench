import { NextResponse } from "next/server";

const RAG_URL = process.env.RAG_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${RAG_URL}/documents`, { cache: "no-store" });
    if (!res.ok) {
      return NextResponse.json({ error: "rag_unreachable" }, { status: 502 });
    }
    return NextResponse.json(await res.json());
  } catch (err) {
    console.error("GET /api/documents failed:", err);
    return NextResponse.json({ error: "rag_unreachable" }, { status: 502 });
  }
}