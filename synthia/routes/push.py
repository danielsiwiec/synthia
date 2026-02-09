from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter()

_static_dir = Path(__file__).parent.parent / "static"


class _PushKeys(BaseModel):
    p256dh: str
    auth: str


class _SubscribeRequest(BaseModel):
    endpoint: str
    keys: _PushKeys


@router.get("/sw.js")
async def service_worker():
    return FileResponse(
        _static_dir / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed": "/"}
    )


@router.get("/push/vapid-key")
async def vapid_key(request: Request):
    return {"public_key": request.app.state.push_service.vapid_public_key}


@router.post("/push/subscribe")
async def subscribe(request: Request, body: _SubscribeRequest):
    await request.app.state.push_service.save_subscription(body.endpoint, body.keys.p256dh, body.keys.auth)
    return {"ok": True}
