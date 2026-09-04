"use client";

import { useEffect, useState } from "react";
import { getStatus, StatusResponse } from "@/lib/api";
import { ShieldCheck, CircleDot } from "lucide-react";

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
    <div className="flex h-full w-64 flex-col overflow-y-auto bg-black">
      <div className="p-4">
        <div className="mb-3 font-bold text-neutral-400"># SYSTEM_STATUS</div>
        <div className="flex items-start gap-2 text-emerald-400">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <div className="font-bold text-emerald-300">No external calls</div>
            <div className="mt-1 text-neutral-300">All inference stays on this machine</div>
          </div>
        </div>
      </div>

      <div className="border-t border-neutral-800 p-4">
        <div className="mb-3 font-bold text-neutral-400"># ROUTER_DAEMON</div>
        <div className="flex items-center gap-2 font-bold">
          <CircleDot className={status?.online ? "h-4 w-4 text-emerald-400" : "h-4 w-4 text-red-500"} />
          <span className={status?.online ? "text-emerald-300" : "text-red-400"}>
            {status === null ? "checking..." : status.online ? "127.0.0.1:11435" : "unreachable"}
          </span>
        </div>
      </div>

      <div className="border-t border-neutral-800 p-4">
        <div className="mb-3 font-bold text-neutral-400"># CONFIGURED_MODELS</div>
        <div className="flex flex-col gap-4">
          {models?.length ? (
            models.map((m) => (
              <div key={m.name} className="flex flex-col gap-1.5">
                <span className="font-bold text-sky-300">{m.name}</span>
                {m.purpose && (
                  <div className="flex flex-wrap gap-1.5">
                    {m.purpose.slice(0, 3).map((p) => (
                      <span key={p} className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] font-medium text-neutral-100">
                        {p}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))
          ) : (
            <span className="text-neutral-400">
              {status?.online === false ? "Start router to see models" : "—"}
            </span>
          )}
        </div>
      </div>

      <div className="mt-auto border-t border-neutral-800 p-4">
        <div className="mb-2 font-bold text-neutral-400"># COMPUTE_NODE</div>
        <div className="font-bold text-amber-400">CPU-only · no dedicated GPU</div>
      </div>
    </div>
  );
}