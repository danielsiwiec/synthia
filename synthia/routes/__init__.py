from synthia.routes.audio import router as audio_router
from synthia.routes.health import router as health_router
from synthia.routes.task import router as task_router
from synthia.routes.voice import mount_static
from synthia.routes.voice import router as voice_router

__all__ = ["audio_router", "health_router", "task_router", "voice_router", "mount_static"]
