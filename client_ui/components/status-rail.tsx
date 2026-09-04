"use client";

import { useEffect, useState } from "react";
import { getStatus, StatusResponse } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { ShieldCheck, CircleDot } from "lucide-react";

export function StatusRail() {
  const [status, setStatus] = useState<StatusResponse | null>(null);

  useEffect(() => {
    const poll = () => getStatus().then(setStatus);
    poll();
    const id = setInterval(poll, 8000);
    return () => clearInterval(id);
  }, []);

  const models = (status?.models as any)?.models as
    | { name: string; purpose?: string[] }[]
    | undefined;

  return (
    <div className="flex h-full w-64 flex-col gap-3">
      <Panel>
        <div className="flex items-center gap-2 px-4 py-3">
          <ShieldCheck className="h-4 w-4 text-sage" strokeWidth={1.75} />
          <div>
            <div className="text-sm font-medium text-text">
              No external calls
            </div>
            <div className="text-xs text-muted">
              All inference stays on this machine
            </div>
          </div>
        </div>
      </Panel>

      <Panel className="flex-1 overflow-hidden">
        <PanelHeader>Router</PanelHeader>
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border">
          <CircleDot
            className={
              status?.online
                ? "h-3 w-3 text-sage"
                : "h-3 w-3 text-brick"
            }
            strokeWidth={2.5}
          />
          <span className="font-mono text-xs text-muted">
            {status === null
              ? "checking..."
              : status.online
              ? "127.0.0.1:11435"
              : "unreachable"}
          </span>
        </div>

        <div className="px-4 py-2.5">
          <div className="mb-2 text-xs text-muted">Configured models</div>
          <div className="flex flex-col gap-2">
            {models?.length ? (
              models.map((m) => (
                <div key={m.name} className="flex flex-col gap-1">
                  <span className="font-mono text-xs text-text">
                    {m.name}
                  </span>
                  {m.purpose && (
                    <div className="flex flex-wrap gap-1">
                      {m.purpose.slice(0, 3).map((p) => (
                        <Badge key={p} tone="neutral">
                          {p}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))
            ) : (
              <span className="text-xs text-muted">
                {status?.online === false
                  ? "Start the router to see models"
                  : "—"}
              </span>
            )}
          </div>
        </div>
      </Panel>

      <Panel>
        <div className="px-4 py-2.5">
          <div className="text-xs text-muted">Compute</div>
          <div className="mt-1 font-mono text-xs text-text">
            CPU-only · no dedicated GPU
          </div>
        </div>
      </Panel>
    </div>
  );
}
