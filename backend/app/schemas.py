from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Role


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth / users ----------
class UserOut(ORM):
    id: int
    username: str
    full_name: str
    role: Role
    specialty: str | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str
    password: str = Field(min_length=8)
    role: Role
    specialty: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- patients ----------
class PatientIn(BaseModel):
    first_name: str
    last_name: str
    dob: date
    sex: Literal["male", "female", "other"]
    phone: str | None = None
    address: str | None = None
    blood_type: str | None = None
    allergies: str | None = None
    insurance_provider: str | None = None
    insurance_number: str | None = None
    emergency_contact: str | None = None


class PatientOut(PatientIn, ORM):
    id: int
    mrn: str
    created_at: datetime


class NoteIn(BaseModel):
    kind: Literal["progress", "diagnosis", "discharge"] = "progress"
    text: str = Field(min_length=1)


class NoteOut(ORM):
    id: int
    kind: str
    text: str
    at: datetime
    author_name: str = ""


class VitalsIn(BaseModel):
    heart_rate: int | None = Field(None, ge=0, le=300)
    systolic: int | None = Field(None, ge=0, le=300)
    diastolic: int | None = Field(None, ge=0, le=200)
    temperature_c: float | None = Field(None, ge=25, le=45)
    spo2: int | None = Field(None, ge=0, le=100)
    resp_rate: int | None = Field(None, ge=0, le=80)


class VitalsOut(VitalsIn, ORM):
    id: int
    at: datetime


# ---------- appointments ----------
class AppointmentIn(BaseModel):
    patient_id: int
    doctor_id: int
    start: datetime
    end: datetime
    reason: str

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class AppointmentOut(ORM):
    id: int
    patient_id: int
    patient_name: str = ""
    doctor_id: int
    doctor_name: str = ""
    start: datetime
    end: datetime
    reason: str
    status: str


class StatusIn(BaseModel):
    status: str


# ---------- ER ----------
class ERArrivalIn(BaseModel):
    patient_id: int
    complaint: str
    triage_level: int = Field(ge=1, le=5)


class ERAssignIn(BaseModel):
    bed_id: int | None = None
    attending_id: int | None = None


class BedOut(ORM):
    id: int
    label: str
    ward: str
    occupied: bool


class ERVisitOut(ORM):
    id: int
    patient_id: int
    patient_name: str = ""
    complaint: str
    triage_level: int
    status: str
    bed_id: int | None
    bed_label: str | None = None
    attending_id: int | None
    attending_name: str | None = None
    arrived_at: datetime
    closed_at: datetime | None
    wait_minutes: int = 0


# ---------- surgery ----------
class SurgeryIn(BaseModel):
    patient_id: int
    room_id: int
    surgeon_id: int
    procedure: str
    start: datetime
    end: datetime
    priority: Literal["elective", "urgent", "emergency"] = "elective"
    notes: str | None = None
    team: list[dict] = []  # [{"user_id": 3, "role": "anesthesiologist"}]

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class SurgeryOut(ORM):
    id: int
    patient_id: int
    patient_name: str = ""
    room_id: int
    room_name: str = ""
    surgeon_id: int
    surgeon_name: str = ""
    procedure: str
    start: datetime
    end: datetime
    priority: str
    status: str
    notes: str | None
    team: list[dict] = []


class RoomOut(ORM):
    id: int
    name: str
    active: bool


# ---------- pharmacy ----------
class DrugIn(BaseModel):
    name: str
    form: str
    stock: int = Field(ge=0)
    reorder_level: int = Field(20, ge=0)
    unit_price: float = Field(ge=0)


class DrugOut(DrugIn, ORM):
    id: int
    low_stock: bool = False


class RestockIn(BaseModel):
    quantity: int = Field(gt=0)


class PrescriptionIn(BaseModel):
    patient_id: int
    drug_id: int
    dosage: str
    quantity: int = Field(gt=0)


class PrescriptionOut(ORM):
    id: int
    patient_id: int
    patient_name: str = ""
    drug_id: int
    drug_name: str = ""
    prescriber_name: str = ""
    dosage: str
    quantity: int
    status: str
    created_at: datetime
    dispensed_at: datetime | None


# ---------- labs ----------
class LabOrderIn(BaseModel):
    patient_id: int
    test_name: str
    priority: Literal["routine", "stat"] = "routine"


class LabResultIn(BaseModel):
    result: str = Field(min_length=1)
    abnormal: bool = False


class LabOrderOut(ORM):
    id: int
    patient_id: int
    patient_name: str = ""
    ordered_by_name: str = ""
    test_name: str
    priority: str
    status: str
    result: str | None
    abnormal: bool
    ordered_at: datetime
    resulted_at: datetime | None


# ---------- billing ----------
class ItemIn(BaseModel):
    description: str
    quantity: int = Field(1, gt=0)
    unit_price: float = Field(ge=0)


class InvoiceIn(BaseModel):
    patient_id: int
    items: list[ItemIn] = Field(min_length=1)


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    method: Literal["cash", "card", "insurance", "mobile_money"]


class InvoiceOut(BaseModel):
    id: int
    patient_id: int
    patient_name: str
    status: str
    created_at: datetime
    items: list[dict]
    total: float
    paid: float
    balance: float


# ======================= Phase 2 =======================
class AdmitIn(BaseModel):
    patient_id: int
    bed_id: int
    attending_id: int
    reason: str = Field(min_length=1, max_length=200)
    er_visit_id: int | None = None


class TransferIn(BaseModel):
    bed_id: int


class DischargeIn(BaseModel):
    summary: str = Field(min_length=5)


class AdmissionOut(BaseModel):
    id: int
    patient_id: int
    patient_name: str
    mrn: str
    allergies: str | None
    bed_id: int | None
    bed_label: str | None
    ward: str | None
    attending_id: int
    attending_name: str
    source: str
    reason: str
    status: str
    admitted_at: datetime
    discharged_at: datetime | None
    discharge_summary: str | None
    los_days: int
    transfers: list[dict]


class ShiftIn(BaseModel):
    user_id: int
    start: datetime
    end: datetime
    kind: Literal["day", "night", "on_call"]
    unit: str = "General"
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if (self.end - self.start).total_seconds() > 24 * 3600:
            raise ValueError("a shift cannot be longer than 24 hours")
        return self


class ShiftOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    role: str
    specialty: str | None
    start: datetime
    end: datetime
    kind: str
    unit: str
    notes: str | None


class ImagingIn(BaseModel):
    patient_id: int
    modality: Literal["xray", "ct", "mri", "ultrasound"]
    body_part: str = Field(min_length=1, max_length=60)
    clinical_info: str | None = Field(None, max_length=300)
    contrast: bool = False
    priority: Literal["routine", "urgent", "stat"] = "routine"
    override_allergy: bool = False


class ImagingScheduleIn(BaseModel):
    scheduled_at: datetime


class ImagingReportIn(BaseModel):
    report: str = Field(min_length=5)
    critical: bool = False


class ImagingOut(BaseModel):
    id: int
    patient_id: int
    patient_name: str
    ordered_by_name: str
    modality: str
    body_part: str
    clinical_info: str | None
    contrast: bool
    priority: str
    status: str
    scheduled_at: datetime | None
    performed_at: datetime | None
    radiologist_name: str | None
    report: str | None
    critical: bool
    ordered_at: datetime
    reported_at: datetime | None
