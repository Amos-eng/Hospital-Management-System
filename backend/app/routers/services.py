"""Pharmacy, laboratory and billing."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Drug, Invoice, InvoiceItem, LabOrder, Patient, Payment, Prescription,
                      Role, User, now)
from ..live import hub
from ..schemas import (DrugIn, DrugOut, InvoiceIn, InvoiceOut, LabOrderIn, LabOrderOut,
                       LabResultIn, PaymentIn, PrescriptionIn, PrescriptionOut, RestockIn)
from ..security import CLINICAL, audit, require
from .helpers import drug_out, invoice_out, lab_out, rx_out
from .patients import get_patient_or_404

router = APIRouter(prefix="/api", tags=["services"])


def allergy_match(allergies: str | None, drug_name: str) -> bool:
    """True if any listed allergy (comma/semicolon separated) appears in the drug name, or vice versa."""
    if not allergies:
        return False
    name = drug_name.lower()
    for a in allergies.replace(";", ",").split(","):
        a = a.strip().lower()
        if a and (a in name or name.split()[0] in a):
            return True
    return False


# =============== Pharmacy ===============
@router.get("/drugs", response_model=list[DrugOut])
def drugs(low_stock: bool = False, db: Session = Depends(get_db),
          _: User = Depends(require(*CLINICAL, Role.pharmacist))):
    out = [drug_out(d) for d in db.scalars(select(Drug).order_by(Drug.name)).all()]
    return [d for d in out if d.low_stock] if low_stock else out


@router.post("/drugs", response_model=DrugOut, status_code=201)
def add_drug(body: DrugIn, db: Session = Depends(get_db), user: User = Depends(require(Role.pharmacist))):
    if db.scalar(select(Drug).where(func.lower(Drug.name) == body.name.lower())):
        raise HTTPException(409, "Drug already exists")
    d = Drug(**body.model_dump())
    db.add(d)
    db.flush()
    audit(db, user, "CREATE", "drug", d.id)
    db.commit()
    return drug_out(d)


@router.post("/drugs/{did}/restock", response_model=DrugOut)
def restock(did: int, body: RestockIn, db: Session = Depends(get_db), user: User = Depends(require(Role.pharmacist))):
    d = db.get(Drug, did)
    if not d:
        raise HTTPException(404, "Drug not found")
    d.stock += body.quantity
    audit(db, user, "UPDATE", "drug", did, f"+{body.quantity}")
    db.commit()
    return drug_out(d)


@router.get("/prescriptions", response_model=list[PrescriptionOut])
def prescriptions(status: str | None = None, db: Session = Depends(get_db),
                  _: User = Depends(require(Role.pharmacist, Role.doctor, Role.surgeon))):
    q = select(Prescription).order_by(Prescription.created_at.desc()).limit(200)
    if status:
        q = q.where(Prescription.status == status)
    return [rx_out(r) for r in db.scalars(q).all()]


@router.post("/prescriptions", response_model=PrescriptionOut, status_code=201)
def prescribe(body: PrescriptionIn, db: Session = Depends(get_db), user: User = Depends(require(Role.doctor, Role.surgeon))):
    patient = get_patient_or_404(db, body.patient_id)
    drug = db.get(Drug, body.drug_id)
    if not drug:
        raise HTTPException(404, "Drug not found")
    r = Prescription(**body.model_dump(), prescriber_id=user.id)
    db.add(r)
    db.flush()
    audit(db, user, "CREATE", "prescription", r.id)
    db.commit()
    out = rx_out(r)
    # allergy safety net: surface a warning header-less hint in the audit trail
    if allergy_match(patient.allergies, drug.name):
        audit(db, user, "WARN", "prescription", r.id, f"Possible allergy match: {drug.name}")
        db.commit()
    return out


@router.post("/prescriptions/{rid}/dispense", response_model=PrescriptionOut)
def dispense(rid: int, db: Session = Depends(get_db), user: User = Depends(require(Role.pharmacist))):
    r = db.get(Prescription, rid)
    if not r:
        raise HTTPException(404, "Prescription not found")
    if r.status != "pending":
        raise HTTPException(409, f"Prescription is already {r.status}")
    if allergy_match(r.patient.allergies, r.drug.name):
        raise HTTPException(409, f"Allergy alert: patient is allergic to {r.drug.name}")
    if r.drug.stock < r.quantity:
        raise HTTPException(409, f"Insufficient stock ({r.drug.stock} left)")
    r.drug.stock -= r.quantity
    r.status = "dispensed"
    r.dispensed_at = now()
    audit(db, user, "UPDATE", "prescription", rid, "dispensed")
    db.commit()
    if r.drug.stock <= r.drug.reorder_level:
        hub.alert("warning", "Low stock", f"{r.drug.name}: {r.drug.stock} left (reorder level {r.drug.reorder_level})", roles={Role.pharmacist})
    return rx_out(r)


# =============== Laboratory ===============
@router.get("/labs", response_model=list[LabOrderOut])
def labs(status: str | None = None, db: Session = Depends(get_db),
         _: User = Depends(require(Role.lab_tech, *CLINICAL))):
    q = select(LabOrder).order_by(LabOrder.priority.desc(), LabOrder.ordered_at).limit(300)
    if status:
        q = q.where(LabOrder.status == status)
    return [lab_out(l) for l in db.scalars(q).all()]


@router.post("/labs", response_model=LabOrderOut, status_code=201)
def order_lab(body: LabOrderIn, db: Session = Depends(get_db), user: User = Depends(require(Role.doctor, Role.surgeon, Role.nurse))):
    get_patient_or_404(db, body.patient_id)
    l = LabOrder(**body.model_dump(), ordered_by_id=user.id)
    db.add(l)
    db.flush()
    audit(db, user, "CREATE", "lab_order", l.id, body.test_name)
    db.commit()
    if body.priority == "stat":
        hub.alert("warning", "STAT lab ordered", f"{body.test_name} — {l.patient.first_name} {l.patient.last_name}", roles={Role.lab_tech})
    return lab_out(l)


@router.post("/labs/{lid}/collect", response_model=LabOrderOut)
def collect(lid: int, db: Session = Depends(get_db), user: User = Depends(require(Role.lab_tech, Role.nurse))):
    l = db.get(LabOrder, lid)
    if not l:
        raise HTTPException(404, "Lab order not found")
    if l.status != "ordered":
        raise HTTPException(409, f"Order is already {l.status}")
    l.status = "collected"
    audit(db, user, "UPDATE", "lab_order", lid, "collected")
    db.commit()
    return lab_out(l)


@router.post("/labs/{lid}/result", response_model=LabOrderOut)
def result(lid: int, body: LabResultIn, db: Session = Depends(get_db), user: User = Depends(require(Role.lab_tech))):
    l = db.get(LabOrder, lid)
    if not l:
        raise HTTPException(404, "Lab order not found")
    if l.status != "collected":
        raise HTTPException(409, "Sample must be collected before resulting")
    l.status, l.result, l.abnormal, l.resulted_at = "resulted", body.result, body.abnormal, now()
    audit(db, user, "UPDATE", "lab_order", lid, "resulted" + (" ABNORMAL" if body.abnormal else ""))
    db.commit()
    if body.abnormal:
        hub.alert("critical" if l.priority == "stat" else "warning", "Abnormal lab result",
                  f"{l.test_name} — {l.patient.first_name} {l.patient.last_name}: {body.result}", user_ids={l.ordered_by_id})
    return lab_out(l)


# =============== Billing ===============
@router.get("/invoices", response_model=list[InvoiceOut])
def invoices(status: str | None = None, patient_id: int | None = None, db: Session = Depends(get_db),
             _: User = Depends(require(Role.billing, Role.receptionist))):
    q = select(Invoice).order_by(Invoice.created_at.desc()).limit(300)
    if status:
        q = q.where(Invoice.status == status)
    if patient_id:
        q = q.where(Invoice.patient_id == patient_id)
    return [invoice_out(i) for i in db.scalars(q).all()]


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(body: InvoiceIn, db: Session = Depends(get_db), user: User = Depends(require(Role.billing))):
    get_patient_or_404(db, body.patient_id)
    inv = Invoice(patient_id=body.patient_id)
    inv.items = [InvoiceItem(**i.model_dump()) for i in body.items]
    db.add(inv)
    db.flush()
    audit(db, user, "CREATE", "invoice", inv.id)
    db.commit()
    return invoice_out(inv)


@router.post("/invoices/{iid}/pay", response_model=InvoiceOut)
def pay(iid: int, body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(require(Role.billing))):
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv.status != "open":
        raise HTTPException(409, f"Invoice is {inv.status}")
    balance = invoice_out(inv).balance
    if body.amount > balance + 0.005:
        raise HTTPException(422, f"Payment exceeds balance of {balance:.2f}")
    inv.payments.append(Payment(amount=body.amount, method=body.method))
    db.flush()
    if invoice_out(inv).balance <= 0.005:
        inv.status, inv.paid_at = "paid", now()
    audit(db, user, "CREATE", "payment", iid, f"{body.amount:.2f} {body.method}")
    db.commit()
    return invoice_out(inv)


@router.post("/invoices/{iid}/void", response_model=InvoiceOut)
def void(iid: int, db: Session = Depends(get_db), user: User = Depends(require(Role.billing))):
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv.status == "paid":
        raise HTTPException(409, "Cannot void a paid invoice")
    inv.status = "void"
    audit(db, user, "UPDATE", "invoice", iid, "void")
    db.commit()
    return invoice_out(inv)
