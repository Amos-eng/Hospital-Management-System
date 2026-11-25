import os

import asyncio

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, SessionLocal, engine
from .live import hub
from .routers import admissions, auth, dashboard, imaging, patients, roster, scheduling, services
from .seed import seed_if_empty

app = FastAPI(title="Hospital Management System", version="0.1.0")

origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, patients.router, scheduling.router, services.router, dashboard.router,
          admissions.router, roster.router, imaging.router):
    app.include_router(r)


@app.on_event("startup")
async def startup():
    hub.loop = asyncio.get_running_loop()
    Base.metadata.create_all(engine)
    if os.getenv("SEED_DEMO_DATA", "1") == "1":
        with SessionLocal() as db:
            seed_if_empty(db)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.websocket("/api/ws")
async def live(ws: WebSocket):
    await hub.handle(ws)
