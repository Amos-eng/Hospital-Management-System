from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ClinicalNote, LabOrder, Patient, Prescription, Role, User, Vitals
from ..schemas import (ImagingOut, LabOrderOut, NoteIn, NoteOut, PatientIn, PatientOut, PrescriptionOut,
                       VitalsIn, VitalsOut)
from ..security import CLINICAL, audit, current_user, require
from ..models import Admission, ERVisit, ImagingOrder, Surgery
from .helpers import imaging_out, lab_out, rx_out

router = APIRouter(prefix="/api/patients", tags=["patients"])

FRONT_DESK = (Role.receptionist, *CLINICAL)


def get_patient_or_404(db: Session, pid: int) -> Patient:
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    return p


def next_mrn(db: Session) -> str:
    last = db.scalar(select(Patient.id).order_by(Patient.id.desc()).limit(1)) or 0
    return f"MRN{last + 1:06d}"


@router.get("", response_model=list[PatientOut])
def search(q: str = "", limit: int = 50, db: Session = Depends(get_db),
           _: User = Depends(require(*FRONT_DESK, Role.billing, Role.pharmacist, Role.lab_tech))):
    stmt = select(Patient).order_by(Patient.last_name, Patient.first_name).limit(min(limit, 200))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Patient.first_name.ilike(like), Patient.last_name.ilike(like),
                              Patient.mrn.ilike(like), Patient.phone.ilike(like)))
    return db.scalars(stmt).all()


@router.post("", response_model=PatientOut, status_code=201)
def register(body: PatientIn, db: Session = Depends(get_db), user: User = Depends(require(*FRONT_DESK))):
    p = Patient(**body.model_dump(), mrn=next_mrn(db))
    db.add(p)
    db.flush()
    audit(db, user, "CREATE", "patient", p.id)
    db.commit()
    return p


@router.get("/{pid}", response_model=PatientOut)
def get_one(pid: int, db: Session = Depends(get_db),
            user: User = Depends(require(*FRONT_DESK, Role.billing, Role.pharmacist, Role.lab_tech))):
    p = get_patient_or_404(db, pid)
    audit(db, user, "READ", "patient", pid)
    db.commit()
    return p


@router.put("/{pid}", response_model=PatientOut)
def update(pid: int, body: PatientIn, db: Session = Depends(get_db), user: User = Depends(require(*FRONT_DESK))):
    p = get_patient_or_404(db, pid)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    audit(db, user, "UPDATE", "patient", pid)
    db.commit()
    return p


# ----- clinical data: clinicians only -----
@router.get("/{pid}/notes", response_model=list[NoteOut])
def notes(pid: int, db: Session = Depends(get_db), user: User = Depends(require(*CLINICAL))):
    get_patient_or_404(db, pid)
    rows = db.scalars(select(ClinicalNote).where(ClinicalNote.patient_id == pid)
                      .order_by(ClinicalNote.at.desc())).all()
    audit(db, user, "READ", "clinical_notes", pid)
    db.commit()
    return [NoteOut(id=n.id, kind=n.kind, text=n.text, at=n.at, author_name=n.author.full_name) for n in rows]


@router.post("/{pid}/notes", response_model=NoteOut, status_code=201)
def add_note(pid: int, body: NoteIn, db: Session = Depends(get_db),
             user: User = Depends(require(Role.doctor, Role.surgeon))):
    get_patient_or_404(db, pid)
    n = ClinicalNote(patient_id=pid, author_id=user.id, kind=body.kind, text=body.text)
    db.add(n)
    db.flush()
    audit(db, user, "CREATE", "clinical_note", n.id)
    db.commit()
    return NoteOut(id=n.id, kind=n.kind, text=n.text, at=n.at, author_name=user.full_name)


@router.get("/{pid}/vitals", response_model=list[VitalsOut])
def vitals(pid: int, db: Session = Depends(get_db), user: User = Depends(require(*CLINICAL))):
    get_patient_or_404(db, pid)
    return db.scalars(select(Vitals).where(Vitals.patient_id == pid).order_by(Vitals.at.desc()).limit(50)).all()


@router.post("/{pid}/vitals", response_model=VitalsOut, status_code=201)
def add_vitals(pid: int, body: VitalsIn, db: Session = Depends(get_db), user: User = Depends(require(*CLINICAL))):
    get_patient_or_404(db, pid)
    v = Vitals(patient_id=pid, **body.model_dump())
    db.add(v)
    db.flush()
    audit(db, user, "CREATE", "vitals", v.id)
    db.commit()
    return v


