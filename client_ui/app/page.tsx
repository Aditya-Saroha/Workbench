import { StatusRail } from "@/components/status-rail";
import { ChatPanel } from "@/components/chat-panel";
import { ContextPanel } from "@/components/context-panel";

export default function Home() {
  return (
    <main className="flex h-screen w-screen overflow-hidden bg-black font-mono text-xs text-neutral-100">
      <StatusRail />
      
      <div className="flex-1 border-x border-neutral-800 bg-black">
        <ChatPanel />
      </div>
      
      <ContextPanel />
    </main>
  );
}