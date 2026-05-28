export interface SseHandlers {
  onInit?: () => void;
  onProgress?: (summary: string) => void;
  onThought?: (thinking: string) => void;
  onResult?: (result: string) => void;
}

export interface SseConnection {
  close: () => void;
  opened: Promise<void>;
}

export function connectThreadEvents(
  threadId: string,
  handlers: SseHandlers,
): SseConnection {
  const source = new EventSource(`/chat/threads/${threadId}/events`);

  const opened = new Promise<void>((resolve) => {
    // The server emits `connected` immediately after registering the
    // subscriber, so this resolves once events are guaranteed to be delivered.
    source.addEventListener("connected", () => resolve(), { once: true });
    source.addEventListener("open", () => resolve(), { once: true });
  });

  source.addEventListener("init", () => handlers.onInit?.());

  source.addEventListener("progress", (e) => {
    const data = JSON.parse((e as MessageEvent).data);
    handlers.onProgress?.(data.summary);
  });

  source.addEventListener("thought", (e) => {
    const data = JSON.parse((e as MessageEvent).data);
    handlers.onThought?.(data.thinking);
  });

  source.addEventListener("result", (e) => {
    const data = JSON.parse((e as MessageEvent).data);
    handlers.onResult?.(data.result);
  });

  return { close: () => source.close(), opened };
}
