import enum
from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(str, enum.Enum):
    admin = "admin"
    doctor = "doctor"
    surgeon = "surgeon"
    nurse = "nurse"
    pharmacist = "pharmacist"
    lab_tech = "lab_tech"
    billing = "billing"
    receptionist = "receptionist"
    radiologist = "radiologist"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role))
    specialty: Mapped[str | None] = mapped_column(String(80), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(20))  # READ / CREATE / UPDATE
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    mrn: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(60))
    last_name: Mapped[str] = mapped_column(String(60), index=True)
    dob: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(10))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    blood_type: Mapped[str | None] = mapped_column(String(5), nullable=True)
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    insurance_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    insurance_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    notes: Mapped[list["ClinicalNote"]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    vitals: Mapped[list["Vitals"]] = relationship(back_populates="patient", cascade="all, delete-orphan")


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30), default="progress")  # progress/diagnosis/discharge
    text: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    patient: Mapped[Patient] = relationship(back_populates="notes")
    author: Mapped[User] = relationship()


class Vitals(Base):
    __tablename__ = "vitals"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    systolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diastolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    spo2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resp_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    patient: Mapped[Patient] = relationship(back_populates="vitals")


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled/completed/cancelled/no_show
    patient: Mapped[Patient] = relationship()
    doctor: Mapped[User] = relationship()


class Bed(Base):
    __tablename__ = "beds"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(20), unique=True)
    ward: Mapped[str] = mapped_column(String(30))  # ER / ICU / General
    occupied: Mapped[bool] = mapped_column(Boolean, default=False)


class ERVisit(Base):
    __tablename__ = "er_visits"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    complaint: Mapped[str] = mapped_column(String(200))
    triage_level: Mapped[int] = mapped_column(Integer)  # ESI 1 (critical) .. 5 (non-urgent)
    status: Mapped[str] = mapped_column(String(20), default="waiting")  # waiting/in_treatment/admitted/discharged
    bed_id: Mapped[int | None] = mapped_column(ForeignKey("beds.id"), nullable=True)
    attending_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    arrived_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    patient: Mapped[Patient] = relationship()
    bed: Mapped[Bed | None] = relationship()
    attending: Mapped[User | None] = relationship()


class OperatingRoom(Base):
    __tablename__ = "operating_rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Surgery(Base):
    __tablename__ = "surgeries"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("operating_rooms.id"), index=True)
    surgeon_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    procedure: Mapped[str] = mapped_column(String(200))
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    priority: Mapped[str] = mapped_column(String(10), default="elective")  # elective/urgent/emergency
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled/in_progress/completed/cancelled
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient: Mapped[Patient] = relationship()
    room: Mapped[OperatingRoom] = relationship()
    surgeon: Mapped[User] = relationship()
    team: Mapped[list["SurgeryTeamMember"]] = relationship(cascade="all, delete-orphan")


class SurgeryTeamMember(Base):
    __tablename__ = "surgery_team"
    id: Mapped[int] = mapped_column(primary_key=True)
    surgery_id: Mapped[int] = mapped_column(ForeignKey("surgeries.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(30))  # assistant / anesthesiologist / scrub_nurse
    user: Mapped[User] = relationship()


class Drug(Base):
    __tablename__ = "drugs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    form: Mapped[str] = mapped_column(String(30))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    reorder_level: Mapped[int] = mapped_column(Integer, default=20)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    drug_id: Mapped[int] = mapped_column(ForeignKey("drugs.id"))
    prescriber_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    dosage: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/dispensed/cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    dispensed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    patient: Mapped[Patient] = relationship()
    drug: Mapped[Drug] = relationship()
    prescriber: Mapped[User] = relationship()


class LabOrder(Base):
    __tablename__ = "lab_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    ordered_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    test_name: Mapped[str] = mapped_column(String(100))
    priority: Mapped[str] = mapped_column(String(10), default="routine")  # routine/stat
    status: Mapped[str] = mapped_column(String(20), default="ordered")  # ordered/collected/resulted
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    abnormal: Mapped[bool] = mapped_column(Boolean, default=False)
    ordered_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    resulted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    patient: Mapped[Patient] = relationship()
    ordered_by: Mapped[User] = relationship()


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/paid/void
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    patient: Mapped[Patient] = relationship()
    items: Mapped[list["InvoiceItem"]] = relationship(cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(20))  # cash/card/insurance/mobile_money
    at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ======================= Phase 2 =======================
class Admission(Base):
    __tablename__ = "admissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    bed_id: Mapped[int | None] = mapped_column(ForeignKey("beds.id"), nullable=True)
    attending_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    er_visit_id: Mapped[int | None] = mapped_column(ForeignKey("er_visits.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="direct")  # er / direct
    reason: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(15), default="admitted", index=True)  # admitted / discharged
    admitted_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    discharged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discharge_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient: Mapped[Patient] = relationship()
    bed: Mapped[Bed | None] = relationship()
    attending: Mapped[User] = relationship()
    transfers: Mapped[list["BedTransfer"]] = relationship(cascade="all, delete-orphan", order_by="BedTransfer.at")


class BedTransfer(Base):
    __tablename__ = "bed_transfers"
    id: Mapped[int] = mapped_column(primary_key=True)
    admission_id: Mapped[int] = mapped_column(ForeignKey("admissions.id"), index=True)
    from_bed_id: Mapped[int | None] = mapped_column(ForeignKey("beds.id"), nullable=True)
    to_bed_id: Mapped[int] = mapped_column(ForeignKey("beds.id"))
    by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    from_bed: Mapped[Bed | None] = relationship(foreign_keys=[from_bed_id])
    to_bed: Mapped[Bed] = relationship(foreign_keys=[to_bed_id])


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[str] = mapped_column(String(10))  # day / night / on_call
    unit: Mapped[str] = mapped_column(String(30), default="General")
    notes: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user: Mapped[User] = relationship()


class ImagingOrder(Base):
    __tablename__ = "imaging_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    ordered_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    modality: Mapped[str] = mapped_column(String(15))  # xray / ct / mri / ultrasound
    body_part: Mapped[str] = mapped_column(String(60))
    clinical_info: Mapped[str | None] = mapped_column(String(300), nullable=True)
    contrast: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String(10), default="routine")  # routine / urgent / stat
    status: Mapped[str] = mapped_column(String(15), default="ordered", index=True)  # ordered/scheduled/performed/reported/cancelled
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    performed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    radiologist_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    ordered_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    patient: Mapped[Patient] = relationship()
    ordered_by: Mapped[User] = relationship(foreign_keys=[ordered_by_id])
    radiologist: Mapped[User | None] = relationship(foreign_keys=[radiologist_id])
