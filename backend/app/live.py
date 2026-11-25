"""Real-time push: a WebSocket hub plus automatic 'something changed' events.

Design notes
- Clients authenticate with their first message ({"type":"auth","token":...}); the token is never put in a URL.
- Change events carry only a topic name (no patient data). Clients refetch through the normal,
  permission-checked REST endpoints, so the socket cannot leak records.
- Alerts (critical arrivals, abnormal labs ...) are targeted by role and/or user id.
- Topics are derived from committed DB writes, so routers don't have to remember to publish.
"""
import asyncio
import json
import logging

import jwt
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import event
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Role, User
from .security import ALGORITHM, SECRET_KEY

log = logging.getLogger("hms.live")

TABLE_TOPICS = {
    "er_visits": ["er"], "beds": ["beds", "er", "admissions"],
    "surgeries": ["surgery"], "surgery_team": ["surgery"],
    "lab_orders": ["labs"], "imaging_orders": ["imaging"],
    "admissions": ["admissions", "beds"], "bed_transfers": ["admissions", "beds"],
    "shifts": ["roster"], "prescriptions": ["pharmacy"], "drugs": ["pharmacy"],
    "appointments": ["appointments"], "invoices": ["billing"], "payments": ["billing"],
    "invoice_items": ["billing"], "patients": ["patients"], "clinical_notes": ["patients"], "vitals": ["patients"],
}
CLINICAL_ROLES = {Role.doctor, Role.surgeon, Role.nurse, Role.admin}


class Hub:
    def __init__(self):
        self.clients: dict[WebSocket, tuple[int, Role]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    # ---- connection handling ----
    async def handle(self, ws: WebSocket):
        await ws.accept()
        try:
            first = await asyncio.wait_for(ws.receive_text(), timeout=5)
            token = json.loads(first).get("token", "")
            ident = await run_in_threadpool(self._identify, token)
        except (asyncio.TimeoutError, ValueError, WebSocketDisconnect, AttributeError):
            ident = None
        if not ident:
            await ws.close(code=4401)
            return
        self.clients[ws] = ident
        await ws.send_text(json.dumps({"type": "hello"}))
        try:
            while True:  # we only listen so we notice disconnects; clients may send pings
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            self.clients.pop(ws, None)

    @staticmethod
    def _identify(token: str):
        try:
            uid = int(jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            return None
        with SessionLocal() as db:
            u = db.get(User, uid)
            return (u.id, u.role) if u and u.active else None

    # ---- publishing (callable from sync request threads) ----
    async def _send(self, msg: dict, roles=None, user_ids=None):
        data = json.dumps(msg, default=str)
        for ws, (uid, role) in list(self.clients.items()):
            if roles is not None or user_ids is not None:
                if not ((roles and role in roles) or (user_ids and uid in user_ids)):
                    continue
            try:
                await ws.send_text(data)
            except Exception:
                self.clients.pop(ws, None)

    def emit(self, msg: dict, roles=None, user_ids=None):
        if self.loop and self.loop.is_running() and self.clients:
            asyncio.run_coroutine_threadsafe(self._send(msg, roles, user_ids), self.loop)

    def topics(self, topics):
        self.emit({"type": "event", "topics": sorted(set(topics))})

    def alert(self, level: str, title: str, message: str, roles=None, user_ids=None):
        """level: critical | warning | info. Targeted by role and/or user id."""
        self.emit({"type": "alert", "level": level, "title": title, "message": message}, roles, user_ids)


hub = Hub()


# ---- derive topics from committed writes ----
@event.listens_for(Session, "after_flush")
def _collect(session, _ctx):
    bucket = session.info.setdefault("topics", set())
    for obj in (*session.new, *session.dirty, *session.deleted):
        bucket.update(TABLE_TOPICS.get(getattr(obj, "__tablename__", ""), ()))


@event.listens_for(Session, "after_commit")
def _publish(session):
    topics = session.info.pop("topics", None)
    if topics:
        hub.topics(topics)


@event.listens_for(Session, "after_rollback")
def _discard(session):
    session.info.pop("topics", None)
