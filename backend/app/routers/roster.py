"""Staff shift rostering with conflict and coverage checks."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Role, Shift, User, now
from ..schemas import ShiftIn, ShiftOut
from ..security import CLINICAL, audit, current_user, require
from .helpers import shift_out

router = APIRouter(prefix="/api/shifts", tags=["roster"])

ROSTERABLE = (Role.doctor, Role.surgeon, Role.nurse, Role.radiologist, Role.pharmacist, Role.lab_tech)
# minimum people required on each regular shift (on_call is not counted)
MIN_COVER = {"nurse": 2, "doctor": 1, "surgeon": 1}


def _day_bounds(d: date):
    s = datetime.combine(d, datetime.min.time())
    return s, s + timedelta(days=1)


@router.get("", response_model=list[ShiftOut])
def list_shifts(start: date, days: int = 7, user_id: int | None = None, db: Session = Depends(get_db),
                _: User = Depends(current_user)):
    if not 1 <= days <= 31:
        raise HTTPException(422, "days must be between 1 and 31")
    lo, _hi = _day_bounds(start)
    hi = lo + timedelta(days=days)
    q = select(Shift).where(Shift.start < hi, Shift.end > lo).order_by(Shift.start)
    if user_id:
        q = q.where(Shift.user_id == user_id)
    return [shift_out(s) for s in db.scalars(q).all()]


@router.get("/on-duty", response_model=list[ShiftOut])
def on_duty(db: Session = Depends(get_db), _: User = Depends(current_user)):
    t = now()
    rows = db.scalars(select(Shift).where(Shift.start <= t, Shift.end > t).order_by(Shift.kind, Shift.unit)).all()
    return [shift_out(s) for s in rows]


@router.get("/coverage")
def coverage(start: date, days: int = 7, db: Session = Depends(get_db), _: User = Depends(require(*CLINICAL))):
    """For each day and regular shift kind: head-count per role vs the minimum."""
    if not 1 <= days <= 31:
        raise HTTPException(422, "days must be between 1 and 31")
    lo, _hi = _day_bounds(start)
    hi = lo + timedelta(days=days)
    shifts = db.scalars(select(Shift).where(Shift.start >= lo, Shift.start < hi, Shift.kind != "on_call")).all()
    counts = defaultdict(lambda: defaultdict(int))
    for s in shifts:
        counts[(s.start.date(), s.kind)][s.user.role.value] += 1
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        for kind in ("day", "night"):
            c = counts[(d, kind)]
            gaps = {r: need - c.get(r, 0) for r, need in MIN_COVER.items() if c.get(r, 0) < need}
            out.append(dict(date=d.isoformat(), kind=kind, counts={r: c.get(r, 0) for r in MIN_COVER},
                            understaffed=bool(gaps), gaps=gaps))
    return out


@router.post("", response_model=ShiftOut, status_code=201)
def create_shift(body: ShiftIn, db: Session = Depends(get_db), user: User = Depends(require(Role.doctor))):
    person = db.get(User, body.user_id)
    if not person or not person.active:
        raise HTTPException(404, "Staff member not found")
    if person.role not in ROSTERABLE:
        raise HTTPException(422, f"{person.role.value} staff are not rostered here")
    # regular shifts may not overlap each other; on-call may not overlap other on-call
    same_class = (Shift.kind == "on_call") if body.kind == "on_call" else (Shift.kind != "on_call")
    clash = db.scalar(select(Shift).where(Shift.user_id == body.user_id, same_class,
                                          Shift.start < body.end, Shift.end > body.start))
    if clash:
        raise HTTPException(409, f"{person.full_name} already has a {clash.kind} shift "
                                 f"{clash.start:%a %H:%M}-{clash.end:%H:%M} that overlaps")
    # rest rule: at least 8h between the end of one regular shift and the start of the next
    if body.kind != "on_call":
        rest = timedelta(hours=8)
        tight = db.scalar(select(Shift).where(
            Shift.user_id == body.user_id, Shift.kind != "on_call",
            Shift.end > body.start - rest, Shift.start < body.end + rest))
        if tight:
            raise HTTPException(409, f"{person.full_name} needs at least 8 hours rest around the "
                                     f"{tight.start:%a %H:%M}-{tight.end:%H:%M} shift")
    s = Shift(**body.model_dump())
    db.add(s)
    db.flush()
    audit(db, user, "CREATE", "shift", s.id, f"{person.username} {body.kind}")
    db.commit()
    return shift_out(s)


@router.delete("/{sid}", status_code=204)
def delete_shift(sid: int, db: Session = Depends(get_db), user: User = Depends(require(Role.doctor))):
    s = db.get(Shift, sid)
    if not s:
        raise HTTPException(404, "Shift not found")
    audit(db, user, "DELETE", "shift", sid, s.user.username)
    db.delete(s)
    db.commit()
