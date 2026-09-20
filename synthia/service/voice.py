import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types
from loguru import logger

from synthia.agents.agent import VOICE_MODEL_SPEC, Agent

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
_BYTES_PER_SAMPLE = 2
_INPUT_MIME = f"audio/pcm;rate={INPUT_SAMPLE_RATE}"
_CLOSE_TIMEOUT_S = 5

OnTurn = Callable[[str, str, float], Awaitable[None]]
Outbound = bytes | dict[str, Any]


class _Segments:
    def __init__(self) -> None:
        self._done: list[str] = []
        self._partial = ""

    def add(self, text: str | None, finished: bool | None) -> str:
        if finished:
            self._done.append((text or self._partial).strip())
            self._partial = ""
        else:
            self._partial += text or ""
        return self.text

    @property
    def text(self) -> str:
        return " ".join(part for part in (*self._done, self._partial.strip()) if part)


class TurnTranscript:
    def __init__(self) -> None:
        self._user = _Segments()
        self._assistant = _Segments()

    @property
    def user(self) -> str:
        return self._user.text

    @property
    def assistant(self) -> str:
        return self._assistant.text

    def add_input(self, text: str | None, finished: bool | None) -> str:
        return self._user.add(text, finished)

    def add_output(self, text: str | None, finished: bool | None) -> str:
        return self._assistant.add(text, finished)

    def reset(self) -> None:
        self._user = _Segments()
        self._assistant = _Segments()


def audio_cost(input_bytes: int, output_bytes: int) -> float:
    input_minutes = input_bytes / (INPUT_SAMPLE_RATE * _BYTES_PER_SAMPLE) / 60
    output_minutes = output_bytes / (OUTPUT_SAMPLE_RATE * _BYTES_PER_SAMPLE) / 60
    return round(
        input_minutes * VOICE_MODEL_SPEC.audio_input_cost_per_min
        + output_minutes * VOICE_MODEL_SPEC.audio_output_cost_per_min,
        8,
    )


def _run_config() -> RunConfig:
    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(),
        context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
    )


class VoiceSession:
    def __init__(self, agent: Agent, session_id: str, on_turn: OnTurn):
        self._agent = agent
        self._session_id = session_id
        self._on_turn = on_turn
        self._queue = LiveRequestQueue()
        self._outbound: asyncio.Queue[Outbound | None] = asyncio.Queue()
        self._transcript = TurnTranscript()
        self._input_bytes = 0
        self._output_bytes = 0
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        self._spoke = False
        self._log = logger.bind(session_id=session_id, agent="voice")

    @property
    def closed(self) -> bool:
        return self._closed

    async def start(self) -> None:
        self._task = asyncio.create_task(self._pump())
        self._outbound.put_nowait({"type": "ready"})

    def send_audio(self, pcm: bytes) -> None:
        if self._closed:
            return
        self._input_bytes += len(pcm)
        self._queue.send_realtime(types.Blob(data=pcm, mime_type=_INPUT_MIME))

    def send_text(self, text: str) -> None:
        if self._closed:
            return
        self._queue.send_content(types.Content(role="user", parts=[types.Part(text=text)]))

    async def outbound(self) -> AsyncIterator[Outbound]:
        while True:
            item = await self._outbound.get()
            if item is None:
                return
            yield item

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._task is None:
            self._outbound.put_nowait(None)
            return
        self._task.cancel()
        try:
            await asyncio.wait_for(self._task, _CLOSE_TIMEOUT_S)
        except (TimeoutError, asyncio.CancelledError):
            pass
        except Exception as error:
            self._log.warning(f"voice session ended with error: {error}")
        self._queue.close()

    async def _pump(self) -> None:
        try:
            async for event in self._agent.run_live(self._session_id, self._queue, _run_config()):
                await self._handle(event)
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self._log.error(f"voice session failed: {error}")
            self._outbound.put_nowait({"type": "error", "message": str(error)})
        finally:
            await self._flush_turn()
            self._closed = True
            self._outbound.put_nowait(None)

    async def _handle(self, event: Any) -> None:
        error = getattr(event, "error_message", None)
        if error:
            self._outbound.put_nowait({"type": "error", "message": error})

        input_transcription = getattr(event, "input_transcription", None)
        if input_transcription is not None:
            text = self._transcript.add_input(input_transcription.text, input_transcription.finished)
            self._emit_transcript("user", text, bool(input_transcription.finished))

        output_transcription = getattr(event, "output_transcription", None)
        if output_transcription is not None:
            self._spoke = True
            text = self._transcript.add_output(output_transcription.text, output_transcription.finished)
            self._emit_transcript("assistant", text, bool(output_transcription.finished))

        content = getattr(event, "content", None)
        for part in (getattr(content, "parts", None) or []) if content else []:
            blob = getattr(part, "inline_data", None)
            if blob is not None and blob.data and (blob.mime_type or "").startswith("audio/"):
                self._spoke = True
                self._output_bytes += len(blob.data)
                self._outbound.put_nowait(blob.data)
            call = getattr(part, "function_call", None)
            if call is not None:
                self._log.info(f"🔧 [{call.name}] input={dict(call.args or {})}")

        if getattr(event, "interrupted", False):
            self._outbound.put_nowait({"type": "interrupted"})
            await self._flush_turn()

        if getattr(event, "turn_complete", False):
            self._outbound.put_nowait({"type": "turn_complete", "spoke": self._spoke})
            if self._spoke:
                await self._flush_turn()

    def _emit_transcript(self, role: str, text: str, final: bool) -> None:
        if not text:
            return
        self._outbound.put_nowait({"type": "transcript", "role": role, "text": text, "final": final})

    async def _flush_turn(self) -> None:
        user, assistant = self._transcript.user.strip(), self._transcript.assistant.strip()
        if not user and not assistant:
            return
        cost = audio_cost(self._input_bytes, self._output_bytes)
        self._input_bytes = 0
        self._output_bytes = 0
        self._spoke = False
        self._transcript.reset()
        self._log.info(f"🎙️ turn user={user[:60]!r} assistant={assistant[:60]!r} cost=${cost}")
        try:
            await self._on_turn(user, assistant, cost)
        except Exception as error:
            self._log.error(f"voice turn handler failed: {error}")
