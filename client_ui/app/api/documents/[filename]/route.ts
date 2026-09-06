// Path: app/api/documents/[filename]/route.ts
//
// Proxies to the RAG service directly (port likely different from the
// agent orchestrator — set RAG_SERVICE_URL to match wherever
// `rag_service.py` actually runs; 8000 below is a placeholder, not a
// confirmed default).

import { NextRequest, NextResponse } from "next/server";

const RAG_SERVICE_URL = process.env.RAG_URL ?? process.env.RAG_SERVICE_URL ?? "http://127.0.0.1:8000";

export async function DELETE(req: NextRequest) {
  try {
    const pathSegments = req.nextUrl.pathname.split("/");
    const filename = decodeURIComponent(pathSegments[pathSegments.length - 1]);

    const res = await fetch(`${RAG_SERVICE_URL}/documents/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    });

    const body = await res.json().catch(() => ({}));

    if (!res.ok) {
      return NextResponse.json({ error: "Failed to delete", detail: body.detail }, { status: res.status });
    }

    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ error: "RAG service unreachable" }, { status: 502 });
  }
}