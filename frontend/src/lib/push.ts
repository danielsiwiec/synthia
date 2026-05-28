function _toBase64Url(buffer: ArrayBuffer | null): string {
  if (!buffer) return "";
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

export function pushSupported(): boolean {
  return (
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

async function _subscribe(): Promise<void> {
  await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  const reg = await navigator.serviceWorker.ready;
  const res = await fetch("/push/vapid-key");
  const { public_key } = await res.json();
  const applicationServerKey = Uint8Array.from(
    atob(public_key.replace(/-/g, "+").replace(/_/g, "/")),
    (c) => c.charCodeAt(0),
  );

  let sub = await reg.pushManager.getSubscription();
  if (sub) {
    const existing = new Uint8Array(sub.options.applicationServerKey as ArrayBuffer);
    if (
      existing.length !== applicationServerKey.length ||
      existing.some((b, i) => b !== applicationServerKey[i])
    ) {
      await sub.unsubscribe();
      sub = null;
    }
  }
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    });
  }

  await fetch("/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      endpoint: sub.endpoint,
      keys: {
        p256dh: _toBase64Url(sub.getKey("p256dh")),
        auth: _toBase64Url(sub.getKey("auth")),
      },
    }),
  });
}

export async function initPush(
  onNeedsPermission: () => void,
): Promise<void> {
  if (!pushSupported()) return;
  if (Notification.permission === "granted") {
    await _subscribe().catch((e) => console.error("Push subscribe failed:", e));
  } else if (Notification.permission === "default") {
    onNeedsPermission();
  }
}

export async function requestPushPermission(): Promise<boolean> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return false;
  await _subscribe().catch((e) => console.error("Push subscribe failed:", e));
  return true;
}
