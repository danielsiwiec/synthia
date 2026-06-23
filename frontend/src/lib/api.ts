export type Role = "user" | "assistant";
export type MessageType = "user" | "result" | "thought" | "progress" | "image";

export interface ThreadSummary {
  id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface Project {
  id: string;
  name: string;
  status: "active" | "closed";
  next_step: string;
  document: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface OutgoingAttachment {
  name: string;
  content_type: string;
  data: string;
}

export interface DisplayAttachment {
  id: string;
  type: "image" | "document" | "file";
  name: string;
  content_type: string;
  url: string;
}

export interface SynthiaMessage {
  id: string;
  thread_id: string;
  role: Role;
  message_type: MessageType;
  content: string;
  metadata: {
    reaction?: string;
    persona?: string | null;
    consulted_personas?: string[];
    [key: string]: unknown;
  } | null;
  created_at: string | null;
  attachments?: DisplayAttachment[];
}

async function _json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export function listThreads(): Promise<ThreadSummary[]> {
  return fetch("/chat/threads").then((r) => _json<ThreadSummary[]>(r));
}

export function listProjects(): Promise<Project[]> {
  return fetch("/chat/projects").then((r) => _json<Project[]>(r));
}

export function getMessages(threadId: string): Promise<SynthiaMessage[]> {
  return fetch(`/chat/threads/${threadId}/messages`).then((r) =>
    _json<SynthiaMessage[]>(r),
  );
}

export async function sendMessage(
  threadId: string,
  content: string,
  reaction: string | null,
  attachments?: OutgoingAttachment[],
  projectId?: string | null,
  persona?: string | null,
): Promise<void> {
  await fetch(`/chat/threads/${threadId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      reaction,
      attachments,
      project_id: projectId ?? null,
      persona: persona ?? null,
    }),
  });
}

export async function renameThread(threadId: string, title: string): Promise<void> {
  await fetch(`/chat/threads/${threadId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function deleteThread(threadId: string): Promise<void> {
  await fetch(`/chat/threads/${threadId}`, { method: "DELETE" });
}

export async function stopTask(threadId: string): Promise<void> {
  await fetch(`/chat/threads/${threadId}/stop`, { method: "POST" });
}
