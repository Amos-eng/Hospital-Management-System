from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Admission, ImagingOrder, Shift, Appointment, Bed, Drug, ERVisit, Invoice, LabOrder, Patient, Prescription,
                      Surgery, User)
from ..security import current_user

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(tz_offset: int = Query(0, ge=-840, le=840), db: Session = Depends(get_db), _: User = Depends(current_user)):
    local_now = datetime.utcnow() + timedelta(minutes=tz_offset)
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(minutes=tz_offset)
    tomorrow = today + timedelta(days=1)
    count = lambda stmt: db.scalar(stmt) or 0
    beds_total = count(select(func.count(Bed.id)))
    beds_used = count(select(func.count(Bed.id)).where(Bed.occupied.is_(True)))
    return {
        "patients": count(select(func.count(Patient.id))),
        "er_waiting": count(select(func.count(ERVisit.id)).where(ERVisit.status == "waiting")),
        "er_in_treatment": count(select(func.count(ERVisit.id)).where(ERVisit.status == "in_treatment")),
        "er_critical": count(select(func.count(ERVisit.id)).where(
            ERVisit.status.in_(["waiting", "in_treatment"]), ERVisit.triage_level <= 2)),
        "beds_total": beds_total,
        "beds_occupied": beds_used,
        "appointments_today": count(select(func.count(Appointment.id)).where(
            Appointment.start >= today, Appointment.start < tomorrow, Appointment.status == "scheduled")),
        "surgeries_today": count(select(func.count(Surgery.id)).where(
            Surgery.start >= today, Surgery.start < tomorrow, Surgery.status != "cancelled")),
        "surgeries_in_progress": count(select(func.count(Surgery.id)).where(Surgery.status == "in_progress")),
        "labs_pending": count(select(func.count(LabOrder.id)).where(LabOrder.status != "resulted")),
        "rx_pending": count(select(func.count(Prescription.id)).where(Prescription.status == "pending")),
        "low_stock_drugs": count(select(func.count(Drug.id)).where(Drug.stock <= Drug.reorder_level)),
        "inpatients": count(select(func.count(Admission.id)).where(Admission.status == "admitted")),
        "imaging_pending": count(select(func.count(ImagingOrder.id)).where(
            ImagingOrder.status.in_(["ordered", "scheduled", "performed"]))),
        "staff_on_duty": count(select(func.count(Shift.id)).where(
            Shift.start <= datetime.utcnow(), Shift.end > datetime.utcnow(), Shift.kind != "on_call")),
        "open_balance": round(sum(
            (sum(i.quantity * i.unit_price for i in inv.items) - sum(p.amount for p in inv.payments))
            for inv in db.scalars(select(Invoice).where(Invoice.status == "open")).all()), 2),
    }
