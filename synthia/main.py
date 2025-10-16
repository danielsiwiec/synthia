import os
from fastapi import FastAPI
from dotenv import load_dotenv

from synthia.telegram import Telegram


async def lifespan(app: FastAPI):
    telegram = Telegram(token=os.environ["TELEGRAM_BOT_TOKEN"], chat_id=os.environ["TELEGRAM_CHAT_ID"])
    await telegram.start()
    yield


app = FastAPI(title="Synthia", lifespan=lifespan)

load_dotenv()


@app.get("/")
async def root():
    return {"status": "OK"}
