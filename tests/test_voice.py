import asyncio
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from synthia.agents.agent import VOICE_MODEL, Agent, required_api_key
from synthia.service.voice import INPUT_SAMPLE_RATE, OUTPUT_SAMPLE_RATE, TurnTranscript, VoiceSession, audio_cost

_VOICE_KEY = required_api_key(VOICE_MODEL)
_HAS_KEY = bool(_VOICE_KEY and os.getenv(_VOICE_KEY))
_HAS_SAY = sys.platform == "darwin" and shutil.which("say") is not None


@pytest.mark.smoke
def test_transcript_partials_accumulate_and_final_closes_a_segment() -> None:
    transcript = TurnTranscript()
    assert transcript.add_output("Good", False) == "Good"
    assert transcript.add_output("bye for ", False) == "Goodbye for"
    assert transcript.add_output("Goodbye for now.", True) == "Goodbye for now."
    assert transcript.add_output("See you.", True) == "Goodbye for now. See you."
    assert transcript.add_input("what's ", False) == "what's"
    assert transcript.add_input(None, True) == "what's"
    transcript.reset()
    assert transcript.user == "" and transcript.assistant == ""


@pytest.mark.smoke
def test_audio_cost_uses_per_minute_rates() -> None:
    one_minute_in = INPUT_SAMPLE_RATE * 2 * 60
    one_minute_out = OUTPUT_SAMPLE_RATE * 2 * 60
    assert audio_cost(one_minute_in, one_minute_out) == pytest.approx(0.005 + 0.018)
    assert audio_cost(0, 0) == 0


async def _collect(session: VoiceSession, timeout: float = 90) -> tuple[int, list[dict]]:
    audio_bytes = 0
    events: list[dict] = []

    async def _drain() -> None:
        nonlocal audio_bytes
        async for item in session.outbound():
            if isinstance(item, bytes):
                audio_bytes += len(item)
                continue
            events.append(item)
            if item["type"] == "error" or (item["type"] == "turn_complete" and item["spoke"]):
                return

    await asyncio.wait_for(_drain(), timeout)
    return audio_bytes, events


def _voice_tools() -> tuple[list, list[str]]:
    calls: list[str] = []

    def get_weather(city: str) -> dict:
        """Look up the current weather for a city.

        Args:
            city: The city name.
        """
        calls.append(city)
        return {"city": city, "temp_c": 21, "sky": "clear"}

    return [get_weather], calls


@pytest.mark.skipif(not _HAS_KEY, reason=f"requires {_VOICE_KEY}")
async def test_voice_session_speaks_calls_tools_and_reports_turn() -> None:
    tools, calls = _voice_tools()
    agent = await Agent.create(model=VOICE_MODEL, tools=tools, system_prompt="Be brief.", include_builtins=False)
    turns: list[tuple[str, str, float]] = []

    async def _on_turn(user: str, assistant: str, cost: float) -> None:
        turns.append((user, assistant, cost))

    session = VoiceSession(agent, "voice-test-text", _on_turn)
    await session.start()
    try:
        session.send_text("What's the weather in Paris? Use the tool, then answer in one short sentence.")
        audio_bytes, events = await _collect(session)
    finally:
        await session.close()
        await agent.disconnect()

    assert events[0]["type"] == "ready"
    assert events[-1]["type"] == "turn_complete"
    assert audio_bytes > 0
    assert calls == ["Paris"]
    transcripts = [e for e in events if e["type"] == "transcript" and e["role"] == "assistant"]
    assert transcripts and transcripts[-1]["final"] is True
    assert len(turns) == 1
    user_text, assistant_text, cost = turns[0]
    assert user_text == ""
    assert assistant_text == transcripts[-1]["text"].strip()
    assert cost > 0


@pytest.mark.skipif(not (_HAS_KEY and _HAS_SAY), reason="requires the voice model key and macOS `say`")
async def test_voice_session_transcribes_spoken_audio(tmp_path: Path) -> None:
    wav_path = tmp_path / "question.wav"
    subprocess.run(
        ["say", "-o", str(wav_path), "--data-format=LEI16@16000", "What is the weather in Paris today?"],
        check=True,
    )
    with wave.open(str(wav_path)) as wav:
        assert wav.getframerate() == INPUT_SAMPLE_RATE and wav.getsampwidth() == 2 and wav.getnchannels() == 1
        pcm = wav.readframes(wav.getnframes())

    tools, calls = _voice_tools()
    agent = await Agent.create(model=VOICE_MODEL, tools=tools, system_prompt="Be brief.", include_builtins=False)
    turns: list[tuple[str, str, float]] = []

    async def _on_turn(user: str, assistant: str, cost: float) -> None:
        turns.append((user, assistant, cost))

    session = VoiceSession(agent, "voice-test-audio", _on_turn)
    await session.start()
    chunk = INPUT_SAMPLE_RATE * 2 // 10

    async def _microphone() -> None:
        await asyncio.sleep(1)
        for offset in range(0, len(pcm), chunk):
            session.send_audio(pcm[offset : offset + chunk])
        while not session.closed:
            session.send_audio(bytes(chunk))
            await asyncio.sleep(0.1)

    microphone = asyncio.create_task(_microphone())
    try:
        audio_bytes, events = await _collect(session)
    finally:
        microphone.cancel()
        await session.close()
        await agent.disconnect()

    assert events[-1]["type"] == "turn_complete"
    assert audio_bytes > 0
    assert calls == ["Paris"]
    user_transcripts = [e for e in events if e["type"] == "transcript" and e["role"] == "user"]
    assert user_transcripts and "paris" in user_transcripts[-1]["text"].lower()
    assert len(turns) == 1
    assert "paris" in turns[0][0].lower()
    assert turns[0][1]
