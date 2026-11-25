import os
import threading
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import AuditLog, Role, User

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me-in-production-please-32b")
if os.getenv("APP_ENV") == "production" and SECRET_KEY.startswith("dev-only"):
    raise RuntimeError("Set a strong SECRET_KEY before running with APP_ENV=production")
ALGORITHM = "HS256"
TOKEN_MINUTES = int(os.getenv("TOKEN_MINUTES", "480"))

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class LoginThrottle:
    """Lock a username out after repeated failures (in-memory, per process).

    Keyed by the submitted username, whether or not it exists, so the response never
    reveals which accounts are real. Use a shared store (e.g. Redis) when running several workers.
    """

    def __init__(self, max_fails: int = 5, window_s: int = 15 * 60):
        self.max_fails, self.window_s = max_fails, window_s
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._now = time.monotonic  # replaceable in tests

    def _recent(self, key: str) -> list[float]:
        cutoff = self._now() - self.window_s
        kept = [t for t in self._fails.get(key, []) if t > cutoff]
        if kept:
            self._fails[key] = kept
        else:
            self._fails.pop(key, None)
        return kept

    def check(self, username: str):
        key = username.strip().lower()
        with self._lock:
            recent = self._recent(key)
            if len(recent) >= self.max_fails:
                wait = int(recent[0] + self.window_s - self._now()) + 1
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    f"Too many failed sign-in attempts. Try again in {max(1, wait // 60 + (wait % 60 > 0))} minute(s).",
                                    headers={"Retry-After": str(wait)})

    def failed(self, username: str):
        with self._lock:
            self._fails.setdefault(username.strip().lower(), []).append(self._now())

    def succeeded(self, username: str):
        with self._lock:
            self._fails.pop(username.strip().lower(), None)


throttle = LoginThrottle(int(os.getenv("LOGIN_MAX_FAILS", "5")), int(os.getenv("LOGIN_LOCK_MINUTES", "15")) * 60)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)
    return jwt.encode({"sub": str(user.id), "role": user.role.value, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    err = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                        headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise err
    if not user or not user.active:
        raise err
    return user


def require(*roles: Role):
    """Dependency factory: allow only the listed roles (admin always allowed)."""
    allowed = set(roles) | {Role.admin}

    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role '{user.role.value}' is not permitted here")
        return user

    return dep


CLINICAL = (Role.doctor, Role.surgeon, Role.nurse)


def audit(db: Session, user: User, action: str, entity: str, entity_id: int | None = None, detail: str | None = None):
    db.add(AuditLog(user_id=user.id, username=user.username, action=action,
                    entity=entity, entity_id=entity_id, detail=detail))
