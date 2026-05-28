export type Role = "user" | "assistant";
export type MessageType = "user" | "result" | "thought" | "progress";

export interface ThreadSummary {
  id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface SynthiaMessage {
  id: string;
  thread_id: string;
  role: Role;
  message_type: MessageType;
  content: string;
  metadata: { reaction?: string; [key: string]: unknown } | null;
  created_at: string | null;
}

async function _json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export function listThreads(): Promise<ThreadSummary[]> {
  return fetch("/chat/threads").then((r) => _json<ThreadSummary[]>(r));
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
): Promise<void> {
  await fetch(`/chat/threads/${threadId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, reaction }),
  });
}

export async function deleteThread(threadId: string): Promise<void> {
  await fetch(`/chat/threads/${threadId}`, { method: "DELETE" });
}

export async function stopTask(threadId: string): Promise<void> {
  await fetch(`/chat/threads/${threadId}/stop`, { method: "POST" });
}
