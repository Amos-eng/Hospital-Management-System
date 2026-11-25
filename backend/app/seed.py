"""Demo data: a Seattle-Grace-style staff roster, patients, rooms, drugs and a live ER."""
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (Admission, ImagingOrder, Shift, Bed, Drug, ERVisit, Invoice, InvoiceItem, LabOrder, OperatingRoom, Patient,
                     Prescription, Role, Surgery, SurgeryTeamMember, User, Vitals)
from .security import hash_password

DEMO_PASSWORD = "Hospital123!"

STAFF = [
    ("admin", "System Administrator", Role.admin, None),
    ("dr.shepherd", "Dr. Derek Shepherd", Role.surgeon, "Neurosurgery"),
    ("dr.grey", "Dr. Meredith Grey", Role.surgeon, "General Surgery"),
    ("dr.bailey", "Dr. Miranda Bailey", Role.surgeon, "General Surgery"),
    ("dr.yang", "Dr. Cristina Yang", Role.surgeon, "Cardiothoracic"),
    ("dr.karev", "Dr. Alex Karev", Role.doctor, "Pediatrics"),
    ("dr.webber", "Dr. Richard Webber", Role.doctor, "Internal Medicine"),
    ("dr.hunt", "Dr. Owen Hunt", Role.doctor, "Trauma / ER"),
    ("dr.torres", "Dr. Callie Torres", Role.surgeon, "Orthopedics"),
    ("dr.altman", "Dr. Erica Hahn", Role.doctor, "Anesthesiology"),
    ("nurse.olivia", "Olivia Harper, RN", Role.nurse, "ER"),
    ("nurse.joe", "Joe Wilson, RN", Role.nurse, "Surgical"),
    ("nurse.kim", "Kim Alvarez, RN", Role.nurse, "ICU"),
    ("nurse.ade", "Ade Bello, RN", Role.nurse, "General"),
    ("dr.chen", "Dr. Rae Chen", Role.radiologist, "Radiology"),
    ("pharm.lee", "Lee Park, PharmD", Role.pharmacist, None),
    ("lab.tran", "Tran Nguyen, MLT", Role.lab_tech, None),
    ("bill.cole", "Cole Matthews", Role.billing, None),
    ("front.amy", "Amy Reed", Role.receptionist, None),
]

PATIENTS = [
    ("Jane", "Doe", date(1985, 4, 12), "female", "O+", "Penicillin"),
    ("John", "Smith", date(1972, 9, 3), "male", "A-", None),
    ("Maria", "Garcia", date(1999, 1, 25), "female", "B+", "Latex"),
    ("David", "Okafor", date(1960, 11, 8), "male", "AB+", None),
    ("Aisha", "Mwangi", date(2010, 6, 30), "female", "O-", "Amoxicillin"),
    ("Liam", "Carter", date(1991, 3, 17), "male", "A+", None),
    ("Sofia", "Rossi", date(1948, 12, 2), "female", "B-", "Aspirin"),
    ("Chen", "Wei", date(1979, 7, 21), "male", "O+", None),
    ("Grace", "Njeri", date(1967, 2, 14), "female", "A+", "Iodine contrast"),
    ("Omar", "Hassan", date(1983, 8, 9), "male", "B+", None),
]

DRUGS = [
    ("Paracetamol 500mg", "tablet", 800, 100, 0.10), ("Ibuprofen 400mg", "tablet", 500, 100, 0.15),
    ("Amoxicillin 500mg", "capsule", 300, 80, 0.35), ("Morphine 10mg/ml", "injection", 40, 50, 4.50),
    ("Epinephrine 1mg/ml", "injection", 60, 30, 6.00), ("Metoprolol 50mg", "tablet", 250, 60, 0.25),
    ("Insulin Glargine", "injection", 25, 30, 18.00), ("Aspirin 75mg", "tablet", 600, 100, 0.05),
    ("Propofol 10mg/ml", "injection", 35, 40, 9.50), ("Normal Saline 1L", "bag", 150, 50, 2.20),
]


