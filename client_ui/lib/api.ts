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

export async function queryRag(
  query: string,
  topK = 5
): Promise<RagResponse> {
  try {
    const res = await fetch("/api/rag", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, top_k: topK }),
    });
    return await res.json();
  } catch (err) {
    return {
      query,
      context: [],
      sources: [],
      error: "network_error",
      detail: String(err),
    };
  }
}

export async function sendChat(
  message: string,
  context?: RagChunk[]
): Promise<ChatResponse> {
  const contextBlock = context?.length
    ? "Use the following excerpts from company manuals, SOPs, and past " +
      "correspondence to ground your answer. Cite the source and page " +
      "when you rely on a fact from it.\n\n" +
      context
        .map((c, i) => `[${i + 1}] ${c.source} (p.${c.page})\n${c.text}`)
        .join("\n\n") +
      "\n\n---\n\n"
    : "";

  const augmented = contextBlock ? `${contextBlock}Question: ${message}` : message;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model: "auto",
        messages: [{ role: "user", content: augmented }],
      }),
    });
    return await res.json();
  } catch (err) {
    return {
      choices: [],
      router: {} as RouterDecision,
      error: "network_error",
      detail: String(err),
    };
  }
}

export interface IngestResponse {
  ingested?: string[];
  chunks?: number;
  error?: string;
  detail?: string;
}

export async function uploadDocuments(files: File[]): Promise<IngestResponse> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));

  try {
    const res = await fetch("/api/rag/ingest", {
      method: "POST",
      body: formData,
    });
    return await res.json();
  } catch (err) {
    return { error: "network_error", detail: String(err) };
  }
}

export async function listDocuments(): Promise<{ files?: string[]; error?: string; detail?: string }> {
  try {
    const res = await fetch("/api/documents");
    return await res.json();
  } catch {
    return { error: "network_error" };
  }
}