import os
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
