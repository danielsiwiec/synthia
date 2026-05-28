import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  deleteThread as apiDeleteThread,
  getMessages,
  listThreads,
  sendMessage,
  stopTask,
  type SynthiaMessage,
  type ThreadSummary,
} from "@/lib/api";
import { connectThreadEvents, type SseConnection } from "@/lib/sse";
import { initPush } from "@/lib/push";

const POLL_INTERVAL = 5000;

function _convertMessage(m: SynthiaMessage): ThreadMessageLike {
  if (m.role === "user") {
    return { role: "user", id: m.id, content: [{ type: "text", text: m.content }] };
  }
  if (m.message_type === "thought") {
    return { role: "assistant", id: m.id, content: [{ type: "reasoning", text: m.content }] };
  }
  return { role: "assistant", id: m.id, content: [{ type: "text", text: m.content }] };
}

function _inferRunning(messages: SynthiaMessage[]): boolean {
  const last = messages[messages.length - 1];
  if (!last) return false;
  if (last.role === "assistant" && last.message_type === "result") return false;
  return last.role === "user" || (last.role === "assistant" && last.message_type === "thought");
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
          setMessages((prev) => [
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
          ]);
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
      const msgs = await getMessages(id);
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
      if (!text) return;

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
        },
      ]);
      setIsRunning(true);
      await connRef.current?.opened;
      await sendMessage(tid, text, null);
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
