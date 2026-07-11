export interface Project {
  id: string;
  name: string;
  tech_stack: string;
  framework_version?: string | null;
}

export interface Session {
  id: string;
  project_id: string;
  title?: string | null;
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at?: string;
}

export interface DomainResult {
  domain: string;
  agent: string;
  summary: string;
  file_path: string;
  code_preview: string;
  stages?: Array<{ stage: string; summary: string }>;
}

export interface ExportResult {
  mode: string;
  target_path: string;
  files_copied: number;
  hint?: string;
}

const API_BASE = "/api";

export async function createProject(name: string): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      tech_stack: "spring-boot",
      framework_version: "4.0",
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createSession(projectId: string, title?: string): Promise<Session> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchMessages(sessionId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function exportProject(projectId: string): Promise<ExportResult> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/export`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function streamChat(
  sessionId: string,
  message: string,
  handlers: {
      onStatus?: (data: Record<string, unknown>) => void;
      onCapabilityEnabled?: (data: Record<string, unknown>) => void;
      onCapabilityGenerating?: (data: Record<string, unknown>) => void;
      onCapabilityGenerated?: (data: Record<string, unknown>) => void;
      onDomainResult?: (data: DomainResult) => void;
    onToken?: (content: string) => void;
    onDone?: (data: Record<string, unknown>) => void;
    onError?: (message: string) => void;
  },
): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    throw new Error(await res.text());
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      if (!part.trim()) continue;
      const lines = part.split("\n");
      let eventType = "message";
      let dataLine = "";
      for (const line of lines) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        if (line.startsWith("data:")) dataLine = line.slice(5).trim();
      }
      if (!dataLine) continue;
      const payload = JSON.parse(dataLine) as Record<string, unknown>;

      if (eventType === "token" && typeof payload.content === "string") {
        handlers.onToken?.(payload.content);
      } else if (eventType === "status") {
        handlers.onStatus?.(payload);
      } else if (eventType === "capability_generating") {
        handlers.onCapabilityGenerating?.(payload);
      } else if (eventType === "capability_generated") {
        handlers.onCapabilityGenerated?.(payload);
      } else if (eventType === "capability_enabled") {
        handlers.onCapabilityEnabled?.(payload);
      } else if (eventType === "domain_result") {
        handlers.onDomainResult?.(payload as unknown as DomainResult);
      } else if (eventType === "done") {
        handlers.onDone?.(payload);
      } else if (eventType === "error") {
        handlers.onError?.(String(payload.message ?? "未知错误"));
      }
    }
  }
}

export async function healthCheck(): Promise<boolean> {
  const res = await fetch(`${API_BASE}/health`);
  return res.ok;
}
