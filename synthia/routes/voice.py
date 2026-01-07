from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter()

_static_dir = Path(__file__).parent.parent / "static"


@router.get("/")
async def voice_interface():
    return FileResponse(_static_dir / "index.html")


def mount_static(app):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")
