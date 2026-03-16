from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.webhook import router as webhook_router, store, flow
from app.api.dashboard import router as dashboard_router
from app.core.config import settings

app = FastAPI(title="Empressa Fashion Bot Backend")

# Serve images for WhatsApp via ngrok:
# /static/catalog/img_001.png
# /static/generated/<file>.png
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(webhook_router)
app.include_router(dashboard_router)

_checker_task = None

@app.get("/health")
def health():
    return {"status": "ok"}


async def inactivity_checker():
    """Reuses the same store and flow instances as the webhook router."""
    while True:
        try:
            expired = await store.pop_expired_sessions()
            if expired:
                print(f"[checker] expired candidates: {expired} timeout={settings.SESSION_TIMEOUT_SECONDS}")
            for wa_id in expired:
                await flow.force_timeout(wa_id)
        except Exception as e:
            print(f"[checker] error: {e}")

        await asyncio.sleep(settings.CHECKER_INTERVAL_SECONDS)


@app.on_event("startup")
async def on_startup():
    global _checker_task
    _checker_task = asyncio.create_task(inactivity_checker())


@app.on_event("shutdown")
async def on_shutdown():
    global _checker_task
    if _checker_task:
        _checker_task.cancel()
        try:
            await _checker_task
        except asyncio.CancelledError:
            pass
    print("[shutdown] cleanup complete")
