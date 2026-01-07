from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from loguru import logger

router = APIRouter()


@router.get("/tts")
async def text_to_speech(request: Request, text: str, voice: str = "shimmer"):
    response = await request.app.state.openai_client.audio.speech.create(
        model="tts-1",
        voice=voice,  # type: ignore[arg-type]
        input=text,
        response_format="mp3",
    )

    def stream_audio():
        yield from response.iter_bytes(1024)

    return StreamingResponse(stream_audio(), media_type="audio/mpeg")


@router.post("/transcribe")
async def transcribe_audio(request: Request, audio: UploadFile):
    audio_data = await audio.read()

    if len(audio_data) < 100:
        logger.warning(f"Audio data too small: {len(audio_data)} bytes")
        raise HTTPException(status_code=400, detail="Audio data too small or empty")

    try:
        transcription = await request.app.state.openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=(audio.filename or "audio.webm", audio_data),
        )
        return {"text": transcription.text}
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}") from e
