"use client";

import { useEffect, useState } from "react";
import { queryRag, listDocuments, RagResponse } from "@/lib/api";
import { FileText, File } from "lucide-react";

export function ContextPanel() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<RagResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [files, setFiles] = useState<string[]>([]);
  const [filesError, setFilesError] = useState<string | null>(null);

  useEffect(() => { refreshFiles(); }, []);

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

  return (
    <div className="flex h-full w-80 flex-col bg-black">
      
      <div className="border-b border-neutral-800 p-4">
        <div className="mb-4 flex items-center justify-between font-bold text-neutral-400">
          <span># KNOWLEDGE_BASE</span>
          <span className="text-emerald-400">{files.length} doc{files.length === 1 ? "" : "s"}</span>
        </div>
        {filesError ? (
          <div className="font-bold text-red-500">{filesError}</div>
        ) : files.length === 0 ? (
          <div className="text-neutral-500">No documents ingested yet.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {files.map((f) => (
              <div key={f} className="flex items-center gap-2 font-bold text-cyan-300">
                <File className="h-4 w-4 shrink-0 text-cyan-500" />
                <span className="truncate">{f}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border-b border-neutral-800 p-4">
        <div className="flex items-center gap-2 rounded bg-neutral-900 px-3 py-2.5 focus-within:ring-1 focus-within:ring-neutral-600">
          <span className="shrink-0 font-bold text-emerald-400">grep</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="search manuals..."
            className="flex-1 bg-transparent text-white outline-none placeholder:text-neutral-500"
            disabled={pending}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {result?.error ? (
          <div className="font-bold text-red-500">{result.detail}</div>
        ) : !result ? (
          <div className="leading-relaxed text-neutral-500">
            &gt; Retrieved passages will appear here...
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {result.context.map((c, i) => (
              <div key={i} className="border-l-2 border-amber-500 pl-4">
                <div className="mb-2 flex items-center gap-2 font-bold text-amber-400">
                  <FileText className="h-4 w-4" />
                  <span>{c.source} : {c.page}</span>
                </div>
                <div className="text-[13px] leading-relaxed text-neutral-100">
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