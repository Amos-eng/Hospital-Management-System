import { useState } from 'react'
import { api } from '../api'
import { AdmitModal } from './Wards'
import { Field, Loading, Modal, Status, Table, useAction, useApi } from '../ui'

const ESI = { 1: 'Resuscitation', 2: 'Emergent', 3: 'Urgent', 4: 'Less urgent', 5: 'Non-urgent' }

export default function ER({ user }) {
  const board = useApi('/er', { poll: 60000, topics: ['er'] })
  const beds = useApi('/beds?ward=ER', { poll: 60000, topics: ['beds'] })
  const staff = useApi('/staff')
  const [admit, setAdmit] = useState(false)
  const [assign, setAssign] = useState(null)
  const [admitTo, setAdmitTo] = useState(null)
  const refresh = async () => { await Promise.all([board.reload(), beds.reload()]) }
  const act = useAction(refresh)
  const isDoc = ['doctor', 'surgeon', 'admin'].includes(user.role)
  const canAssign = ['doctor', 'surgeon', 'nurse', 'admin'].includes(user.role)

  return (
    <>
      <div className="header">
        <div><h1>Emergency Room</h1><span className="muted">Sorted by acuity, then wait time · live</span></div>
        <button className="btn" onClick={() => setAdmit(true)}>+ New arrival</button>
      </div>
      {act.banner}
      <div className="card" style={{ marginBottom: 14 }}>
        <h2>ER beds</h2>
        {beds.data && <div className="bed-grid">{beds.data.map((b) => <div key={b.id} className={`bed ${b.occupied ? 'occ' : 'free'}`}>{b.label} · {b.occupied ? 'occupied' : 'free'}</div>)}</div>}
      </div>
      <div className="card">
        <Loading state={board} />
        <Table empty="No patients in the ER right now." rows={board.data} cols={[
          { h: 'ESI', render: (v) => <span className={`esi esi-${v.triage_level}`} title={ESI[v.triage_level]}>{v.triage_level}</span> },
          { h: 'Patient', render: (v) => <><b>{v.patient_name}</b><br /><span className="muted small">{v.complaint}</span></> },
          { h: 'Wait', render: (v) => `${v.wait_minutes} min` },
          { h: 'Status', render: (v) => <Status value={v.status} /> },
          { h: 'Bed', render: (v) => v.bed_label || '—' },
          { h: 'Attending', render: (v) => v.attending_name || '—' },
          { h: '', render: (v) => (
            <div className="row">
              {canAssign && <button className="btn sm ghost" onClick={() => setAssign(v)}>Assign</button>}
              {isDoc && <>
                <button className="btn sm ghost" disabled={act.busy} onClick={() => setAdmitTo(v)}>Admit to ward</button>
                <button className="btn sm ghost" disabled={act.busy} onClick={() => act.run(() => api.post(`/er/${v.id}/close`, { status: 'discharged' }), 'Patient discharged')}>Discharge</button>
              </>}
            </div>
          ) },
        ]} />
      </div>
      {admitTo && <AdmitModal preset={{ patient_id: admitTo.patient_id, patient_name: admitTo.patient_name, complaint: admitTo.complaint, er_visit_id: admitTo.id }}
        onClose={() => setAdmitTo(null)} onDone={async () => { setAdmitTo(null); await refresh() }} />}
      {admit && <Arrival onClose={() => setAdmit(false)} onDone={async () => { setAdmit(false); await refresh() }} />}
      {assign && <Assign visit={assign} beds={beds.data || []} staff={(staff.data || []).filter((s) => ['doctor', 'surgeon'].includes(s.role))}
        onClose={() => setAssign(null)} onDone={async () => { setAssign(null); await refresh() }} />}
    </>
  )
}

function Arrival({ onClose, onDone }) {
  const [q, setQ] = useState('')
  const found = useApi(`/patients?q=${encodeURIComponent(q)}&limit=8`)
  const [pid, setPid] = useState('')
  const [complaint, setComplaint] = useState('')
  const [level, setLevel] = useState(3)
  const act = useAction(onDone)
  return (
    <Modal title="ER arrival / triage" onClose={onClose}>
      {act.banner}
      <div className="form">
        <Field label="Find patient (name, MRN, phone)"><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" /></Field>
        <Field label="Patient">
          <select value={pid} onChange={(e) => setPid(e.target.value)}>
            <option value="">Select…</option>
            {(found.data || []).map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name} · {p.mrn}</option>)}
          </select>
        </Field>
        <Field label="Triage level (ESI)">
          <select value={level} onChange={(e) => setLevel(+e.target.value)}>{Object.entries(ESI).map(([k, v]) => <option key={k} value={k}>{k} — {v}</option>)}</select>
        </Field>
      </div>
      <div style={{ margin: '12px 0' }}><Field label="Chief complaint"><input value={complaint} onChange={(e) => setComplaint(e.target.value)} /></Field></div>
      <button className="btn" disabled={act.busy || !pid || !complaint.trim()}
        onClick={() => act.run(() => api.post('/er', { patient_id: +pid, complaint, triage_level: level }))}>Register arrival</button>
    </Modal>
  )
}

function Assign({ visit, beds, staff, onClose, onDone }) {
  const [bed, setBed] = useState(visit.bed_id || '')
  const [doc, setDoc] = useState(visit.attending_id || '')
  const act = useAction(onDone)
  return (
    <Modal title={`Assign — ${visit.patient_name}`} onClose={onClose}>
      {act.banner}
      <div className="form">
        <Field label="Bed">
          <select value={bed} onChange={(e) => setBed(e.target.value)}>
            <option value="">Select…</option>
            {beds.map((b) => <option key={b.id} value={b.id} disabled={b.occupied && b.id !== visit.bed_id}>{b.label}{b.occupied && b.id !== visit.bed_id ? ' (occupied)' : ''}</option>)}
          </select>
        </Field>
        <Field label="Attending">
          <select value={doc} onChange={(e) => setDoc(e.target.value)}>
            <option value="">Select…</option>
            {staff.map((s) => <option key={s.id} value={s.id}>{s.full_name} · {s.specialty}</option>)}
          </select>
        </Field>
      </div>
      <p><button className="btn" disabled={act.busy || (!bed && !doc)}
        onClick={() => act.run(() => api.post(`/er/${visit.id}/assign`, { bed_id: bed ? +bed : null, attending_id: doc ? +doc : null }))}>Save</button></p>
    </Modal>
  )
}
