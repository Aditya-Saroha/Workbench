// components/status-rail.tsx
"use client";

import { useEffect, useState } from "react";
import { getStatus, listSessions, createSession, deleteSession, SessionSummary, StatusResponse } from "@/lib/api";
import { getSessionId, setSessionId, useSessionId } from "@/lib/session";
import { ShieldCheck, Circle, Plus, Trash2 } from "lucide-react";

/**
 * Design tokens — shared across status-rail / chat-panel / context-panel:
 *   canvas    zinc-50   (app background)
 *   surface   white     (side rails, drawers)
 *   card      white + border-zinc-200
 *   text      zinc-900 primary · zinc-600 secondary · zinc-500 muted floor
 *   accent    indigo-600 (user bubble, focus rings — used sparingly)
 *   state     emerald-600 success · amber-600 attention · rose-600 danger
 *   type      font-mono = status/data layer · font-sans = human-read content
 *   radius    full = dots/pills · xl = controls · 2xl = cards/panels
 */

export function StatusRail() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [chats, setChats] = useState<SessionSummary[]>([]);
  const [creatingChat, setCreatingChat] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);
  const activeSession = useSessionId();

  useEffect(() => {
    const poll = () => getStatus().then(setStatus).catch(() => {});
    poll();
    const id = setInterval(poll, 8000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const refresh = () => listSessions().then((result) => setChats(result.sessions ?? [])).catch(() => {});
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  async function newChat() {
    if (creatingChat) return;
    setCreatingChat(true);
    // Registers the chat on the orchestrator right away (title "New chat")
    // instead of only in local React/localStorage state, so it's still
    // there after a refresh even before the first message is sent — the
    // first message then autonames it (see main.py's create_task).
    const created = await createSession();
    setCreatingChat(false);
    if (!created) return;
    setSessionId(created.id);
    setChats((current) => [created, ...current.filter((c) => c.id !== created.id)]);
  }

  async function removeChat(id: string) {
    setConfirmingDelete(null);
    const ok = await deleteSession(id);
    if (!ok) return;
    setChats((current) => current.filter((c) => c.id !== id));
    if (id === activeSession) {
      await newChat();
    }
  }

  const models = (status?.models as any)?.models as
    | { name: string; purpose?: string[] }[]
    | undefined;

  return (
    <div className="flex h-full w-64 flex-col gap-6 overflow-y-auto border-r border-zinc-200 bg-white p-5">

      {/* Privacy assurance */}
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
        <div className="flex items-start gap-2.5">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
          <div className="font-sans">
            <div className="text-sm font-medium text-emerald-900">Runs entirely on this machine</div>
            <div className="mt-0.5 text-[13px] leading-snug text-emerald-700">Nothing leaves your device</div>
          </div>
        </div>
      </div>

      <div>
        <div className="mb-2.5 flex items-center justify-between text-[11px] text-zinc-500">
          <span>Chats</span>
          <button onClick={newChat} disabled={creatingChat} className="rounded-md p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-40" title="New chat" aria-label="New chat">
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="flex max-h-56 flex-col gap-1 overflow-y-auto">
          {(chats.length ? chats : [{ id: getSessionId(), title: "New chat", updated_at: Date.now() / 1000 }]).map((chat) => (
            <div
              key={chat.id}
              className={`group flex items-center gap-1 rounded-lg border px-2.5 py-2 text-left font-sans text-[12px] ${chat.id === activeSession ? "border-indigo-200 bg-indigo-50 text-indigo-800" : "border-zinc-200 bg-zinc-50 text-zinc-600 hover:bg-zinc-100"}`}
            >
              <button onClick={() => setSessionId(chat.id)} className="flex-1 truncate text-left" title={chat.title}>
                {chat.title || "New chat"}
              </button>
              {confirmingDelete === chat.id ? (
                <div className="flex shrink-0 items-center gap-1">
                  <button onClick={() => removeChat(chat.id)} className="rounded p-0.5 text-rose-600 hover:bg-rose-50" title="Confirm delete">
                    <Trash2 className="h-3 w-3" />
                  </button>
                  <button onClick={() => setConfirmingDelete(null)} className="rounded px-1 text-zinc-400 hover:bg-zinc-100">
                    ✕
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmingDelete(chat.id)}
                  className="shrink-0 rounded p-0.5 text-zinc-400 opacity-0 transition-opacity hover:bg-zinc-100 hover:text-rose-500 group-hover:opacity-100"
                  title="Delete chat"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Router status */}
      <div>
        <div className="mb-2.5 text-[11px] text-zinc-500">Router</div>
        <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-3 py-2.5">
          <Circle
            className={`h-2 w-2 shrink-0 ${
              status?.online ? "fill-emerald-500 text-emerald-500" : "fill-rose-500 text-rose-500"
            }`}
          />
          <span className="font-sans text-sm text-zinc-800">
            {status === null ? "Checking…" : status.online ? "Online · 127.0.0.1:11435" : "Unreachable"}
          </span>
        </div>
      </div>

      {/* Configured models */}
      <div>
        <div className="mb-2.5 text-[11px] text-zinc-500">Models</div>
        <div className="flex flex-col gap-2">
          {models?.length ? (
            models.map((m) => (
              <div key={m.name} className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2.5">
                <div className="text-[13px] text-zinc-800">{m.name}</div>
                {m.purpose && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {m.purpose.slice(0, 3).map((p) => (
                      <span
                        key={p}
                        className="rounded-full border border-zinc-200 bg-white px-2 py-0.5 text-[11px] text-zinc-600"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2.5 font-sans text-sm text-zinc-500">
              {status?.online === false ? "Start the router to see models" : "—"}
            </div>
          )}
        </div>
      </div>

      {/* Compute */}
      <div className="mt-auto border-t border-zinc-200 pt-4">
        <div className="text-[11px] text-zinc-500">Compute</div>
        <div className="mt-1.5 font-sans text-sm text-zinc-600">CPU only · no dedicated GPU</div>
      </div>

    </div>
  );
}