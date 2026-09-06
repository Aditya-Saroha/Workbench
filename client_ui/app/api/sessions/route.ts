import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8001";

export async function GET(req: NextRequest) {
  try {
    const res = await fetch(`${ORCHESTRATOR_URL}/api/sessions`, { cache: "no-store" });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json({ error: "Orchestrator unreachable" }, { status: 502 });
  }
}
