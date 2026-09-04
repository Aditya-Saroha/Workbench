"use client";

import { useRef, useState } from "react";
import { sendChat, queryRag, uploadDocuments, ChatResponse, RagChunk } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { ArrowUp, Paperclip } from "lucide-react";

interface Turn {
  role: "user" | "assistant";
  content: string;
  router?: ChatResponse["router"];
  sources?: RagChunk[];
  error?: string;
}

export function ChatPanel() {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function submit() {
    const message = input.trim();
    if (!message || pending) return;

    setInput("");
    setTurns((t) => [...t, { role: "user", content: message }]);
    setPending(true);
    setStatus("Searching knowledge base…");

    const rag = await queryRag(message);
    const chunks = rag.context ?? [];

    setStatus("Routing and running…");
    const res = await sendChat(message, chunks);

    setTurns((t) => [
      ...t,
      res.error
        ? { role: "assistant", content: "", error: res.detail ?? res.error }
        : {
            role: "assistant",
            content: res.choices?.[0]?.message?.content ?? "",
            router: res.router,
            sources: chunks,
          },
    ]);
    setPending(false);
    setStatus(null);
  }

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // allow re-selecting the same file later
    if (files.length === 0) return;

    setUploading(true);
    setStatus(`Uploading ${files.length} file${files.length > 1 ? "s" : ""}…`);

    const res = await uploadDocuments(files);

    setUploading(false);
    setStatus(null);
    setTurns((t) => [
      ...t,
      res.error
        ? { role: "assistant", content: "", error: res.detail ?? res.error }
        : {
            role: "assistant",
            content: `Added to the knowledge base: ${files.map((f) => f.name).join(", ")}${
              res.chunks ? ` (${res.chunks} chunks indexed)` : ""
            }.`,
          },
    ]);
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
                      {t.sources && t.sources.length > 0 && (
                        <Panel className="mt-1.5">
                          <div className="px-3 py-2 text-xs text-muted">
                            Grounded in:
                          </div>
                          <div className="flex flex-wrap gap-1.5 border-t border-border px-3 py-2">
                            {t.sources.map((s, idx) => (
                              <Badge key={idx} tone="amber">
                                {s.source}
                              </Badge>
                            ))}
                          </div>
                        </Panel>
                      )}
                    </>
                  )}
                </div>
              )
            )}
            {(pending || uploading) && (
              <div className="text-xs text-muted">{status}</div>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-border px-6 py-4">
        <div className="flex items-end gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            multiple
            className="hidden"
            onChange={handleFileSelect}
          />
          <Button
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || pending}
            title="Add files to the knowledge base"
          >
            <Paperclip className="h-4 w-4" strokeWidth={2} />
          </Button>
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