@router.get("/{pid}/labs", response_model=list[LabOrderOut])
def patient_labs(pid: int, db: Session = Depends(get_db), user: User = Depends(require(*CLINICAL))):
    get_patient_or_404(db, pid)
    rows = db.scalars(select(LabOrder).where(LabOrder.patient_id == pid).order_by(LabOrder.ordered_at.desc())).all()
    return [lab_out(r) for r in rows]


@router.get("/{pid}/prescriptions", response_model=list[PrescriptionOut])
def patient_rx(pid: int, db: Session = Depends(get_db), user: User = Depends(require(*CLINICAL))):
    get_patient_or_404(db, pid)
    rows = db.scalars(select(Prescription).where(Prescription.patient_id == pid)
                      .order_by(Prescription.created_at.desc())).all()
    return [rx_out(r) for r in rows]


@router.get("/{pid}/imaging", response_model=list[ImagingOut])
def patient_imaging(pid: int, db: Session = Depends(get_db), user: User = Depends(require(*CLINICAL))):
    get_patient_or_404(db, pid)
    rows = db.scalars(select(ImagingOrder).where(ImagingOrder.patient_id == pid)
                      .order_by(ImagingOrder.ordered_at.desc())).all()
    return [imaging_out(r) for r in rows]


@router.get("/{pid}/timeline")
def timeline(pid: int, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
             user: User = Depends(require(*CLINICAL))):
    """Everything that happened to a patient, newest first, from every module."""
    get_patient_or_404(db, pid)
    ev = []

    def add(at, kind, title, detail=None, by=None, flag=False):
        if at:
            ev.append(dict(at=at, kind=kind, title=title, detail=detail, by=by, flag=flag))

    for n in db.scalars(select(ClinicalNote).where(ClinicalNote.patient_id == pid)):
        add(n.at, "note", f"{n.kind.capitalize()} note", n.text[:300], n.author.full_name)
    for v in db.scalars(select(Vitals).where(Vitals.patient_id == pid)):
        parts = [f"HR {v.heart_rate}" if v.heart_rate is not None else None,
                 f"BP {v.systolic}/{v.diastolic}" if v.systolic is not None else None,
                 f"Temp {v.temperature_c}°C" if v.temperature_c is not None else None,
                 f"SpO2 {v.spo2}%" if v.spo2 is not None else None,
                 f"RR {v.resp_rate}" if v.resp_rate is not None else None]
        add(v.at, "vitals", "Vitals recorded", " · ".join(p for p in parts if p), flag=v.spo2 is not None and v.spo2 < 94)
    for l in db.scalars(select(LabOrder).where(LabOrder.patient_id == pid)):
        add(l.ordered_at, "lab", f"Lab ordered: {l.test_name}", f"Priority {l.priority}", l.ordered_by.full_name)
        add(l.resulted_at, "lab", f"Lab resulted: {l.test_name}", l.result, flag=l.abnormal)
    for i in db.scalars(select(ImagingOrder).where(ImagingOrder.patient_id == pid)):
        add(i.ordered_at, "imaging", f"Imaging ordered: {i.modality.upper()} {i.body_part}", i.clinical_info, i.ordered_by.full_name)
        add(i.reported_at, "imaging", f"Imaging reported: {i.modality.upper()} {i.body_part}", (i.report or "")[:300],
            i.radiologist.full_name if i.radiologist else None, flag=i.critical)
    for r in db.scalars(select(Prescription).where(Prescription.patient_id == pid)):
        add(r.created_at, "prescription", f"Prescribed: {r.drug.name}", f"{r.dosage} x{r.quantity}", r.prescriber.full_name)
        add(r.dispensed_at, "prescription", f"Dispensed: {r.drug.name}")
    for a in db.scalars(select(Admission).where(Admission.patient_id == pid)):
        add(a.admitted_at, "admission", "Admitted", a.reason, a.attending.full_name)
        add(a.discharged_at, "admission", "Discharged", (a.discharge_summary or "")[:300])
    for e in db.scalars(select(ERVisit).where(ERVisit.patient_id == pid)):
        add(e.arrived_at, "er", f"ER arrival (ESI {e.triage_level})", e.complaint, flag=e.triage_level <= 2)
        add(e.closed_at, "er", f"ER visit closed: {e.status}")
    for s in db.scalars(select(Surgery).where(Surgery.patient_id == pid)):
        add(s.start, "surgery", f"Surgery: {s.procedure}", f"{s.priority}, {s.status}", s.surgeon.full_name)

    ev.sort(key=lambda e: e["at"], reverse=True)
    audit(db, user, "READ", "patient_timeline", pid)
    db.commit()
    return ev[:limit]
