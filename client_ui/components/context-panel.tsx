"use client";

import { useEffect, useState } from "react";
import { queryRag, listDocuments, RagResponse } from "@/lib/api";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { FileText, File } from "lucide-react";

export function ContextPanel() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<RagResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [files, setFiles] = useState<string[]>([]);
  const [filesError, setFilesError] = useState<string | null>(null);

  useEffect(() => {
    refreshFiles();
  }, []);

  async function refreshFiles() {
    const res = await listDocuments();
    if (res.error) {
      setFilesError(res.detail ?? res.error);
    } else {
      setFiles(res.files ?? []);
      setFilesError(null);
    }
  }

  async function submit() {
    if (!query.trim() || pending) return;
    setPending(true);
    setResult(await queryRag(query.trim()));
    setPending(false);
  }

  return (
    <div className="flex h-full w-80 flex-col">
      <Panel className="flex h-full flex-col">
        <PanelHeader>Knowledge base</PanelHeader>

        <div className="border-b border-border px-3 py-2.5">
          <div className="mb-1.5 flex items-center justify-between font-mono text-[11px] text-muted">
            <span>{files.length} document{files.length === 1 ? "" : "s"}</span>
          </div>
          {filesError ? (
            <div className="text-xs text-brick">{filesError}</div>
          ) : files.length === 0 ? (
            <div className="text-xs text-muted">No documents ingested yet.</div>
          ) : (
            <div className="flex flex-col gap-1">
              {files.map((f) => (
                <div key={f} className="flex items-center gap-1.5 text-xs text-text/80">
                  <File className="h-3 w-3 shrink-0" strokeWidth={1.75} />
                  <span className="truncate">{f}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex gap-1.5 border-b border-border px-3 py-2.5">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Search SOPs, manuals…"
            className="flex-1 rounded border border-border bg-surface2 px-2.5 py-1.5 text-xs text-text placeholder:text-muted focus:outline-none focus-visible:outline-amber"
          />
          <Button variant="ghost" onClick={submit} disabled={pending}>
            Go
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3">
          {result?.error ? (
            <div className="text-xs text-brick">{result.detail}</div>
          ) : !result ? (
            <div className="text-xs text-muted">
              Retrieved passages appear here with their source document
              and page.
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {result.context.map((c, i) => (
                <div key={i} className="border-l border-amber/40 pl-3">
                  <div className="mb-1 flex items-center gap-1.5 font-mono text-[11px] text-muted">
                    <FileText className="h-3 w-3" strokeWidth={1.75} />
                    {c.source} · p.{c.page}
                  </div>
                  <div className="text-xs leading-relaxed text-text/80">
                    {c.text}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}