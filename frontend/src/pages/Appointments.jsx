import { useState } from 'react'
import { api } from '../api'
import { Field, Loading, Status, Table, fmtTime, nowLocalInput, toApiTime, tzOffset, useAction, useApi } from '../ui'

export default function Appointments() {
  const [day, setDay] = useState(() => new Date().toLocaleDateString('en-CA'))
  const list = useApi(`/appointments?day=${day}&tz_offset=${tzOffset()}`, { topics: ['appointments'] })
  const patients = useApi('/patients?limit=200')
  const staff = useApi('/staff')
  const [f, setF] = useState({ patient_id: '', doctor_id: '', reason: '', start: nowLocalInput(1), end: nowLocalInput(2) })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const act = useAction(list.reload)
  const docs = (staff.data || []).filter((s) => ['doctor', 'surgeon'].includes(s.role))
  const ready = f.patient_id && f.doctor_id && f.reason.trim() && f.start < f.end

  return (
    <>
      <div className="header">
        <div><h1>Appointments</h1><span className="muted">Double-booking a doctor is blocked</span></div>
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} style={{ width: 160 }} />
      </div>
      {act.banner}
      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Book appointment</h2>
        <div className="form">
          <Field label="Patient"><select value={f.patient_id} onChange={set('patient_id')}><option value="">Select…</option>{(patients.data || []).map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name} · {p.mrn}</option>)}</select></Field>
          <Field label="Doctor"><select value={f.doctor_id} onChange={set('doctor_id')}><option value="">Select…</option>{docs.map((d) => <option key={d.id} value={d.id}>{d.full_name} · {d.specialty}</option>)}</select></Field>
          <Field label="Start"><input type="datetime-local" value={f.start} onChange={set('start')} /></Field>
          <Field label="End"><input type="datetime-local" value={f.end} onChange={set('end')} /></Field>
          <Field label="Reason"><input value={f.reason} onChange={set('reason')} /></Field>
          <button className="btn" disabled={act.busy || !ready}
            onClick={() => act.run(() => api.post('/appointments', { patient_id: +f.patient_id, doctor_id: +f.doctor_id, reason: f.reason, start: toApiTime(f.start), end: toApiTime(f.end) }), 'Appointment booked')}>Book</button>
        </div>
      </div>
      <div className="card">
        <Loading state={list} />
        <Table empty="No appointments on this day." rows={list.data} cols={[
          { h: 'Time', render: (a) => `${fmtTime(a.start)} – ${fmtTime(a.end)}` },
          { h: 'Patient', render: (a) => a.patient_name }, { h: 'Doctor', render: (a) => a.doctor_name },
          { h: 'Reason', render: (a) => a.reason }, { h: 'Status', render: (a) => <Status value={a.status} /> },
          { h: '', render: (a) => a.status === 'scheduled' && (
            <div className="row">
              <button className="btn sm ghost" onClick={() => act.run(() => api.patch(`/appointments/${a.id}/status`, { status: 'completed' }))}>Complete</button>
              <button className="btn sm ghost" onClick={() => act.run(() => api.patch(`/appointments/${a.id}/status`, { status: 'no_show' }))}>No-show</button>
              <button className="btn sm danger" onClick={() => act.run(() => api.patch(`/appointments/${a.id}/status`, { status: 'cancelled' }))}>Cancel</button>
            </div>) },
        ]} />
      </div>
    </>
  )
}
