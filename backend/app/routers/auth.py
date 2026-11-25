from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..csvutil import to_csv
from ..database import get_db
from ..models import AuditLog, Role, User
from ..schemas import PasswordChangeIn, TokenOut, UserCreate, UserOut
from ..security import audit, create_token, throttle, current_user, hash_password, require, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    throttle.check(form.username)
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        throttle.failed(form.username)
        raise HTTPException(401, "Incorrect username or password")
    throttle.succeeded(form.username)
    audit(db, user, "LOGIN", "user", user.id)
    db.commit()
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/auth/change-password", status_code=204)
def change_password(body: PasswordChangeIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(422, "New password must be different from the current one")
    user.password_hash = hash_password(body.new_password)
    audit(db, user, "UPDATE", "user", user.id, "password changed")
    db.commit()


@router.get("/staff", response_model=list[UserOut])
def staff(role: Role | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(User).where(User.active.is_(True)).order_by(User.full_name)
    if role:
        q = q.where(User.role == role)
    return db.scalars(q).all()


@router.post("/staff", response_model=UserOut, status_code=201)
def create_staff(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require())):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "Username already exists")
    user = User(username=body.username, full_name=body.full_name, role=body.role,
                specialty=body.specialty, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    audit(db, admin, "CREATE", "user", user.id, f"role={body.role.value}")
    db.commit()
    return user


@router.get("/audit.csv")
def audit_csv(limit: int = Query(1000, ge=1, le=10000), username: str | None = None, action: str | None = None,
              db: Session = Depends(get_db), admin: User = Depends(require())):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if username:
        q = q.where(AuditLog.username == username)
    if action:
        q = q.where(AuditLog.action == action.upper())
    rows = db.scalars(q).all()
    audit(db, admin, "READ", "audit_export", None, f"{len(rows)} rows")
    db.commit()
    body = to_csv(["id", "at_utc", "username", "action", "entity", "entity_id", "detail"],
                  [(r.id, r.at.isoformat(timespec="seconds"), r.username, r.action, r.entity, r.entity_id, r.detail) for r in rows])
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'})


@router.get("/audit")
def audit_log(limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require())):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))).all()
    return [dict(id=r.id, at=r.at, username=r.username, action=r.action, entity=r.entity,
                 entity_id=r.entity_id, detail=r.detail) for r in rows]
