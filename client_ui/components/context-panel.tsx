// components/context-panel.tsx
"use client";

import { useEffect, useState } from "react";
import { queryRag, listDocuments, deleteDocument, RagResponse } from "@/lib/api";
import { useSessionId } from "@/lib/session";
import { FileText, File, Trash2, Check, X, Loader2 } from "lucide-react";

const SEARCH_PHRASES = [
  "Triangulating relevant passages…",
  "Scanning the knowledge base…",
  "Cross-referencing your documents…",
  "Narrowing down the best matches…",
];

function useRotatingPhrase(active: boolean, phrases: string[], intervalMs = 1600) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!active) { setI(0); return; }
    const id = setInterval(() => setI((v) => (v + 1) % phrases.length), intervalMs);
    return () => clearInterval(id);
  }, [active, phrases, intervalMs]);
  return phrases[i];
}

export function ContextPanel() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<RagResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [files, setFiles] = useState<string[]>([]);
  const [filesError, setFilesError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const sessionId = useSessionId();

  const loadingPhrase = useRotatingPhrase(pending, SEARCH_PHRASES);

  useEffect(() => {
    refreshFiles();

    const refreshOnFocus = () => refreshFiles();
    const interval = window.setInterval(refreshFiles, 5000);
    window.addEventListener("focus", refreshOnFocus);

    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", refreshOnFocus);
    };
  }, []);

  useEffect(() => {
    setResult(null);
    setFiles([]);
    refreshFiles();
  }, [sessionId]);

  async function refreshFiles() {
    const res = await listDocuments();
    if (res.error) setFilesError(res.detail ?? res.error);
    else { setFiles(res.files ?? []); setFilesError(null); }
  }

  async function submit() {
    if (!query.trim() || pending) return;
    setPending(true);
    setResult(await queryRag(query.trim()));
    setPending(false);
  }

  async function confirmRemove(name: string) {
    setConfirming(null);
    setRemoving(name);
    const res = await deleteDocument(name);
    setRemoving(null);
    if (!res.error) {
      setFiles((prev) => prev.filter((f) => f !== name));
    } else if (res.status === 404) {
      // The row can outlive the file after a restart or external cleanup.
      // Remove it locally and reconcile with the RAG service's list.
      setFiles((prev) => prev.filter((f) => f !== name));
      await refreshFiles();
    } else {
      setFilesError(res.detail ?? res.error);
    }
  }

  return (
    <div className="flex h-full w-80 flex-col border-l border-zinc-200 bg-white">

      {/* Knowledge base list */}
      <div className="border-b border-zinc-200 p-5">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-[11px] text-zinc-500">Knowledge base</span>
          <span className="rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-[11px] text-zinc-600">
            {files.length} doc{files.length === 1 ? "" : "s"}
          </span>
        </div>

        {filesError ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 font-sans text-[13px] text-rose-700">{filesError}</div>
        ) : files.length === 0 ? (
          <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-4 text-center font-sans text-[13px] text-zinc-500">
            No documents yet — attach one from the chat.
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {files.map((f) => (
              <div key={f} className="group flex items-center gap-2 rounded-xl px-2.5 py-2 hover:bg-zinc-50">
                <File className="h-4 w-4 shrink-0 text-zinc-500" />
                <span className="flex-1 truncate font-sans text-[13px] text-zinc-800">{f}</span>

                {removing === f ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-zinc-400" />
                ) : confirming === f ? (
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      onClick={() => confirmRemove(f)}
                      className="rounded-md p-1 text-rose-600 hover:bg-rose-50"
                      title="Confirm remove"
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => setConfirming(null)}
                      className="rounded-md p-1 text-zinc-500 hover:bg-zinc-100"
                      title="Cancel"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirming(f)}
                    className="shrink-0 rounded-md p-1 text-zinc-400 opacity-0 transition-opacity hover:bg-zinc-100 hover:text-rose-500 group-hover:opacity-100"
                    title="Remove from knowledge base"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Search */}
      <div className="border-b border-zinc-200 p-5">
        <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-3.5 py-2.5 focus-within:border-indigo-500">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Search your documents…"
            className="flex-1 bg-transparent font-sans text-[13px] text-zinc-900 outline-none placeholder:text-zinc-500"
            disabled={pending}
          />
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-5">
        {pending ? (
          <div className="font-sans text-[13px] text-zinc-500">{loadingPhrase}</div>
        ) : result?.error ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 font-sans text-[13px] text-rose-700">{result.detail}</div>
        ) : !result ? (
          <div className="font-sans text-[13px] leading-relaxed text-zinc-500">
            Matching passages will appear here.
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {result.context.map((c, i) => (
              <div key={i} className="rounded-xl border border-zinc-200 bg-zinc-50 p-3.5">
                <div className="mb-1.5 flex items-center gap-1.5 text-[11px] text-zinc-500">
                  <FileText className="h-3.5 w-3.5" />
                  <span>{c.source} · p.{c.page}</span>
                </div>
                <div className="font-sans text-[13px] leading-relaxed text-zinc-700">
                  {c.text}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
}