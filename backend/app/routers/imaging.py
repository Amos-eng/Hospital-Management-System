"""Radiology: orders, scheduling, performing and reporting."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..live import hub
from ..models import ImagingOrder, Role, User, now
from ..schemas import ImagingIn, ImagingOut, ImagingReportIn, ImagingScheduleIn
from ..security import CLINICAL, audit, require
from .helpers import imaging_out
from .patients import get_patient_or_404

router = APIRouter(prefix="/api/imaging", tags=["imaging"])

ORDERERS = (Role.doctor, Role.surgeon, Role.nurse)
CONTRAST_ALLERGY_WORDS = ("contrast", "iodine", "gadolinium")


def _get(db: Session, iid: int) -> ImagingOrder:
    o = db.get(ImagingOrder, iid)
    if not o:
        raise HTTPException(404, "Imaging order not found")
    return o


@router.get("", response_model=list[ImagingOut])
def list_orders(status: str | None = None, patient_id: int | None = None, db: Session = Depends(get_db),
                _: User = Depends(require(Role.radiologist, *CLINICAL))):
    urgency = case((ImagingOrder.priority == "stat", 0), (ImagingOrder.priority == "urgent", 1), else_=2)
    q = select(ImagingOrder).order_by(urgency, ImagingOrder.ordered_at.desc()).limit(300)
    if status:
        q = q.where(ImagingOrder.status == status)
    if patient_id:
        q = q.where(ImagingOrder.patient_id == patient_id)
    return [imaging_out(o) for o in db.scalars(q).all()]


@router.post("", response_model=ImagingOut, status_code=201)
def order(body: ImagingIn, db: Session = Depends(get_db), user: User = Depends(require(*ORDERERS))):
    patient = get_patient_or_404(db, body.patient_id)
    if body.contrast and body.modality in ("xray", "ultrasound"):
        raise HTTPException(422, "Contrast is only used with CT or MRI")
    allergic = patient.allergies and any(w in patient.allergies.lower() for w in CONTRAST_ALLERGY_WORDS)
    if body.contrast and allergic and not body.override_allergy:
        raise HTTPException(409, f"Allergy warning: patient has a recorded contrast-related allergy "
                                 f"({patient.allergies}). Re-submit with the override only if clinically justified.")
    o = ImagingOrder(**body.model_dump(exclude={"override_allergy"}), ordered_by_id=user.id)
    db.add(o)
    db.flush()
    audit(db, user, "CREATE", "imaging_order", o.id, f"{body.modality} {body.body_part} {body.priority}")
    if body.contrast and allergic:
        audit(db, user, "WARN", "imaging_order", o.id, f"contrast allergy override: {patient.allergies}")
    db.commit()
    if body.priority == "stat":
        hub.alert("warning", "STAT imaging ordered", f"{body.modality.upper()} {body.body_part} — {patient.first_name} {patient.last_name}",
                  roles={Role.radiologist})
    return imaging_out(o)


@router.post("/{iid}/schedule", response_model=ImagingOut)
def schedule(iid: int, body: ImagingScheduleIn, db: Session = Depends(get_db),
             user: User = Depends(require(Role.radiologist, Role.nurse))):
    o = _get(db, iid)
    if o.status not in ("ordered", "scheduled"):
        raise HTTPException(409, f"Order is already {o.status}")
    # one scanner per modality: no overlapping 30-minute slots
    from datetime import timedelta
    clash = db.scalar(select(ImagingOrder).where(
        ImagingOrder.modality == o.modality, ImagingOrder.status == "scheduled", ImagingOrder.id != o.id,
        ImagingOrder.scheduled_at < body.scheduled_at + timedelta(minutes=30),
        ImagingOrder.scheduled_at > body.scheduled_at - timedelta(minutes=30)))
    if clash:
        raise HTTPException(409, f"The {o.modality.upper()} scanner is booked around {clash.scheduled_at:%H:%M}")
    o.status, o.scheduled_at = "scheduled", body.scheduled_at
    audit(db, user, "UPDATE", "imaging_order", iid, "scheduled")
    db.commit()
    return imaging_out(o)


@router.post("/{iid}/perform", response_model=ImagingOut)
def perform(iid: int, db: Session = Depends(get_db), user: User = Depends(require(Role.radiologist))):
    o = _get(db, iid)
    if o.status not in ("ordered", "scheduled"):
        raise HTTPException(409, f"Order is already {o.status}")
    o.status, o.performed_at = "performed", now()
    audit(db, user, "UPDATE", "imaging_order", iid, "performed")
    db.commit()
    return imaging_out(o)


@router.post("/{iid}/report", response_model=ImagingOut)
def report(iid: int, body: ImagingReportIn, db: Session = Depends(get_db), user: User = Depends(require(Role.radiologist))):
    o = _get(db, iid)
    if o.status != "performed":
        raise HTTPException(409, "The scan must be performed before it can be reported")
    o.status, o.report, o.critical = "reported", body.report, body.critical
    o.radiologist_id, o.reported_at = user.id, now()
    audit(db, user, "UPDATE", "imaging_order", iid, "reported" + (" CRITICAL" if body.critical else ""))
    db.commit()
    if body.critical:
        hub.alert("critical", "Critical imaging finding",
                  f"{o.modality.upper()} {o.body_part} — {o.patient.first_name} {o.patient.last_name}. Review the report now.",
                  user_ids={o.ordered_by_id})
    return imaging_out(o)


@router.post("/{iid}/cancel", response_model=ImagingOut)
def cancel(iid: int, db: Session = Depends(get_db), user: User = Depends(require(Role.radiologist, *ORDERERS))):
    o = _get(db, iid)
    if o.status in ("reported", "cancelled"):
        raise HTTPException(409, f"Order is already {o.status}")
    o.status = "cancelled"
    audit(db, user, "UPDATE", "imaging_order", iid, "cancelled")
    db.commit()
    return imaging_out(o)
