// components/status-rail.tsx
"use client";

import { useEffect, useState } from "react";
import { getStatus, StatusResponse } from "@/lib/api";
import { ShieldCheck, Circle } from "lucide-react";

/**
 * Design tokens — shared across status-rail / chat-panel / context-panel:
 *   canvas    zinc-50   (app background)
 *   surface   white     (side rails, drawers)
 *   card      white + border-zinc-200
 *   text      zinc-900 primary · zinc-600 secondary · zinc-500 muted floor
 *   accent    indigo-600 (user bubble, focus rings — used sparingly)
 *   state     emerald-600 success · amber-600 attention · rose-600 danger
 *   type      font-mono = status/data layer · font-sans = human-read content
 *   radius    full = dots/pills · xl = controls · 2xl = cards/panels
 */

export function StatusRail() {
  const [status, setStatus] = useState<StatusResponse | null>(null);

  useEffect(() => {
    const poll = () => getStatus().then(setStatus).catch(() => {});
    poll();
    const id = setInterval(poll, 8000);
    return () => clearInterval(id);
  }, []);

  const models = (status?.models as any)?.models as
    | { name: string; purpose?: string[] }[]
    | undefined;

  return (
    <div className="flex h-full w-64 flex-col gap-6 overflow-y-auto border-r border-zinc-200 bg-white p-5">

      {/* Privacy assurance */}
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
        <div className="flex items-start gap-2.5">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
          <div className="font-sans">
            <div className="text-sm font-medium text-emerald-900">Runs entirely on this machine</div>
            <div className="mt-0.5 text-[13px] leading-snug text-emerald-700">Nothing leaves your device</div>
          </div>
        </div>
      </div>

      {/* Router status */}
      <div>
        <div className="mb-2.5 text-[11px] text-zinc-500">Router</div>
        <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-3 py-2.5">
          <Circle
            className={`h-2 w-2 shrink-0 ${
              status?.online ? "fill-emerald-500 text-emerald-500" : "fill-rose-500 text-rose-500"
            }`}
          />
          <span className="font-sans text-sm text-zinc-800">
            {status === null ? "Checking…" : status.online ? "Online · 127.0.0.1:11435" : "Unreachable"}
          </span>
        </div>
      </div>

      {/* Configured models */}
      <div>
        <div className="mb-2.5 text-[11px] text-zinc-500">Models</div>
        <div className="flex flex-col gap-2">
          {models?.length ? (
            models.map((m) => (
              <div key={m.name} className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2.5">
                <div className="text-[13px] text-zinc-800">{m.name}</div>
                {m.purpose && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {m.purpose.slice(0, 3).map((p) => (
                      <span
                        key={p}
                        className="rounded-full border border-zinc-200 bg-white px-2 py-0.5 text-[11px] text-zinc-600"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2.5 font-sans text-sm text-zinc-500">
              {status?.online === false ? "Start the router to see models" : "—"}
            </div>
          )}
        </div>
      </div>

      {/* Compute */}
      <div className="mt-auto border-t border-zinc-200 pt-4">
        <div className="text-[11px] text-zinc-500">Compute</div>
        <div className="mt-1.5 font-sans text-sm text-zinc-600">CPU only · no dedicated GPU</div>
      </div>

    </div>
  );
}