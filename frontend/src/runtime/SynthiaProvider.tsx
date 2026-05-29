import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  type AppendMessage,
  type CompleteAttachment,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  deleteThread as apiDeleteThread,
  getMessages,
  listThreads,
  sendMessage,
  stopTask,
  type DisplayAttachment,
  type OutgoingAttachment,
  type SynthiaMessage,
  type ThreadSummary,
} from "@/lib/api";
import { attachmentAdapter } from "@/runtime/attachmentAdapter";
import { connectThreadEvents, type SseConnection } from "@/lib/sse";
import { initPush } from "@/lib/push";

const POLL_INTERVAL = 5000;

// assistant-ui only renders image message parts whose src is a data:, blob:, or https:// URL
// (see sanitizeImageContent). Our attachment URLs are same-origin relative paths, so fetch them
// into a blob: URL before they reach the message store.
const _blobUrlCache = new Map<string, string>();

async function _toDisplayUrl(url: string): Promise<string> {
  if (/^(data:|blob:|https:\/\/)/.test(url)) return url;
  const cached = _blobUrlCache.get(url);
  if (cached) return cached;
  try {
    const res = await fetch(url);
    const blobUrl = URL.createObjectURL(await res.blob());
    _blobUrlCache.set(url, blobUrl);
    return blobUrl;
  } catch {
    return url;
  }
}

async function _resolveImageUrls(messages: SynthiaMessage[]): Promise<SynthiaMessage[]> {
  return Promise.all(
    messages.map(async (m) => {
      if (!m.attachments?.length) return m;
      const attachments = await Promise.all(
        m.attachments.map(async (a) => (a.type === "image" ? { ...a, url: await _toDisplayUrl(a.url) } : a)),
      );
      return { ...m, attachments };
    }),
  );
}

function _dataUrlOf(att: CompleteAttachment): string | undefined {
  const part = att.content?.[0];
  if (part?.type === "image") return part.image;
  if (part?.type === "file") return part.data;
  return undefined;
}

function _splitAttachments(attachments: readonly CompleteAttachment[]): {
  display: DisplayAttachment[];
  outgoing: OutgoingAttachment[];
} {
  const display: DisplayAttachment[] = [];
  const outgoing: OutgoingAttachment[] = [];
  for (const att of attachments) {
    const dataUrl = _dataUrlOf(att);
    if (!dataUrl) continue;
    const contentType = att.contentType ?? "";
    const type = att.type === "image" ? "image" : att.type === "document" ? "document" : "file";
    display.push({ id: att.id, type, name: att.name, content_type: contentType, url: dataUrl });
    const comma = dataUrl.indexOf(",");
    outgoing.push({
      name: att.name,
      content_type: contentType,
      data: comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl,
    });
  }
  return { display, outgoing };
}

function _attachmentParts(attachments: DisplayAttachment[]) {
  return attachments.map((a) => ({
    id: a.id,
    type: a.type,
    name: a.name,
    contentType: a.content_type,
    status: { type: "complete" as const },
    content: [
      a.type === "image"
        ? { type: "image" as const, image: a.url, filename: a.name }
        : {
            type: "file" as const,
            data: a.url,
            mimeType: a.content_type || "application/octet-stream",
            filename: a.name,
          },
    ],
  }));
}

function _convertMessage(m: SynthiaMessage): ThreadMessageLike {
  if (m.role === "user") {
    const content = m.content ? [{ type: "text" as const, text: m.content }] : [];
    return {
      role: "user",
      id: m.id,
      content,
      ...(m.attachments?.length ? { attachments: _attachmentParts(m.attachments) } : {}),
    };
  }
  if (m.message_type === "thought") {
    return { role: "assistant", id: m.id, content: [{ type: "reasoning", text: m.content }] };
  }
  if (m.attachments?.length) {
    const caption = m.content ? [{ type: "text" as const, text: m.content }] : [];
    const images = m.attachments.map((a) => ({ type: "image" as const, image: a.url }));
    return { role: "assistant", id: m.id, content: [...caption, ...images] };
  }
  return { role: "assistant", id: m.id, content: [{ type: "text", text: m.content }] };
}

function _inferRunning(messages: SynthiaMessage[]): boolean {
  // A turn is in flight only when the latest user message has no result after it. We can't just
  // look at the last message: with interleaved thinking the model emits a final thought that is
  // persisted slightly after the result, so a completed turn often ends on a thought.
  let lastUser = -1;
  let lastResult = -1;
  messages.forEach((m, i) => {
    if (m.role === "user") lastUser = i;
    else if (m.role === "assistant" && m.message_type === "result") lastResult = i;
  });
  if (lastUser === -1) return false;
  return lastResult < lastUser;
}

