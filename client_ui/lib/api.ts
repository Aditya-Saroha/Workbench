export interface RouterDecision {
  mode: string;
  taskType: string;
  selectedModel: string;
  fallbackModels: string[];
  queueTimeMs: number;
  executionTimeMs: number;
  decisionReason: string;
}

export interface ChatResponse {
  choices: { message: { content: string } }[];
  router: RouterDecision;
  error?: string;
  detail?: string;
}

export interface RagChunk {
  text: string;
  source: string;
  page: number;
  score: number;
}

export interface RagResponse {
  query: string;
  context: RagChunk[];
  sources: { source: string; page: number }[];
  error?: string;
  detail?: string;
}

export interface StatusResponse {
  online: boolean;
  models: unknown;
  gpu: unknown;
}

export async function getStatus(): Promise<StatusResponse> {
  const res = await fetch("/api/status", { cache: "no-store" });
  return res.json();
}

export async function sendChat(message: string): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      model: "auto",
      messages: [{ role: "user", content: message }],
    }),
  });
  return res.json();
}

export async function queryRag(
  query: string,
  topK = 5
): Promise<RagResponse> {
  const res = await fetch("/api/rag", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
  return res.json();
}
