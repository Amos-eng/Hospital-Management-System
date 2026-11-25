from datetime import date, datetime, time, timedelta

from ..models import (Appointment, Drug, ERVisit, Invoice, LabOrder, Prescription, Surgery)
from ..schemas import (AppointmentOut, DrugOut, ERVisitOut, InvoiceOut, LabOrderOut,
                       PrescriptionOut, SurgeryOut)


def day_bounds(d: date, tz_offset: int = 0):
    """UTC [lo, hi) bounds of the *local* calendar day d, for a client `tz_offset` minutes east of UTC."""
    lo = datetime.combine(d, time.min) - timedelta(minutes=tz_offset)
    return lo, lo + timedelta(days=1)


def _pname(p):
    return f"{p.first_name} {p.last_name}"


def appt_out(a: Appointment) -> AppointmentOut:
    return AppointmentOut(id=a.id, patient_id=a.patient_id, patient_name=_pname(a.patient),
                          doctor_id=a.doctor_id, doctor_name=a.doctor.full_name, start=a.start,
                          end=a.end, reason=a.reason, status=a.status)


def er_out(v: ERVisit) -> ERVisitOut:
    end = v.closed_at or datetime.utcnow()
    return ERVisitOut(id=v.id, patient_id=v.patient_id, patient_name=_pname(v.patient),
                      complaint=v.complaint, triage_level=v.triage_level, status=v.status,
                      bed_id=v.bed_id, bed_label=v.bed.label if v.bed else None,
                      attending_id=v.attending_id,
                      attending_name=v.attending.full_name if v.attending else None,
                      arrived_at=v.arrived_at, closed_at=v.closed_at,
                      wait_minutes=max(0, int((end - v.arrived_at).total_seconds() // 60)))


def surgery_out(s: Surgery) -> SurgeryOut:
    return SurgeryOut(id=s.id, patient_id=s.patient_id, patient_name=_pname(s.patient),
                      room_id=s.room_id, room_name=s.room.name, surgeon_id=s.surgeon_id,
                      surgeon_name=s.surgeon.full_name, procedure=s.procedure, start=s.start,
                      end=s.end, priority=s.priority, status=s.status, notes=s.notes,
                      team=[{"user_id": t.user_id, "name": t.user.full_name, "role": t.role} for t in s.team])


def drug_out(d: Drug) -> DrugOut:
    return DrugOut(id=d.id, name=d.name, form=d.form, stock=d.stock, reorder_level=d.reorder_level,
                   unit_price=d.unit_price, low_stock=d.stock <= d.reorder_level)


def rx_out(r: Prescription) -> PrescriptionOut:
    return PrescriptionOut(id=r.id, patient_id=r.patient_id, patient_name=_pname(r.patient),
                           drug_id=r.drug_id, drug_name=r.drug.name, prescriber_name=r.prescriber.full_name,
                           dosage=r.dosage, quantity=r.quantity, status=r.status,
                           created_at=r.created_at, dispensed_at=r.dispensed_at)


def lab_out(l: LabOrder) -> LabOrderOut:
    return LabOrderOut(id=l.id, patient_id=l.patient_id, patient_name=_pname(l.patient),
                       ordered_by_name=l.ordered_by.full_name, test_name=l.test_name,
                       priority=l.priority, status=l.status, result=l.result, abnormal=l.abnormal,
                       ordered_at=l.ordered_at, resulted_at=l.resulted_at)


def invoice_out(i: Invoice) -> InvoiceOut:
    total = round(sum(it.quantity * it.unit_price for it in i.items), 2)
    paid = round(sum(p.amount for p in i.payments), 2)
    return InvoiceOut(id=i.id, patient_id=i.patient_id, patient_name=_pname(i.patient), status=i.status,
                      created_at=i.created_at,
                      items=[dict(description=it.description, quantity=it.quantity, unit_price=it.unit_price)
                             for it in i.items],
                      total=total, paid=paid, balance=round(total - paid, 2))


# ======================= Phase 2 =======================
from ..models import Admission, ImagingOrder, Shift  # noqa: E402
from ..schemas import AdmissionOut, ImagingOut, ShiftOut  # noqa: E402


def admission_out(a: Admission) -> AdmissionOut:
    end = a.discharged_at or datetime.utcnow()
    return AdmissionOut(
        id=a.id, patient_id=a.patient_id, patient_name=_pname(a.patient), mrn=a.patient.mrn,
        allergies=a.patient.allergies, bed_id=a.bed_id, bed_label=a.bed.label if a.bed else None,
        ward=a.bed.ward if a.bed else None, attending_id=a.attending_id, attending_name=a.attending.full_name,
        source=a.source, reason=a.reason, status=a.status, admitted_at=a.admitted_at,
        discharged_at=a.discharged_at, discharge_summary=a.discharge_summary,
        los_days=max(0, (end - a.admitted_at).days),
        transfers=[dict(at=t.at, from_bed=t.from_bed.label if t.from_bed else None, to_bed=t.to_bed.label)
                   for t in a.transfers])


def shift_out(s: Shift) -> ShiftOut:
    return ShiftOut(id=s.id, user_id=s.user_id, user_name=s.user.full_name, role=s.user.role.value,
                    specialty=s.user.specialty, start=s.start, end=s.end, kind=s.kind, unit=s.unit, notes=s.notes)


def imaging_out(i: ImagingOrder) -> ImagingOut:
    return ImagingOut(
        id=i.id, patient_id=i.patient_id, patient_name=_pname(i.patient), ordered_by_name=i.ordered_by.full_name,
        modality=i.modality, body_part=i.body_part, clinical_info=i.clinical_info, contrast=i.contrast,
        priority=i.priority, status=i.status, scheduled_at=i.scheduled_at, performed_at=i.performed_at,
        radiologist_name=i.radiologist.full_name if i.radiologist else None, report=i.report,
        critical=i.critical, ordered_at=i.ordered_at, reported_at=i.reported_at)
