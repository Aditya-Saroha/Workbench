import { NextResponse } from "next/server";

const ROUTER_URL = process.env.ROUTER_URL ?? "http://127.0.0.1:11435";

export async function GET() {
  try {
    const [modelsRes, gpuRes] = await Promise.all([
      fetch(`${ROUTER_URL}/v1/router/models`, { cache: "no-store" }),
      fetch(`${ROUTER_URL}/v1/router/gpu`, { cache: "no-store" }),
    ]);

    const models = modelsRes.ok ? await modelsRes.json() : null;
    const gpu = gpuRes.ok ? await gpuRes.json() : null;

    return NextResponse.json({ online: true, models, gpu });
  } catch {
    return NextResponse.json({ online: false, models: null, gpu: null });
  }
}
