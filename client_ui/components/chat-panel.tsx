// components/chat-panel.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { uploadDocuments, listDocuments, deleteDocument } from "@/lib/api";
import {
  ArrowUp, Paperclip, X, Library, CheckCircle2, CircleDashed, Loader2,
  ChevronDown, ChevronUp, Trash2, Check, AlertCircle,
} from "lucide-react";

interface PlanStep {
  step_id: number;
  description: string;
  tool_name: string;
  status: string;
}

interface AgentState {
  status: string;
  current_step: number;
  plan: PlanStep[];
  trace: { timestamp: number; source: string; message: string }[];
  final_deliverable: string | null;
}

interface Turn {
  role: "user" | "assistant";
  content: string;
  agentState?: AgentState;
  error?: string;
}

const INIT_PHRASES = [
  "Reading your request…",
  "Triangulating the right approach…",
  "Sketching a plan…",
  "Waking up the local model…",
];

const UPLOAD_PHRASES = [
  "Reading document structure…",
  "Indexing pages…",
  "Triangulating key passages…",
  "Wrapping up ingestion…",
];

function useRotatingPhrase(active: boolean, phrases: string[], intervalMs = 1700) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!active) { setI(0); return; }
    const id = setInterval(() => setI((v) => (v + 1) % phrases.length), intervalMs);
    return () => clearInterval(id);
  }, [active, phrases, intervalMs]);
  return phrases[i];
}

function StepIcon({ status }: { status: string }) {
  if (status === "success") return <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />;
  if (status === "running") return <Loader2 className="h-4 w-4 shrink-0 animate-spin text-amber-500" />;
  if (status === "human_approval") return <CircleDashed className="h-4 w-4 shrink-0 animate-pulse text-amber-500" />;
  if (status === "failed") return <AlertCircle className="h-4 w-4 shrink-0 text-rose-500" />;
  return <CircleDashed className="h-4 w-4 shrink-0 text-zinc-300" />;
}

