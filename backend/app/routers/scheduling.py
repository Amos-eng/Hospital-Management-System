"""Appointments, ER triage/beds, and surgery / OR scheduling."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Appointment, Bed, ERVisit, OperatingRoom, Role, Surgery,
                      SurgeryTeamMember, User, now)
from ..live import hub
from ..schemas import (AppointmentIn, AppointmentOut, BedOut, ERArrivalIn, ERAssignIn,
                       ERVisitOut, RoomOut, StatusIn, SurgeryIn, SurgeryOut)
from ..security import CLINICAL, audit, current_user, require
from .helpers import appt_out, er_out, surgery_out
from .patients import get_patient_or_404

router = APIRouter(prefix="/api", tags=["scheduling"])

SCHEDULERS = (Role.receptionist, *CLINICAL)


# =============== Appointments ===============
@router.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(day: date | None = None, doctor_id: int | None = None, patient_id: int | None = None,
                      db: Session = Depends(get_db), _: User = Depends(require(*SCHEDULERS))):
    q = select(Appointment).order_by(Appointment.start)
    if day:
        q = q.where(Appointment.start >= datetime.combine(day, datetime.min.time()),
                    Appointment.start < datetime.combine(day + timedelta(days=1), datetime.min.time()))
    if doctor_id:
        q = q.where(Appointment.doctor_id == doctor_id)
    if patient_id:
        q = q.where(Appointment.patient_id == patient_id)
    return [appt_out(a) for a in db.scalars(q).all()]


@router.post("/appointments", response_model=AppointmentOut, status_code=201)
def book(body: AppointmentIn, db: Session = Depends(get_db), user: User = Depends(require(*SCHEDULERS))):
    get_patient_or_404(db, body.patient_id)
    doctor = db.get(User, body.doctor_id)
    if not doctor or doctor.role not in (Role.doctor, Role.surgeon):
        raise HTTPException(422, "doctor_id must refer to a doctor or surgeon")
    clash = db.scalar(select(Appointment).where(
        Appointment.doctor_id == body.doctor_id, Appointment.status == "scheduled",
        Appointment.start < body.end, Appointment.end > body.start))
    if clash:
        raise HTTPException(409, f"Doctor already booked {clash.start:%H:%M}-{clash.end:%H:%M}")
    a = Appointment(**body.model_dump())
    db.add(a)
    db.flush()
    audit(db, user, "CREATE", "appointment", a.id)
    db.commit()
    return appt_out(a)


@router.patch("/appointments/{aid}/status", response_model=AppointmentOut)
def appt_status(aid: int, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(require(*SCHEDULERS))):
    if body.status not in {"scheduled", "completed", "cancelled", "no_show"}:
        raise HTTPException(422, "Invalid status")
    a = db.get(Appointment, aid)
    if not a:
        raise HTTPException(404, "Appointment not found")
    a.status = body.status
    audit(db, user, "UPDATE", "appointment", aid, body.status)
    db.commit()
    return appt_out(a)


# =============== Emergency room ===============
@router.get("/beds", response_model=list[BedOut])
def beds(ward: str | None = None, db: Session = Depends(get_db), _: User = Depends(require(*SCHEDULERS))):
    q = select(Bed).order_by(Bed.ward, Bed.label)
    if ward:
        q = q.where(Bed.ward == ward)
    return db.scalars(q).all()


@router.get("/er", response_model=list[ERVisitOut])
def er_board(include_closed: bool = False, db: Session = Depends(get_db), _: User = Depends(require(*CLINICAL, Role.receptionist))):
    q = select(ERVisit)
    if not include_closed:
        q = q.where(ERVisit.status.in_(["waiting", "in_treatment"]))
    rows = db.scalars(q).all()
    # most critical first, then longest waiting
    rows.sort(key=lambda v: (v.triage_level, v.arrived_at))
    return [er_out(v) for v in rows]


@router.post("/er", response_model=ERVisitOut, status_code=201)
def er_arrival(body: ERArrivalIn, db: Session = Depends(get_db), user: User = Depends(require(*CLINICAL, Role.receptionist))):
    get_patient_or_404(db, body.patient_id)
    open_visit = db.scalar(select(ERVisit).where(
        ERVisit.patient_id == body.patient_id, ERVisit.status.in_(["waiting", "in_treatment"])))
    if open_visit:
        raise HTTPException(409, "Patient already has an open ER visit")
    v = ERVisit(**body.model_dump())
    db.add(v)
    db.flush()
    audit(db, user, "CREATE", "er_visit", v.id, f"ESI {v.triage_level}")
    db.commit()
    out = er_out(v)
    if v.triage_level <= 2:
        hub.alert("critical", f"ESI {v.triage_level} arrival in the ER", f"{out.patient_name}: {v.complaint}",
                  roles={Role.doctor, Role.surgeon, Role.nurse, Role.admin})
    return out


@router.post("/er/{vid}/assign", response_model=ERVisitOut)
def er_assign(vid: int, body: ERAssignIn, db: Session = Depends(get_db), user: User = Depends(require(*CLINICAL))):
    v = db.get(ERVisit, vid)
    if not v or v.status not in ("waiting", "in_treatment"):
        raise HTTPException(404, "Open ER visit not found")
    if body.bed_id is not None and body.bed_id != v.bed_id:
        bed = db.get(Bed, body.bed_id)
        if not bed:
            raise HTTPException(404, "Bed not found")
        if bed.occupied:
            raise HTTPException(409, f"Bed {bed.label} is occupied")
        if v.bed:
            v.bed.occupied = False
        bed.occupied = True
        v.bed_id = bed.id
    if body.attending_id is not None:
        doc = db.get(User, body.attending_id)
        if not doc or doc.role not in (Role.doctor, Role.surgeon):
            raise HTTPException(422, "attending must be a doctor or surgeon")
        v.attending_id = doc.id
    if v.bed_id and v.attending_id:
        v.status = "in_treatment"
    audit(db, user, "UPDATE", "er_visit", vid, "assign")
    db.commit()
    return er_out(v)


@router.post("/er/{vid}/close", response_model=ERVisitOut)
def er_close(vid: int, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(require(Role.doctor, Role.surgeon))):
    if body.status == "admitted":
        raise HTTPException(422, "Use POST /api/admissions (with er_visit_id) to admit an ER patient to a ward bed")
    if body.status != "discharged":
        raise HTTPException(422, "status must be 'discharged'")
    v = db.get(ERVisit, vid)
    if not v or v.status not in ("waiting", "in_treatment"):
        raise HTTPException(404, "Open ER visit not found")
    v.status = body.status
    v.closed_at = now()
    if v.bed:
        v.bed.occupied = False
    audit(db, user, "UPDATE", "er_visit", vid, body.status)
    db.commit()
    return er_out(v)


# =============== Surgery / OR ===============
@router.get("/operating-rooms", response_model=list[RoomOut])
def rooms(db: Session = Depends(get_db), _: User = Depends(require(*CLINICAL))):
    return db.scalars(select(OperatingRoom).order_by(OperatingRoom.name)).all()


@router.get("/surgeries", response_model=list[SurgeryOut])
def list_surgeries(day: date | None = None, db: Session = Depends(get_db), _: User = Depends(require(*CLINICAL))):
    q = select(Surgery).order_by(Surgery.start)
    if day:
        q = q.where(Surgery.start >= datetime.combine(day, datetime.min.time()),
                    Surgery.start < datetime.combine(day + timedelta(days=1), datetime.min.time()))
    return [surgery_out(s) for s in db.scalars(q).all()]


def _find_conflicts(db: Session, body: SurgeryIn, ignore_id: int | None = None) -> list[str]:
    active = Surgery.status.in_(["scheduled", "in_progress"])
    overlap = and_(Surgery.start < body.end, Surgery.end > body.start)
    extra = [Surgery.id != ignore_id] if ignore_id else []
    problems = []
    if db.scalar(select(Surgery.id).where(active, overlap, Surgery.room_id == body.room_id, *extra)):
        problems.append("Operating room is already booked in that window")
    if db.scalar(select(Surgery.id).where(active, overlap, Surgery.surgeon_id == body.surgeon_id, *extra)):
        problems.append("Surgeon is already operating in that window")
    for m in body.team:
        uid = m.get("user_id")
        busy = db.scalar(
            select(Surgery.id).join(SurgeryTeamMember, SurgeryTeamMember.surgery_id == Surgery.id)
            .where(active, overlap, SurgeryTeamMember.user_id == uid, *extra))
        busy = busy or db.scalar(select(Surgery.id).where(active, overlap, Surgery.surgeon_id == uid, *extra))
        if busy:
            u = db.get(User, uid)
            problems.append(f"{u.full_name if u else uid} is already assigned in that window")
    return problems


@router.post("/surgeries", response_model=SurgeryOut, status_code=201)
def schedule_surgery(body: SurgeryIn, db: Session = Depends(get_db), user: User = Depends(require(Role.doctor, Role.surgeon, Role.nurse))):
    get_patient_or_404(db, body.patient_id)
    room = db.get(OperatingRoom, body.room_id)
    if not room or not room.active:
        raise HTTPException(422, "Operating room not available")
    surgeon = db.get(User, body.surgeon_id)
    if not surgeon or surgeon.role != Role.surgeon:
        raise HTTPException(422, "surgeon_id must refer to a surgeon")
    for m in body.team:
        if not db.get(User, m.get("user_id")):
            raise HTTPException(422, f"Unknown team member {m.get('user_id')}")
    problems = _find_conflicts(db, body)
    if problems:
        raise HTTPException(409, "; ".join(problems))
    s = Surgery(patient_id=body.patient_id, room_id=body.room_id, surgeon_id=body.surgeon_id,
                procedure=body.procedure, start=body.start, end=body.end, priority=body.priority,
                notes=body.notes)
    s.team = [SurgeryTeamMember(user_id=m["user_id"], role=m.get("role", "assistant")) for m in body.team]
    db.add(s)
    db.flush()
    audit(db, user, "CREATE", "surgery", s.id, f"{body.priority}: {body.procedure}")
    db.commit()
    return surgery_out(s)


@router.patch("/surgeries/{sid}/status", response_model=SurgeryOut)
def surgery_status(sid: int, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(require(Role.doctor, Role.surgeon, Role.nurse))):
    if body.status not in {"scheduled", "in_progress", "completed", "cancelled"}:
        raise HTTPException(422, "Invalid status")
    s = db.get(Surgery, sid)
    if not s:
        raise HTTPException(404, "Surgery not found")
    s.status = body.status
    audit(db, user, "UPDATE", "surgery", sid, body.status)
    db.commit()
    return surgery_out(s)
