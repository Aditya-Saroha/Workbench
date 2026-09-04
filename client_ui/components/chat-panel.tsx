"use client";

import { useEffect, useRef, useState } from "react";
import { sendChat, queryRag, uploadDocuments, listDocuments, ChatResponse, RagChunk } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { ArrowUp, Paperclip, X, Library } from "lucide-react";

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
  const [status, setStatus] = useState<string | null>(null);
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [kbFiles, setKbFiles] = useState<string[]>([]);
  const [showKb, setShowKb] = useState(false);
  const [kbLoading, setKbLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    refreshKnowledgeBase();
  }, []);

  async function refreshKnowledgeBase() {
    setKbLoading(true);
    const res = await listDocuments();
    if (!res.error) setKbFiles(res.files ?? []);
    setKbLoading(false);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // allow re-selecting the same file later
    if (files.length === 0) return;

    setStagedFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name));
      return [...prev, ...files.filter((f) => !existing.has(f.name))];
    });
  }

  function removeStagedFile(name: string) {
    setStagedFiles((prev) => prev.filter((f) => f.name !== name));
  }

  async function submit() {
    const message = input.trim();
    const filesToUpload = stagedFiles;
    if (!message && filesToUpload.length === 0) return;
    if (pending) return;

    setInput("");
    setStagedFiles([]);
    setPending(true);

    // 1. Upload any staged files first, as part of this send.
    if (filesToUpload.length > 0) {
      setStatus(`Uploading ${filesToUpload.length} file${filesToUpload.length > 1 ? "s" : ""}…`);
      const uploadRes = await uploadDocuments(filesToUpload);

      if (uploadRes.error) {
        setTurns((t) => [
          ...t,
          { role: "assistant", content: "", error: uploadRes.detail ?? uploadRes.error },
        ]);
        // Re-stage the files so the user doesn't lose their selection on failure.
        setStagedFiles(filesToUpload);
        setPending(false);
        setStatus(null);
        return;
      }

      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content: `Added to the knowledge base: ${filesToUpload.map((f) => f.name).join(", ")}${
            uploadRes.chunks ? ` (${uploadRes.chunks} chunks indexed)` : ""
          }.`,
        },
      ]);
      await refreshKnowledgeBase();
    }

    // 2. Then run the query, if there is one.
    if (!message) {
      setPending(false);
      setStatus(null);
      return;
    }

    setTurns((t) => [...t, { role: "user", content: message }]);
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

  return (
    <div className="flex h-full flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-border px-6 py-3">
        <div className="text-sm text-muted">Describe a task — the router picks the model.</div>
        <Button variant="ghost" onClick={() => setShowKb((v) => !v)} title="View knowledge base">
          <Library className="h-4 w-4" strokeWidth={2} />
          <span className="ml-1.5 font-mono text-xs">{kbFiles.length}</span>
        </Button>
      </div>

      {showKb && (
        <Panel className="mx-6 mt-3">
          <div className="flex items-center justify-between px-3 py-2 text-xs text-muted">
            <span>Knowledge base</span>
            {kbLoading && <span>Refreshing…</span>}
          </div>
          <div className="flex flex-wrap gap-1.5 border-t border-border px-3 py-2">
            {kbFiles.length === 0 ? (
              <span className="text-xs text-muted">No documents ingested yet.</span>
            ) : (
              kbFiles.map((f) => (
                <Badge key={f} tone="amber">
                  {f}
                </Badge>
              ))
            )}
          </div>
        </Panel>
      )}

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {turns.length === 0 ? (
          <div className="flex h-full items-center justify-center text-center">
            <div className="mt-1 font-mono text-xs text-muted">
              approval notes · code review · summarization
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
                          <div className="px-3 py-2 text-xs text-muted">Grounded in:</div>
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
            {(pending) && <div className="text-xs text-muted">{status}</div>}
          </div>
        )}
      </div>

      <div className="border-t border-border px-6 py-4">
        {stagedFiles.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {stagedFiles.map((f) => (
              <span
                key={f.name}
                className="flex items-center gap-1 rounded border border-border bg-surface2 px-2 py-1 text-xs text-text"
              >
                {f.name}
                <button
                  type="button"
                  onClick={() => removeStagedFile(f.name)}
                  className="text-muted hover:text-brick"
                  title="Remove"
                >
                  <X className="h-3 w-3" strokeWidth={2} />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.xlsx"
            multiple
            className="hidden"
            onChange={handleFileSelect}
          />
          <Button
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            disabled={pending}
            title="Attach files to send with your next message"
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
          <Button onClick={submit} disabled={pending || (!input.trim() && stagedFiles.length === 0)}>
            <ArrowUp className="h-4 w-4" strokeWidth={2} />
          </Button>
        </div>
      </div>
    </div>
  );
}