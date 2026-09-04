"use client";

import { useState } from "react";
import { sendChat, ChatResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { ArrowUp } from "lucide-react";

interface Turn {
  role: "user" | "assistant";
  content: string;
  router?: ChatResponse["router"];
  error?: string;
}

export function ChatPanel() {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);

  async function submit() {
    const message = input.trim();
    if (!message || pending) return;

    setInput("");
    setTurns((t) => [...t, { role: "user", content: message }]);
    setPending(true);

    const res = await sendChat(message);

    setTurns((t) => [
      ...t,
      res.error
        ? { role: "assistant", content: "", error: res.detail ?? res.error }
        : {
            role: "assistant",
            content: res.choices?.[0]?.message?.content ?? "",
            router: res.router,
          },
    ]);
    setPending(false);
  }

  return (
    <div className="flex h-full flex-1 flex-col">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {turns.length === 0 ? (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <div className="text-sm text-muted">
                Describe a task — the router picks the model.
              </div>
              <div className="mt-1 font-mono text-xs text-muted">
                approval notes · code review · summarization
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {turns.map((t, i) =>
              t.role === "user" ? (
                <div key={i} className="max-w-2xl self-end">
                  <div className="rounded border border-border bg-surface2 px-4 py-2.5 text-sm text-text">
                    {t.content}
                  </div>
                </div>
              ) : (
                <div key={i} className="max-w-2xl self-start">
                  {t.error ? (
                    <div className="rounded border border-brick/40 bg-surface px-4 py-2.5 text-sm text-brick">
                      {t.error}
                    </div>
                  ) : (
                    <>
                      <div className="whitespace-pre-wrap px-4 py-2.5 text-sm text-text">
                        {t.content}
                      </div>
                      {t.router && (
                        <Panel className="mt-1.5">
                          <div className="flex flex-wrap items-center gap-2 px-3 py-2">
                            <Badge tone="amber">{t.router.taskType}</Badge>
                            <span className="font-mono text-xs text-muted">
                              {t.router.selectedModel}
                            </span>
                            <span className="font-mono text-xs text-muted">
                              {(t.router.executionTimeMs / 1000).toFixed(1)}s
                            </span>
                          </div>
                          <div className="border-t border-border px-3 py-2 font-mono text-[11px] text-muted">
                            {t.router.decisionReason}
                          </div>
                        </Panel>
                      )}
                    </>
                  )}
                </div>
              )
            )}
            {pending && (
              <div className="text-xs text-muted">Routing and running…</div>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-border px-6 py-4">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Draft an approval note from the inspection report…"
            rows={1}
            className="flex-1 resize-none rounded border border-border bg-surface2 px-3 py-2.5 text-sm text-text placeholder:text-muted focus:outline-none focus-visible:outline-amber"
          />
          <Button onClick={submit} disabled={pending || !input.trim()}>
            <ArrowUp className="h-4 w-4" strokeWidth={2} />
          </Button>
        </div>
      </div>
    </div>
  );
}
