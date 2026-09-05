// app/page.tsx
import { StatusRail } from "@/components/status-rail";
import { ChatPanel } from "@/components/chat-panel";
import { ContextPanel } from "@/components/context-panel";

export default function Home() {
  return (
    <main className="flex h-screen w-screen overflow-hidden bg-zinc-50 font-mono text-xs text-zinc-900">
      <StatusRail />

      <div className="flex-1 border-x border-zinc-200 bg-white">
        <ChatPanel />
      </div>

      <ContextPanel />
    </main>
  );
}