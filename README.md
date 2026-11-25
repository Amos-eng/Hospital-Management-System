# Grace Memorial — Hospital Management System

FastAPI + PostgreSQL backend, React (Vite) frontend.

## Phase 1

| Module | What it does |
|---|---|
| Patients & records | Registration (auto MRN), search, clinical notes, vitals, allergies, per-chart audit trail |
| Appointments & ER | Booking with double-booking protection; ER board sorted by ESI acuity then wait time; bed + attending assignment; admit/discharge frees the bed |
| Surgery / OR | OR timeline per room; booking is rejected if the room, the surgeon or any team member is already booked in that window; start/complete/cancel |
| Pharmacy, labs, billing | Prescriptions, stock-checked and allergy-checked dispensing, low-stock flags; lab order → collect → result (STAT first, abnormal flag); invoices, partial payments, void |

Role-based access: admin, doctor, surgeon, nurse, pharmacist, lab_tech, billing, receptionist. Every patient-record read and every write is written to the audit log (admin screen).

## Phase 2

| Module | What it does |
|---|---|
| Live updates | One WebSocket (`/api/ws`) per session. Boards (ER, OR, wards, labs, imaging, roster, dashboard) refresh the moment data changes, and targeted alerts pop up as toasts: ESI 1–2 ER arrivals (clinicians), abnormal labs and critical imaging findings (the ordering clinician only), STAT orders (lab / radiology), low drug stock (pharmacy). The socket carries only topic names and alert text; all record data still comes through the permission-checked REST API. Auto-reconnects and resyncs. |
| Inpatient wards | Ward bed map (ICU / General), admit directly or **from the ER** (releases the ER bed and closes the visit), bed transfers with history, discharge with a required summary. A patient can only have one active admission. |
| Staff roster | Weekly grid, on-duty-now panel, on-call. Blocks overlapping shifts and enforces 8 h rest between regular shifts; coverage strip flags shifts below minimum staffing (2 nurses, 1 doctor, 1 surgeon). Doctors/admin edit; everyone can view. |
| Radiology | X-ray / CT / MRI / ultrasound orders → schedule → perform → report. STAT first, one scanner per modality (no overlapping 30-min slots), contrast only for CT/MRI, contrast-allergy check with an audited override, critical-finding flag. New `radiologist` role (`dr.chen`). |

## Upgrading from phase 1

There are no database migrations yet. If you already ran phase 1, **delete `backend/hms.db`** (SQLite) so the new tables and demo data are created. With PostgreSQL, run `docker compose down -v` (this wipes the data), or add the `radiologist` role value and new tables yourself.

## Run locally (no Docker)

```bash
# backend (SQLite by default, demo data seeded on first start)
cd backend && pip install -r requirements.txt   # must include uvicorn[standard] for WebSockets
uvicorn app.main:app --reload            # http://localhost:8000/docs

# frontend
cd frontend && npm install && npm run dev  # http://localhost:5173
```

## Run with Docker (PostgreSQL)

```bash
echo "SECRET_KEY=$(openssl rand -hex 32)" > .env
docker compose up --build                 # UI http://localhost:8080, API http://localhost:8000/docs
```

Demo logins (password `Hospital123!`): `admin`, `dr.shepherd` (surgeon), `dr.hunt` (ER), `nurse.olivia`, `pharm.lee`, `lab.tran`, `bill.cole`, `front.amy`.
**Set `SEED_DEMO_DATA=0` and create real accounts before any real use.**

## Tests

```bash
cd backend && python -m pytest -q
```

## Known gaps / next phases

- Not production-ready for real patient data: no HIPAA/GDPR review, no password reset or MFA, no token revocation, no DB migrations (Alembic), no HTTPS config.
- The roster, surgery and appointment day filters use UTC days; boards display local time, so late-evening items near midnight can land on the neighbouring day.
- The roster does not yet check that a surgeon or ER doctor is actually on shift when a case is booked.
- Live updates run in a single server process; scaling to several workers needs a shared pub/sub (e.g. Redis).
- Suggested next phases: blood bank, insurance claims, reports/analytics, inpatient medication charts (MAR) and nursing tasks, patient portal, HL7/FHIR integration.