function TraceLog({ trace, live }: { trace: AgentState["trace"]; live: boolean }) {
  const [open, setOpen] = useState(live);
  useEffect(() => { if (live) setOpen(true); }, [live]);
  if (trace.length === 0) return null;

  return (
    <div className="rounded-xl border border-zinc-200">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3.5 py-2.5 text-[13px] text-zinc-500 hover:text-zinc-800"
      >
        <span>{live ? "Working…" : `${trace.length} step${trace.length === 1 ? "" : "s"} logged`}</span>
        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>
      {open && (
        <div className="max-h-48 overflow-y-auto border-t border-zinc-200 bg-zinc-50 px-3.5 py-2.5">
          <div className="flex flex-col gap-2">
            {trace.map((log, idx) => (
              <div key={idx} className="flex gap-3 text-[12px] leading-relaxed">
                <span className="w-16 shrink-0 text-zinc-400">
                  {new Date(log.timestamp * 1000).toISOString().split("T")[1].slice(0, -5)}
                </span>
                <span className="w-20 shrink-0 text-zinc-500">{log.source}</span>
                <span className="flex-1 whitespace-pre-wrap break-words text-zinc-700">{log.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ChatPanel() {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);

  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  const [status, setStatus] = useState<string | null>(null);
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [kbFiles, setKbFiles] = useState<string[]>([]);
  const [showKb, setShowKb] = useState(false);
  const [kbLoading, setKbLoading] = useState(false);
  const [confirmingRemove, setConfirmingRemove] = useState<string | null>(null);
  const [removingFile, setRemovingFile] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const initPhrase = useRotatingPhrase(pending && !!status && !activeTaskId && !status.startsWith("Uploading"), INIT_PHRASES);
  const uploadPhrase = useRotatingPhrase(!!status?.startsWith("Uploading"), UPLOAD_PHRASES);

  useEffect(() => { refreshKnowledgeBase(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, status]);

  useEffect(() => {
    if (!activeTaskId || activeTaskId === "undefined" || !isPolling) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/agent/${activeTaskId}/trace`);
        if (!res.ok) {
          console.error(`Trace poll got ${res.status}`);
          if (res.status === 404) {
            setIsPolling(false);
            setPending(false);
            setTurns((prev) => {
              const newTurns = [...prev];
              const lastTurn = newTurns[newTurns.length - 1];
              if (lastTurn && lastTurn.role === "assistant") {
                lastTurn.error = "Lost connection to this task on the orchestrator (it may have restarted). Please resend.";
              }
              return newTurns;
            });
            setActiveTaskId(null);
          }
          return;
        }

        const data: AgentState = await res.json();

        setTurns((prev) => {
          const newTurns = [...prev];
          const lastTurn = newTurns[newTurns.length - 1];
          if (lastTurn && lastTurn.role === "assistant") {
            lastTurn.agentState = data;
          }
          return newTurns;
        });

        if (["completed", "failed", "paused"].includes(data.status)) {
          setIsPolling(false);
          if (data.status !== "paused") {
            setPending(false);
            setActiveTaskId(null);
          }
        }
      } catch (err) {
        console.error("Trace poll failed", err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeTaskId, isPolling]);

  async function refreshKnowledgeBase() {
    setKbLoading(true);
    const res = await listDocuments();
    if (!res.error) setKbFiles(res.files ?? []);
    setKbLoading(false);
  }

  async function removeDocument(name: string) {
    setConfirmingRemove(null);
    setRemovingFile(name);
    const res = await deleteDocument(name);
    setRemovingFile(null);
    if (!res.error) {
      setKbFiles((prev) => prev.filter((f) => f !== name));
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length === 0) return;
    setStagedFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name));
      return [...prev, ...files.filter((f) => !existing.has(f.name))];
    });
  }

  function removeStagedFile(name: string) {
    setStagedFiles((prev) => prev.filter((f) => f.name !== name));
  }

  async function handleApprove(taskId: string) {
    setIsPolling(true);
    await fetch(`/api/agent/${taskId}/resume`, { method: "POST" });
  }

  async function submit() {
    const message = input.trim();
    const filesToUpload = stagedFiles;
    if (!message && filesToUpload.length === 0) return;
    if (pending) return;

    setInput("");
    setStagedFiles([]);
    setPending(true);

    if (filesToUpload.length > 0) {
      setStatus(`Uploading ${filesToUpload.length} file(s)…`);
      const uploadRes = await uploadDocuments(filesToUpload);

      if (uploadRes.error) {
        setTurns((t) => [...t, { role: "assistant", content: "", error: uploadRes.detail ?? uploadRes.error }]);
        setStagedFiles(filesToUpload);
        setPending(false);
        setStatus(null);
        return;
      }
      setTurns((t) => [
        ...t,
        { role: "assistant", content: `Added to knowledge base: ${filesToUpload.map((f) => f.name).join(", ")}` }
      ]);
      await refreshKnowledgeBase();
    }

    if (!message) {
      setPending(false);
      setStatus(null);
      return;
    }

    setTurns((t) => [...t, { role: "user", content: message }]);
    setStatus("Initializing agent…");

    try {
      const res = await fetch("/api/agent/task", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: message }),
      });

      if (!res.ok) throw new Error("Agent failed to start");

      const data = await res.json();

      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content: "",
          agentState: { status: "initializing", current_step: 0, plan: [], trace: [], final_deliverable: null }
        }
      ]);

      setActiveTaskId(data.task_id);
      setIsPolling(true);
      setStatus(null);

    } catch (err) {
      setTurns((t) => [...t, { role: "assistant", content: "", error: "Could not reach the orchestrator." }]);
      setPending(false);
      setStatus(null);
    }
  }

  return (
    <div className="flex h-full flex-1 flex-col bg-white">

      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4">
        <div className="font-sans text-[13px] text-zinc-500">Describe a task — the agent will plan and carry it out.</div>
        <button
          onClick={() => setShowKb(!showKb)}
          className="flex items-center gap-1.5 rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[13px] font-medium text-zinc-700 hover:bg-zinc-100"
        >
          <Library className="h-3.5 w-3.5" />
          <span>{kbFiles.length} document{kbFiles.length === 1 ? "" : "s"}</span>
        </button>
      </div>

      {/* Knowledge Base Drawer */}
      {showKb && (
        <div className="border-b border-zinc-200 bg-zinc-50 p-5">
          <div className="mb-3 flex items-center justify-between text-[11px] text-zinc-500">
            <span>Ingested documents</span>
            {kbLoading && <span>Refreshing…</span>}
          </div>
          {kbFiles.length === 0 ? (
            <div className="font-sans text-[13px] text-zinc-500">No documents yet.</div>
          ) : (
            <div className="flex flex-col gap-1">
              {kbFiles.map((f) => (
                <div key={f} className="group flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white">
                  <span className="flex-1 truncate font-sans text-[13px] text-zinc-800">{f}</span>
                  {removingFile === f ? (
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-zinc-400" />
                  ) : confirmingRemove === f ? (
                    <div className="flex shrink-0 items-center gap-1">
                      <button onClick={() => removeDocument(f)} className="rounded-md p-1 text-rose-600 hover:bg-rose-50">
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button onClick={() => setConfirmingRemove(null)} className="rounded-md p-1 text-zinc-500 hover:bg-zinc-100">
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmingRemove(f)}
                      className="shrink-0 rounded-md p-1 text-zinc-400 opacity-0 transition-opacity hover:bg-zinc-100 hover:text-rose-500 group-hover:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Main Chat/Trace Area */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {turns.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="max-w-sm text-center font-sans text-[13px] leading-relaxed text-zinc-500">
              Ask for multi-step analysis, coding help, or document generation — attach files with the paperclip below.
            </div>
          </div>
        ) : (
          <div className="mx-auto flex max-w-2xl flex-col gap-6">
            {turns.map((t, i) => (
              <div key={i} className="flex flex-col gap-2">

                {t.role === "user" ? (
                  <div className="flex justify-end">
                    <div className="max-w-[85%] rounded-2xl bg-indigo-600 px-4 py-2.5 font-sans text-[13px] leading-relaxed text-white">
                      {t.content}
                    </div>
                  </div>
                ) : (
                  <>
                    {t.error ? (
                      <div className="flex items-start gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 font-sans text-[13px] text-rose-700">
                        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                        <span>{t.error}</span>
                      </div>
                    ) : t.content && !t.agentState ? (
                      <div className="max-w-[85%] rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 font-sans text-[13px] leading-relaxed text-zinc-800">
                        {t.content}
                      </div>
                    ) : null}
                  </>
                )}

                {/* Agent State Render Block */}
                {t.agentState && (
                  <div className="flex flex-col gap-3">

                    {/* Execution Plan Tracker */}
                    {t.agentState.plan.length > 0 && (
                      <div className="rounded-2xl border border-zinc-200 p-4">
                        <div className="mb-3 text-[11px] text-zinc-500">Plan</div>
                        <div className="flex flex-col gap-2.5">
                          {t.agentState.plan.map((step, idx) => (
                            <div key={idx} className="flex items-center gap-2.5">
                              <StepIcon status={step.status} />
                              <span className={`font-sans text-[13px] ${
                                step.status === "running" ? "font-medium text-zinc-900" :
                                step.status === "pending" ? "text-zinc-500" :
                                step.status === "failed" ? "text-rose-600" :
                                "text-zinc-700"
                              }`}>
                                {step.description}
                              </span>
                              <span className="ml-auto shrink-0 rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-[11px] text-zinc-600">
                                {step.tool_name}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Collapsible trace log */}
                    <TraceLog
                      trace={t.agentState.trace}
                      live={t.agentState.status === "planning" || t.agentState.status === "executing"}
                    />

                    {/* Human Approval Checkpoint */}
                    {t.agentState.status === "paused" && (
                      <div className="flex items-center justify-between rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
                        <span className="flex items-center gap-2 font-sans text-[13px] font-medium text-amber-800">
                          <span className="relative flex h-2.5 w-2.5">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-500" />
                          </span>
                          Waiting on your approval to continue
                        </span>
                        <button
                          onClick={() => handleApprove(activeTaskId!)}
                          className="rounded-full bg-amber-500 px-4 py-1.5 font-sans text-[13px] font-medium text-white hover:bg-amber-600"
                        >
                          Approve
                        </button>
                      </div>
                    )}

                    {/* Final Output Deliverable */}
                    {t.agentState.final_deliverable && (
                      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                        <div className="mb-1.5 text-[11px] text-emerald-700">Result</div>
                        <div className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-zinc-800">
                          {t.agentState.final_deliverable}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* Waiting State (Before Agent returns first plan) */}
            {pending && status && !activeTaskId && (
              <div className="font-sans text-[13px] text-zinc-500">
                {status.startsWith("Uploading") ? uploadPhrase : initPhrase}
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input Footer */}
      <div className="border-t border-zinc-200 bg-white p-5">
        <div className="mx-auto max-w-2xl">
          {stagedFiles.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {stagedFiles.map((f) => (
                <div key={f.name} className="flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 font-sans text-[13px] text-zinc-700">
                  <span>{f.name}</span>
                  <button onClick={() => removeStagedFile(f.name)} className="text-zinc-400 hover:text-rose-500">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2 rounded-2xl border border-zinc-200 bg-white p-2 focus-within:border-indigo-500">
            <input type="file" ref={fileInputRef} accept=".pdf,.docx,.xlsx" multiple className="hidden" onChange={handleFileSelect} />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={pending}
              className="shrink-0 rounded-xl p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 disabled:opacity-40"
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
              placeholder={pending ? "Agent is running…" : "Ask the agent to do something, or attach a document…"}
              disabled={pending}
              className="flex-1 bg-transparent px-1 font-sans text-[13px] text-zinc-900 outline-none placeholder:text-zinc-500 disabled:opacity-50"
            />
            <button
              onClick={submit}
              disabled={pending || (!input.trim() && stagedFiles.length === 0)}
              className="shrink-0 rounded-xl bg-indigo-600 p-2 text-white transition-colors hover:bg-indigo-700 disabled:bg-zinc-100 disabled:text-zinc-300"
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

    </div>
  );
}