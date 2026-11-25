"""Inpatient wards: admissions, bed transfers, discharge."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Admission, Bed, BedTransfer, ERVisit, Role, User, now
from ..schemas import AdmissionOut, AdmitIn, DischargeIn, TransferIn
from ..security import CLINICAL, audit, require
from .helpers import admission_out
from .patients import get_patient_or_404

router = APIRouter(prefix="/api", tags=["inpatient"])


def _free_ward_bed(db: Session, bed_id: int, current: int | None = None) -> Bed:
    bed = db.get(Bed, bed_id)
    if not bed:
        raise HTTPException(404, "Bed not found")
    if bed.ward == "ER":
        raise HTTPException(422, "ER beds are for ER visits; choose an inpatient ward bed")
    if bed.occupied and bed.id != current:
        raise HTTPException(409, f"Bed {bed.label} is occupied")
    return bed


@router.get("/wards")
def wards(db: Session = Depends(get_db), _: User = Depends(require(*CLINICAL))):
    """Bed map per ward with the current occupant."""
    occupants = {a.bed_id: a for a in db.scalars(select(Admission).where(Admission.status == "admitted")).all()}
    out: dict[str, list] = {}
    for b in db.scalars(select(Bed).where(Bed.ward != "ER").order_by(Bed.ward, Bed.label)).all():
        a = occupants.get(b.id)
        out.setdefault(b.ward, []).append(dict(
            id=b.id, label=b.label, occupied=b.occupied, admission_id=a.id if a else None,
            patient_name=f"{a.patient.first_name} {a.patient.last_name}" if a else None,
            reason=a.reason if a else None))
    return [dict(ward=w, beds=beds, occupied=sum(x["occupied"] for x in beds), total=len(beds))
            for w, beds in out.items()]


@router.get("/admissions", response_model=list[AdmissionOut])
def admissions(status: str = "admitted", patient_id: int | None = None, db: Session = Depends(get_db),
               _: User = Depends(require(*CLINICAL))):
    q = select(Admission).order_by(Admission.admitted_at.desc()).limit(300)
    if status != "all":
        q = q.where(Admission.status == status)
    if patient_id:
        q = q.where(Admission.patient_id == patient_id)
    return [admission_out(a) for a in db.scalars(q).all()]


@router.post("/admissions", response_model=AdmissionOut, status_code=201)
def admit(body: AdmitIn, db: Session = Depends(get_db), user: User = Depends(require(Role.doctor, Role.surgeon))):
    get_patient_or_404(db, body.patient_id)
    if db.scalar(select(Admission.id).where(Admission.patient_id == body.patient_id, Admission.status == "admitted")):
        raise HTTPException(409, "Patient is already admitted")
    doc = db.get(User, body.attending_id)
    if not doc or doc.role not in (Role.doctor, Role.surgeon):
        raise HTTPException(422, "attending must be a doctor or surgeon")
    bed = _free_ward_bed(db, body.bed_id)
    source = "direct"
    if body.er_visit_id:
        v = db.get(ERVisit, body.er_visit_id)
        if not v or v.status not in ("waiting", "in_treatment"):
            raise HTTPException(404, "Open ER visit not found")
        if v.patient_id != body.patient_id:
            raise HTTPException(422, "ER visit belongs to a different patient")
        v.status, v.closed_at, source = "admitted", now(), "er"
        if v.bed:
            v.bed.occupied = False
    bed.occupied = True
    a = Admission(patient_id=body.patient_id, bed_id=bed.id, attending_id=doc.id, reason=body.reason,
                  er_visit_id=body.er_visit_id, source=source)
    db.add(a)
    db.flush()
    audit(db, user, "CREATE", "admission", a.id, f"{source} -> {bed.label}")
    db.commit()
    return admission_out(a)


def _active(db: Session, aid: int) -> Admission:
    a = db.get(Admission, aid)
    if not a:
        raise HTTPException(404, "Admission not found")
    if a.status != "admitted":
        raise HTTPException(409, "Patient is already discharged")
    return a


@router.post("/admissions/{aid}/transfer", response_model=AdmissionOut)
def transfer(aid: int, body: TransferIn, db: Session = Depends(get_db), user: User = Depends(require(*CLINICAL))):
    a = _active(db, aid)
    if body.bed_id == a.bed_id:
        raise HTTPException(422, "Patient is already in that bed")
    new = _free_ward_bed(db, body.bed_id)
    old = a.bed
    if old:
        old.occupied = False
    new.occupied = True
    a.bed_id = new.id
    a.transfers.append(BedTransfer(from_bed_id=old.id if old else None, to_bed_id=new.id, by_id=user.id))
    audit(db, user, "UPDATE", "admission", aid, f"transfer {old.label if old else '-'} -> {new.label}")
    db.commit()
    return admission_out(a)


@router.post("/admissions/{aid}/discharge", response_model=AdmissionOut)
def discharge(aid: int, body: DischargeIn, db: Session = Depends(get_db),
              user: User = Depends(require(Role.doctor, Role.surgeon))):
    a = _active(db, aid)
    a.status, a.discharged_at, a.discharge_summary = "discharged", now(), body.summary
    if a.bed:
        a.bed.occupied = False
    audit(db, user, "UPDATE", "admission", aid, "discharged")
    db.commit()
    return admission_out(a)
