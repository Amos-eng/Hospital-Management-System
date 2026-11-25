from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, Role, User
from ..schemas import TokenOut, UserCreate, UserOut
from ..security import audit, create_token, current_user, hash_password, require, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Incorrect username or password")
    audit(db, user, "LOGIN", "user", user.id)
    db.commit()
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


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


@router.get("/audit")
def audit_log(limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require())):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))).all()
    return [dict(id=r.id, at=r.at, username=r.username, action=r.action, entity=r.entity,
                 entity_id=r.entity_id, detail=r.detail) for r in rows]
