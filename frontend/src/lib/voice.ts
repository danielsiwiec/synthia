import {
  VOICE_INPUT_RATE,
  VOICE_OUTPUT_RATE,
  downsample,
  floatTo16BitPCM,
  int16ToFloat32,
  rms,
} from "@/lib/pcm";

export type VoiceRole = "user" | "assistant";
export type VoiceMode = "listening" | "speaking";

export interface VoiceHandlers {
  onReady?: () => void;
  onTranscript?: (role: VoiceRole, text: string, final: boolean) => void;
  onInterrupted?: () => void;
  onTurnComplete?: () => void;
  onMode?: (mode: VoiceMode) => void;
  onVolume?: (volume: number) => void;
  onError?: (message: string) => void;
  onClosed?: (ready: boolean) => void;
}

export interface VoiceConnection {
  mute: () => void;
  unmute: () => void;
  close: () => void;
}

const _CAPTURE_WORKLET = `
class PCMCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._length = 0;
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    this._buffer.push(channel.slice());
    this._length += channel.length;
    if (this._length >= 2048) {
      const out = new Float32Array(this._length);
      let offset = 0;
      for (const chunk of this._buffer) {
        out.set(chunk, offset);
        offset += chunk.length;
      }
      this.port.postMessage(out, [out.buffer]);
      this._buffer = [];
      this._length = 0;
    }
    return true;
  }
}
registerProcessor("pcm-capture", PCMCapture);
`;

function _socketUrl(threadId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/chat/threads/${threadId}/voice`;
}

class _Player {
  private _ctx: AudioContext;
  private _nextTime = 0;
  private _sources = new Set<AudioBufferSourceNode>();
  private _onMode: (mode: VoiceMode) => void;

  constructor(onMode: (mode: VoiceMode) => void) {
    this._ctx = new AudioContext({ sampleRate: VOICE_OUTPUT_RATE });
    this._onMode = onMode;
  }

  enqueue(pcm: ArrayBuffer) {
    const samples = int16ToFloat32(new Int16Array(pcm));
    if (samples.length === 0) return;
    const buffer = this._ctx.createBuffer(1, samples.length, VOICE_OUTPUT_RATE);
    buffer.copyToChannel(samples, 0);
    const source = this._ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this._ctx.destination);
    const startAt = Math.max(this._nextTime, this._ctx.currentTime + 0.02);
    source.start(startAt);
    this._nextTime = startAt + buffer.duration;
    if (this._sources.size === 0) this._onMode("speaking");
    this._sources.add(source);
    source.onended = () => {
      this._sources.delete(source);
      if (this._sources.size === 0) this._onMode("listening");
    };
    if (this._ctx.state === "suspended") void this._ctx.resume();
  }

  flush() {
    for (const source of this._sources) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        // already stopped
      }
    }
    const wasSpeaking = this._sources.size > 0;
    this._sources.clear();
    this._nextTime = 0;
    if (wasSpeaking) this._onMode("listening");
  }

  async close() {
    this.flush();
    await this._ctx.close().catch(() => {});
  }
}

export async function openVoiceConnection(
  threadId: string,
  handlers: VoiceHandlers,
): Promise<VoiceConnection> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const captureCtx = new AudioContext();
  const workletUrl = URL.createObjectURL(new Blob([_CAPTURE_WORKLET], { type: "application/javascript" }));
  try {
    await captureCtx.audioWorklet.addModule(workletUrl);
  } finally {
    URL.revokeObjectURL(workletUrl);
  }
  const source = captureCtx.createMediaStreamSource(stream);
  const capture = new AudioWorkletNode(captureCtx, "pcm-capture");
  source.connect(capture);

  const player = new _Player((mode) => handlers.onMode?.(mode));
  const ws = new WebSocket(_socketUrl(threadId));
  ws.binaryType = "arraybuffer";

  let ready = false;
  let muted = false;
  let closed = false;

  capture.port.onmessage = (event: MessageEvent<Float32Array>) => {
    if (ws.readyState !== WebSocket.OPEN || !ready) return;
    const chunk = event.data;
    handlers.onVolume?.(muted ? 0 : Math.min(1, rms(chunk) * 4));
    if (muted) return;
    const pcm = floatTo16BitPCM(downsample(chunk, captureCtx.sampleRate, VOICE_INPUT_RATE));
    ws.send(pcm.buffer);
  };

  const teardown = async () => {
    if (closed) return;
    closed = true;
    capture.port.onmessage = null;
    for (const track of stream.getTracks()) track.stop();
    source.disconnect();
    capture.disconnect();
    await captureCtx.close().catch(() => {});
    await player.close();
  };

  ws.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
    if (event.data instanceof ArrayBuffer) {
      player.enqueue(event.data);
      return;
    }
    const msg = JSON.parse(event.data) as { type: string; [key: string]: unknown };
    switch (msg.type) {
      case "ready":
        ready = true;
        handlers.onReady?.();
        break;
      case "transcript":
        handlers.onTranscript?.(msg.role as VoiceRole, msg.text as string, Boolean(msg.final));
        break;
      case "interrupted":
        player.flush();
        handlers.onInterrupted?.();
        break;
      case "turn_complete":
        handlers.onTurnComplete?.();
        break;
      case "error":
        handlers.onError?.(String(msg.message ?? "voice session error"));
        break;
    }
  };

  ws.onerror = () => {
    if (!ready) handlers.onError?.("could not open voice session");
  };

  ws.onclose = () => {
    void teardown().then(() => handlers.onClosed?.(ready));
  };

  return {
    mute: () => {
      muted = true;
      for (const track of stream.getAudioTracks()) track.enabled = false;
    },
    unmute: () => {
      muted = false;
      for (const track of stream.getAudioTracks()) track.enabled = true;
    },
    close: () => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "end" }));
      ws.close();
      void teardown();
    },
  };
}