export function SynthiaProvider({ children }: { children: ReactNode }) {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SynthiaMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const threadIdRef = useRef<string | null>(null);
  const connRef = useRef<SseConnection | null>(null);

  const refreshThreads = useCallback(async () => {
    setThreads(await listThreads());
  }, []);

  const _disconnect = useCallback(() => {
    connRef.current?.close();
    connRef.current = null;
  }, []);

  const _connect = useCallback(
    (threadId: string): SseConnection => {
      _disconnect();
      const conn = connectThreadEvents(threadId, {
        onInit: () => setIsRunning(true),
        onThought: (thinking) => {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant" && last.message_type === "thought") {
              return [...prev.slice(0, -1), { ...last, content: thinking }];
            }
            return [
              ...prev,
              {
                id: `t-${Date.now()}-${prev.length}`,
                thread_id: threadId,
                role: "assistant",
                message_type: "thought",
                content: thinking,
                metadata: null,
                created_at: null,
              },
            ];
          });
          setIsRunning(true);
        },
        onResult: (result) => {
          setMessages((prev) => [
            ...prev,
            {
              id: `r-${Date.now()}-${prev.length}`,
              thread_id: threadId,
              role: "assistant",
              message_type: "result",
              content: result,
              metadata: null,
              created_at: null,
            },
          ]);
          setIsRunning(false);
          void refreshThreads();
        },
        onImage: (data) => {
          void (async () => {
            const url = await _toDisplayUrl(data.attachment.url);
            setMessages((prev) => [
              ...prev,
              {
                id: `i-${Date.now()}-${prev.length}`,
                thread_id: threadId,
                role: "assistant",
                message_type: "image",
                content: data.caption ?? "",
                metadata: null,
                created_at: null,
                attachments: [
                  {
                    id: `i-${Date.now()}-att`,
                    type: "image",
                    name: data.attachment.name,
                    content_type: data.attachment.content_type,
                    url,
                  },
                ],
              },
            ]);
          })();
        },
      });
      connRef.current = conn;
      return conn;
    },
    [_disconnect, refreshThreads],
  );

  const newThread = useCallback(() => {
    const id = String(Date.now());
    threadIdRef.current = id;
    setCurrentThreadId(id);
    setMessages([]);
    setIsRunning(false);
    _connect(id);
  }, [_connect]);

  const switchThread = useCallback(
    async (id: string) => {
      threadIdRef.current = id;
      setCurrentThreadId(id);
      const msgs = await _resolveImageUrls(await getMessages(id));
      setMessages(msgs);
      setIsRunning(_inferRunning(msgs));
      _connect(id);
    },
    [_connect],
  );

  const removeThread = useCallback(
    async (id: string) => {
      await apiDeleteThread(id);
      if (threadIdRef.current === id) {
        threadIdRef.current = null;
        setCurrentThreadId(null);
        setMessages([]);
        setIsRunning(false);
        _disconnect();
      }
      await refreshThreads();
    },
    [_disconnect, refreshThreads],
  );

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const part = message.content.find((p) => p.type === "text");
      const text = part && part.type === "text" ? part.text.trim() : "";
      const { display, outgoing } = _splitAttachments(message.attachments ?? []);
      if (!text && outgoing.length === 0) return;

      let tid = threadIdRef.current;
      if (!tid) {
        tid = String(Date.now());
        threadIdRef.current = tid;
        setCurrentThreadId(tid);
        _connect(tid);
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `u-${Date.now()}`,
          thread_id: tid as string,
          role: "user",
          message_type: "user",
          content: text,
          metadata: null,
          created_at: null,
          attachments: display.length ? display : undefined,
        },
      ]);
      setIsRunning(true);
      await connRef.current?.opened;
      await sendMessage(tid, text, null, outgoing.length ? outgoing : undefined);
      void refreshThreads();
    },
    [_connect, refreshThreads],
  );

  const onCancel = useCallback(async () => {
    const tid = threadIdRef.current;
    if (tid) await stopTask(tid);
    setIsRunning(false);
  }, []);

  const runtime = useExternalStoreRuntime<SynthiaMessage>({
    isRunning,
    messages,
    convertMessage: _convertMessage,
    onNew,
    onCancel,
    adapters: {
      attachments: attachmentAdapter,
      threadList: {
        threadId: currentThreadId ?? undefined,
        threads: threads.map((t) => ({ status: "regular", id: t.id, title: t.title })),
        onSwitchToNewThread: newThread,
        onSwitchToThread: switchThread,
        onDelete: removeThread,
      },
    },
  });

  useEffect(() => {
    void refreshThreads();
    void initPush(() => {});
    return () => _disconnect();
  }, [refreshThreads, _disconnect]);

  useEffect(() => {
    let timer: number | undefined;
    const start = () => {
      timer = window.setInterval(() => void refreshThreads(), POLL_INTERVAL);
    };
    const stop = () => {
      if (timer) window.clearInterval(timer);
      timer = undefined;
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else {
        void refreshThreads();
        start();
      }
    };
    start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refreshThreads]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <TooltipProvider>{children}</TooltipProvider>
    </AssistantRuntimeProvider>
  );
}