def seed_if_empty(db: Session):
    if db.scalar(select(User.id).limit(1)):
        return
    pw = hash_password(DEMO_PASSWORD)
    users = {u: User(username=u, full_name=n, role=r, specialty=s, password_hash=pw) for u, n, r, s in STAFF}
    db.add_all(users.values())
    patients = [Patient(mrn=f"MRN{i + 1:06d}", first_name=f, last_name=l, dob=d, sex=s, blood_type=bt,
                        allergies=al, phone=f"+254700{100000 + i}", insurance_provider="NHIF",
                        insurance_number=f"INS-{5000 + i}")
                for i, (f, l, d, s, bt, al) in enumerate(PATIENTS)]
    db.add_all(patients)
    rooms = [OperatingRoom(name=f"OR {n}") for n in range(1, 5)]
    beds = [Bed(label=f"ER-{n}", ward="ER") for n in range(1, 9)] + \
           [Bed(label=f"ICU-{n}", ward="ICU") for n in range(1, 5)] + \
           [Bed(label=f"GEN-{n}", ward="General") for n in range(1, 11)]
    drugs = [Drug(name=n, form=f, stock=s, reorder_level=r, unit_price=p) for n, f, s, r, p in DRUGS]
    db.add_all(rooms + beds + drugs)
    db.flush()

    t = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    # a live ER board
    er = [(patients[0], "Chest pain, shortness of breath", 2, -35), (patients[1], "Fractured forearm", 4, -80),
          (patients[2], "Severe allergic reaction", 1, -10), (patients[4], "High fever, vomiting", 3, -50)]
    for p, c, lvl, mins in er:
        db.add(ERVisit(patient_id=p.id, complaint=c, triage_level=lvl, arrived_at=datetime.utcnow() + timedelta(minutes=mins)))
    v = ERVisit(patient_id=patients[5].id, complaint="Motorcycle accident - head trauma", triage_level=1,
                status="in_treatment", bed_id=beds[0].id, attending_id=users["dr.hunt"].id,
                arrived_at=datetime.utcnow() - timedelta(minutes=25))
    beds[0].occupied = True
    db.add(v)
    # today's OR schedule
    ops = [(patients[3], rooms[0], "dr.shepherd", "Craniotomy - tumour resection", 1, 4, "urgent", "in_progress"),
           (patients[6], rooms[1], "dr.yang", "Coronary artery bypass x3", 2, 6, "elective", "scheduled"),
           (patients[7], rooms[2], "dr.torres", "Total knee replacement", 3, 5, "elective", "scheduled")]
    for p, room, sg, proc, off, dur, prio, st in ops:
        s = Surgery(patient_id=p.id, room_id=room.id, surgeon_id=users[sg].id, procedure=proc,
                    start=t + timedelta(hours=off - 2), end=t + timedelta(hours=off - 2 + dur), priority=prio, status=st)
        s.team = [SurgeryTeamMember(user_id=users["dr.altman"].id, role="anesthesiologist"),
                  SurgeryTeamMember(user_id=users["nurse.joe"].id, role="scrub_nurse")] if sg == "dr.shepherd" else []
        db.add(s)
    # inpatients (ward beds start after the 8 ER beds + 4 ICU beds in the list)
    icu1, gen1 = beds[8], beds[12]
    for p, bed, doc, why, days in [(patients[8], icu1, "dr.webber", "Post-op monitoring after cardiac stent", 2),
                                   (patients[9], gen1, "dr.karev", "Pneumonia - IV antibiotics", 3)]:
        bed.occupied = True
        db.add(Admission(patient_id=p.id, bed_id=bed.id, attending_id=users[doc].id, reason=why, source="direct",
                         admitted_at=datetime.utcnow() - timedelta(days=days, hours=3)))
    # radiology queue
    db.add(ImagingOrder(patient_id=patients[0].id, ordered_by_id=users["dr.hunt"].id, modality="xray", body_part="Chest",
                        clinical_info="Chest pain, SOB", priority="stat"))
    db.add(ImagingOrder(patient_id=patients[1].id, ordered_by_id=users["dr.torres"].id, modality="xray", body_part="Right forearm",
                        clinical_info="Suspected distal radius fracture", priority="urgent", status="scheduled",
                        scheduled_at=datetime.utcnow() + timedelta(minutes=40)))
    db.add(ImagingOrder(patient_id=patients[5].id, ordered_by_id=users["dr.hunt"].id, modality="ct", body_part="Head",
                        clinical_info="MVC head trauma", priority="stat", status="performed",
                        performed_at=datetime.utcnow() - timedelta(minutes=5)))
    # weekly roster: day 06:00-18:00, night 18:00-06:00 (UTC); deliberately thin on one night to show a gap
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    plan = {"day": ["dr.webber", "dr.grey", "dr.karev", "dr.bailey", "dr.yang", "nurse.olivia", "nurse.kim", "pharm.lee", "lab.tran", "dr.chen"],
            "night": ["dr.hunt", "dr.shepherd", "dr.torres", "nurse.joe", "nurse.ade"]}
    for d in range(-1, 7):
        for kind, who in plan.items():
            for u in who:
                if kind == "night" and u == "nurse.ade" and d == 3:
                    continue  # gap: only one nurse that night
                if kind == "night" and u in ("dr.shepherd", "dr.torres") and d % 2:
                    continue  # alternate nights
                start = today + timedelta(days=d, hours=6 if kind == "day" else 18)
                db.add(Shift(user_id=users[u].id, start=start, end=start + timedelta(hours=12), kind=kind,
                             unit="ICU" if "kim" in u else "ER" if u in ("dr.hunt", "nurse.olivia") else "General"))
    db.add(Shift(user_id=users["dr.bailey"].id, start=today + timedelta(days=1, hours=18), end=today + timedelta(days=2, hours=6),
                 kind="on_call", unit="Surgery", notes="Trauma surgery backup"))
    # vitals, labs, an rx, an invoice
    db.add(Vitals(patient_id=patients[0].id, heart_rate=118, systolic=150, diastolic=95, temperature_c=37.1, spo2=94, resp_rate=24))
    db.add(LabOrder(patient_id=patients[0].id, ordered_by_id=users["dr.hunt"].id, test_name="Troponin I", priority="stat"))
    db.add(LabOrder(patient_id=patients[4].id, ordered_by_id=users["dr.karev"].id, test_name="Full blood count"))
    db.add(Prescription(patient_id=patients[1].id, drug_id=drugs[1].id, prescriber_id=users["dr.torres"].id,
                        dosage="400mg every 8h with food", quantity=21))
    inv = Invoice(patient_id=patients[3].id)
    inv.items = [InvoiceItem(description="Craniotomy - surgeon fee", quantity=1, unit_price=4500),
                 InvoiceItem(description="OR time (4h)", quantity=4, unit_price=350),
                 InvoiceItem(description="ICU bed (per day)", quantity=2, unit_price=900)]
    db.add(inv)
    db.commit()
