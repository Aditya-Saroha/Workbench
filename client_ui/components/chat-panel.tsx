"use client";

import { useEffect, useRef, useState } from "react";
import { uploadDocuments, listDocuments, RagChunk } from "@/lib/api"; // Removed sendChat, queryRag
import { ArrowUp, Paperclip, X, Library, CheckCircle2, CircleDashed, Loader2 } from "lucide-react";

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

const Prompt = () => (
  <span className="shrink-0 font-bold text-neutral-400">
    <span className="text-sky-400">user</span>
    <span className="text-emerald-500">@</span>
    <span className="text-sky-300">mrpl</span>
    <span className="text-neutral-400">:$</span>{" "}
  </span>
);

const SystemPrompt = () => (
  <span className="shrink-0 font-bold text-neutral-400">
    <span className="text-purple-400">system</span>
    <span className="text-emerald-500">@</span>
    <span className="text-amber-400">orchestrator</span>
    <span className="text-neutral-400">:$</span>{" "}
  </span>
);

export function ChatPanel() {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);

  // Agent Polling State
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  const [status, setStatus] = useState<string | null>(null);
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [kbFiles, setKbFiles] = useState<string[]>([]);
  const [showKb, setShowKb] = useState(false);
  const [kbLoading, setKbLoading] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { refreshKnowledgeBase(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, status]);

  // Polling Effect for Agent Task
  useEffect(() => {
    // ADDED "undefined" CHECK HERE
    if (!activeTaskId || activeTaskId === "undefined" || !isPolling) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/agent/${activeTaskId}/trace`);
        if (!res.ok) return;

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

    // 1. Handle File Uploads (unchanged)
    if (filesToUpload.length > 0) {
      setStatus(`Uploading ${filesToUpload.length} file(s)...`);
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

    // 2. Trigger Agent Orchestrator
    setTurns((t) => [...t, { role: "user", content: message }]);
    setStatus("Initializing agent sandbox...");

    try {
      const res = await fetch("/api/agent/task", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: message }),
      });

      if (!res.ok) throw new Error("Agent failed to start");

      const data = await res.json();

      // Append an empty assistant turn that will be populated by the polling effect
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
      setTurns((t) => [...t, { role: "assistant", content: "", error: "Could not reach Orchestrator." }]);
      setPending(false);
      setStatus(null);
    }
  }

  return (
    <div className="flex h-full flex-1 flex-col bg-black">

      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-800 px-6 py-4">
        <div className="font-bold text-neutral-400">Provide a complex task — the agent will plan and execute.</div>
        <button onClick={() => setShowKb(!showKb)} className="flex items-center gap-2 font-bold text-cyan-400 hover:text-cyan-300">
          <Library className="h-4 w-4" />
          <span>[{kbFiles.length}]</span>
        </button>
      </div>

      {/* Knowledge Base Drawer */}
      {showKb && (
        <div className="border-b border-neutral-800 bg-neutral-900 p-4 px-6">
          <div className="mb-3 flex justify-between font-bold text-neutral-400">
            <span># INGESTED_DOCUMENTS</span>
            {kbLoading && <span className="text-amber-400">Refreshing...</span>}
          </div>
          <div className="flex flex-wrap gap-2">
            {kbFiles.length === 0 ? <span className="text-neutral-500">No documents.</span> :
              kbFiles.map((f) => <span key={f} className="rounded bg-amber-400/20 px-2 py-1 font-bold text-amber-300">{f}</span>)
            }
          </div>
        </div>
      )}

      {/* Main Chat/Trace Area */}
      <div className="flex-1 overflow-y-auto p-6">
        {turns.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center leading-loose text-neutral-400">
              <span className="text-emerald-400">&gt; waiting for input...</span> <br />
              &gt; support: multi-step analysis, coding, document generation
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-8">
            {turns.map((t, i) => (
              <div key={i} className="flex flex-col gap-2">

                {/* Standard Message / Errors */}
                <div className="flex items-start gap-3">
                  {t.role === "user" ? <Prompt /> : <SystemPrompt />}

                  {t.error ? (
                    <div className="font-bold text-red-500">{t.error}</div>
                  ) : t.content && !t.agentState ? (
                    <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-neutral-100">
                      {t.content}
                    </div>
                  ) : null}
                </div>

                {/* Agent State Render Block */}
                {t.agentState && (
                  <div className="ml-[108px] mr-12 mt-2 flex flex-col gap-4 text-[12px]">

                    {/* Execution Plan Tracker */}
                    {t.agentState.plan.length > 0 && (
                      <div className="border border-neutral-800 bg-neutral-900/50 p-4">
                        <div className="mb-3 font-bold text-neutral-500 uppercase tracking-wider text-[10px]">Execution Plan</div>
                        <div className="flex flex-col gap-2">
                          {t.agentState.plan.map((step, idx) => (
                            <div key={idx} className="flex items-center gap-3">
                              {step.status === "success" ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> :
                                step.status === "running" ? <Loader2 className="h-4 w-4 animate-spin text-amber-400" /> :
                                  step.status === "human_approval" ? <CircleDashed className="h-4 w-4 text-amber-500 animate-pulse" /> :
                                    step.status === "failed" ? <X className="h-4 w-4 text-red-500" /> :
                                      <CircleDashed className="h-4 w-4 text-neutral-700" />}

                              <span className={`
                                ${step.status === "success" ? "text-neutral-400" : ""}
                                ${step.status === "running" ? "text-amber-400 font-bold" : ""}
                                ${step.status === "pending" ? "text-neutral-600" : ""}
                                ${step.status === "failed" ? "text-red-400" : ""}
                              `}>
                                {step.description}
                                <span className="ml-2 text-[10px] text-sky-500/50 font-mono">[{step.tool_name}]</span>
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Scrolling Trace Logs */}
                    {t.agentState.trace.length > 0 && (
                      <div className="max-h-48 overflow-y-auto border border-neutral-800 bg-black p-3 font-mono text-[11px] leading-relaxed">
                        {t.agentState.trace.map((log, idx) => (
                          <div key={idx} className="flex gap-4 hover:bg-neutral-900/50">
                            <span className="text-neutral-600 shrink-0">
                              {new Date(log.timestamp * 1000).toISOString().split('T')[1].slice(0, -1)}
                            </span>
                            <span className="text-purple-400/80 shrink-0 w-24">[{log.source}]</span>
                            <span className="text-neutral-300 whitespace-pre-wrap break-words">{log.message}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Human Approval Checkpoint */}
                    {t.agentState.status === "paused" && (
                      <div className="flex items-center justify-between border border-amber-500/30 bg-amber-500/10 p-4">
                        <span className="font-bold text-amber-400 flex items-center gap-2">
                          <span className="relative flex h-3 w-3">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500"></span>
                          </span>
                          Agent requires authorization to proceed.
                        </span>
                        <button
                          onClick={() => handleApprove(activeTaskId!)}
                          className="bg-amber-500 text-black px-4 py-1.5 font-bold hover:bg-amber-400 transition-colors"
                        >
                          APPROVE
                        </button>
                      </div>
                    )}

                    {/* Final Output Deliverable */}
                    {t.agentState.final_deliverable && (
                      <div className="mt-2 border-l-2 border-emerald-500 bg-emerald-500/5 p-4">
                        <div className="mb-2 font-bold text-emerald-500 uppercase text-[10px] tracking-wider">Final Output</div>
                        <div className="whitespace-pre-wrap text-[13px] text-neutral-100">
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
              <div className="flex items-start gap-3">
                <SystemPrompt />
                <span className="animate-pulse font-bold text-amber-400">{status}</span>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input Footer */}
      <div className="border-t border-neutral-800 bg-black p-6">
        {stagedFiles.length > 0 && (
          <div className="mb-4 flex flex-wrap gap-2">
            {stagedFiles.map((f) => (
              <div key={f.name} className="flex items-center gap-2 rounded bg-neutral-800 px-3 py-1.5 font-bold text-cyan-300">
                <span>{f.name}</span>
                <button onClick={() => removeStagedFile(f.name)} className="text-neutral-400 hover:text-red-400">
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex items-center gap-3">
          <input type="file" ref={fileInputRef} accept=".pdf,.docx,.xlsx" multiple className="hidden" onChange={handleFileSelect} />
          <button onClick={() => fileInputRef.current?.click()} disabled={pending} className="text-neutral-400 transition-colors hover:text-cyan-400">
            <Paperclip className="h-5 w-5" />
          </button>
          <div className="flex flex-1 items-center gap-3 rounded bg-neutral-900 px-4 py-3">
            <Prompt />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
              placeholder={pending ? "Agent is running..." : "E.g., Read the uploaded scanned report and draft an approval note..."}
              disabled={pending}
              className="flex-1 bg-transparent text-[13px] text-white outline-none placeholder:text-neutral-600 disabled:opacity-50"
            />
          </div>
          <button
            onClick={submit}
            disabled={pending || (!input.trim() && stagedFiles.length === 0)}
            className="rounded bg-neutral-900 p-3 text-neutral-400 transition-colors hover:text-emerald-400 disabled:opacity-50"
          >
            <ArrowUp className="h-5 w-5" />
          </button>
        </div>
      </div>

    </div>
  );
}