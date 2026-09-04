import { StatusRail } from "@/components/status-rail";
import { ChatPanel } from "@/components/chat-panel";
import { ContextPanel } from "@/components/context-panel";

export default function Home() {
  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-border px-6 py-3.5">
        <div>
          <h1 className="text-sm font-medium text-text">MRPL AI Workbench</h1>
          <p className="font-mono text-[11px] text-muted">
            sovereign · on-premise · agentic
          </p>
        </div>
      </header>

      <div className="flex flex-1 gap-3 overflow-hidden p-3">
        <StatusRail />
        <div className="flex-1 border border-border bg-surface">
          <ChatPanel />
        </div>
        <ContextPanel />
      </div>
    </main>
  );
}
